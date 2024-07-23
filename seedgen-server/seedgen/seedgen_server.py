import grpc
import logging
import os
import shlex
import subprocess
import time
import uuid
import yaml
import requests
import threading

from concurrent import futures
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from typing import List

from config import SEEDGEN_PATH, ARGUS_PATH, SEEDGEN_INJECTED_PATH, SEEDPOOL_PATH
from service import SeedGenService
import agent

from . import seedgen_pb2
from . import seedgen_pb2_grpc


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CP_ROOT = os.getenv("AIXCC_CP_ROOT")
CRS_SCRATCH = os.getenv("AIXCC_CRS_SCRATCH_SPACE")

def copy_directory(src: str, dst: str):
    if not os.path.exists(dst):
        subprocess.run(["cp", "-r", src, dst], check=True)


def generate_seeds(service, cp: str, harness_binary: str):

    # Start seedgen agent
    agent.start_seedgen(service, cp, harness_binary)

    # Check if seed path really exists
    if not os.path.exists(f"{SEEDGEN_PATH}/{cp}/output/{harness_binary}/merge"):
        logger.error(f"Seed path does not exist, seed gen failed: {SEEDGEN_PATH}/{cp}/output/{harness_binary}/merge")
        response = seedgen_pb2.SeedGenResponse()
        response.success = False
        return response

    response = seedgen_pb2.SeedGenResponse()
    response.success = True

    seed_path = f"{SEEDGEN_PATH}/{cp}/output/{harness_binary}/merge"
    if not os.listdir(seed_path):
        seed_path = f"{SEEDGEN_PATH}/{cp}/output/{harness_binary}/seeds"

    response.seed_path = seed_path
    return response


def prepare_scratch():
    os.makedirs(SEEDGEN_PATH, exist_ok=True)
    subprocess.run(["rm", "-rf", f"{SEEDGEN_PATH}/*"], check=True)
    copy_directory("/argus", ARGUS_PATH)
    copy_directory("/seedgen-injected", SEEDGEN_INJECTED_PATH)
    copy_directory("/seeds-global", SEEDPOOL_PATH)


class SeedGenServicer(seedgen_pb2_grpc.SeedGenServicer):
    def __init__(self):
        self.services = {}
        self.ports = {}
        self.lock = threading.Lock()

    def GenerateSeeds(self, request, context):
        logger.info(
            f"Received request for project {request.cp}, harness {request.harness_id}"
        )

        # Read project configuration
        with open(f"{CP_ROOT}/{request.cp}/project.yaml", "r") as f:
            project_configuration = yaml.safe_load(f)

        # Find the CP's service. If it doesn't exist, create it.
        with self.lock:
            if request.cp not in self.services:
                service_port = None
                for port in range(9010, 9100):
                    if port not in self.ports:
                        self.ports[port] = True
                        service_port = port
                        break
                if service_port is None:
                    logger.error("No available ports.")
                    error_response = seedgen_pb2.SeedGenResponse()
                    error_response.success = False
                    return error_response

                # Create a new service
                service = SeedGenService(request.cp, project_configuration, service_port)
                self.services[request.cp] = service
            else:
                service = self.services[request.cp]
        
        service.wait_until_ready()

        harnesses = project_configuration["harnesses"]
        harness_binary = None
        for harness_id, harness in harnesses.items():
            if harness_id == request.harness_id:
                harness_binary = harness["binary"]
                break
        if (
            harness_binary is None
            or harness_binary not in service.available_harness_binaries
        ):
            logger.error("Harness not found.")
            error_response = seedgen_pb2.SeedGenResponse()
            error_response.success = False
            return error_response

        # use run to merge the seed pool
        if os.getenv("FORCE_DISABLE_SEEDPOOL") is None:
            global_seeds_1 = []
            global_seeds_2 = []
            for idx, seed in enumerate(os.listdir("/seeds-global")):
                if idx % 2 == 0:
                    global_seeds_1.append(f"/seeds-global/{seed}")
                else:
                    global_seeds_2.append(f"/seeds-global/{seed}")
            service.run(harness_binary, global_seeds_1)
            service.run(harness_binary, global_seeds_2)
            logger.info(f"[*] Finish merging global seeds pool for project {request.cp}, harness {request.harness_id}.")

        response =  generate_seeds(service, request.cp, harness_binary)
        logger.info(f"[*] Finish generating seeds for project {request.cp}, harness {request.harness_id}.")
        return response

def pend_dind_health(host):
    url = f"http://{host}/_ping"
    
    while True:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print("DinD is healthy!")
                return
            else:
                print(f"DinD not healthy yet. Status code: {response.status_code}")
        except requests.RequestException as e:
            print(f"Error checking DinD health: {e}")
        
        time.sleep(5)

def serve():
    logger.info("BugBuster FuzzLoop - SeedGen version 1.1.11, starting...")
    prepare_scratch()

    docker_host = os.getenv("REAL_DIND_HOST") # shall be something like: tcp://crs-dind-2:2375
    dind_host = docker_host.split("//")[1]
    pend_dind_health(dind_host)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    seedgen_pb2_grpc.add_SeedGenServicer_to_server(SeedGenServicer(), server)

    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set(
        "SeedGen", health_pb2.HealthCheckResponse.ServingStatus.Value("SERVING")
    )

    server.add_insecure_port("[::]:9001")
    server.start()
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)
