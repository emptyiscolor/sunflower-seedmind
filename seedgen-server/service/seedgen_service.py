import os
import shlex
import subprocess
import threading
import grpc
import logging
import time
from typing import List, Optional

from grpc_health.v1 import health_pb2, health_pb2_grpc

from . import seedgeninj_pb2
from . import seedgeninj_pb2_grpc

# Configure logging
logger = logging.getLogger(__name__)

from config import (
    MAX_RETRIES,
    RETRY_INTERVAL,
    SEEDGEN_PATH,
    SEEDPOOL_PATH,
    ARGUS_PATH,
    SEEDGEN_INJECTED_PATH,
)
from .docker_utils import get_docker_image, get_entrypoint

CP_ROOT = os.getenv("AIXCC_CP_ROOT")
CRS_SCRATCH = os.getenv("AIXCC_CRS_SCRATCH_SPACE")

def copy_directory(src: str, dst: str):
    if not os.path.exists(dst):
        subprocess.run(["cp", "-r", src, dst], check=True)


class SeedGenService:
    def __init__(self, cp, project_configuration, port: int):
        docker_host = os.getenv("REAL_DIND_HOST") # shall be something like: tcp://crs-dind-2:2375
        dind_host = docker_host.split("//")[1].split(":")[0]

        self.port = port
        self.grpc_server_address = f"{dind_host}:{port}"
        self.service_name = "seedgen-injected"
        self.timeout = 5
        self.channel = None
        self.stub = None
        self.ready_event = threading.Event()
        self.available_harness_binaries = []

        self.cp = cp
        self.project_configuration = project_configuration

        # prepare the service
        self._prepare()

    def _prepare(self):
        self._start_cp()
        self._connect()
        self._compile_cp()
        self.ready_event.set()

    def wait_until_ready(self):
        logger.info("Waiting for SeedGen service to be ready...")
        self.ready_event.wait()
        logger.info("SeedGen service is ready.")
    
    def _read_run_pov_command(self):
        cp_path = f"{SEEDGEN_PATH}/{self.cp}/fake_cp_root"
        commands = []
        for harness in self.project_configuration["harnesses"]:
            harness_name = self.project_configuration["harnesses"][harness]["name"]
            # Set up other Docker options
            entrypoint_str = f"--entrypoint=echo"
            # Use run.sh to start the Docker container (build mode)
            docker_extra_args = (
                f"{entrypoint_str}"
            )
            docker_host = os.getenv("REAL_DIND_HOST")

            blob_file = "/tmp/hi"
            with open(blob_file, "w") as f:
                f.write("42-b3yond-6ug")

            command = subprocess.check_output(
                ["/bin/bash", "-c", f"./run.sh -x run_pov {blob_file} {harness_name}"],
                env={
                    "DOCKER_EXTRA_ARGS": docker_extra_args,
                    "DOCKER_HOST": docker_host,
                },
                cwd=cp_path,
            )
            logger.info(f"Run POV command: {command}")
            commands.append(command.decode("utf-8").strip())
        return commands
    
    def _start_cp(self):
        image = get_docker_image(self.project_configuration["docker_image"])
        entrypoint = get_entrypoint(image)
        seed_path = f"{SEEDGEN_PATH}/{self.cp}/output"
        os.makedirs(seed_path, exist_ok=True)
        cp_path = f"{SEEDGEN_PATH}/{self.cp}/fake_cp_root"
        copy_directory(f"{CP_ROOT}/{self.cp}", cp_path)
        mount = {
            ARGUS_PATH: "/argus",
            SEEDGEN_INJECTED_PATH: "/seedgen-injected",
            SEEDPOOL_PATH: "/seeds-global",
            seed_path: "/seedgen_output",
        }
        mount_str = " ".join(
            [f"-v {shlex.quote(k)}:{shlex.quote(v)}" for k, v in mount.items()]
        )
        env_vars = {
            "ORIG_ENTRY": entrypoint,
        }
        env_str = " ".join(
            [f"-e {shlex.quote(k)}={shlex.quote(v)}" for k, v in env_vars.items()]
        )
        # Set up other Docker options
        entrypoint_str = f"--entrypoint=/seedgen-injected"
        network_str = f"-p {self.port}:9002"
        # Use run.sh to start the Docker container (build mode)
        docker_extra_args = (
            f"{mount_str} {env_str} {entrypoint_str} {network_str} --privileged"
        )
        docker_host = os.getenv("REAL_DIND_HOST")

        subprocess.Popen(
            ["/bin/bash", "-c", "./run.sh -x build"],
            env={
                "DOCKER_EXTRA_ARGS": docker_extra_args,
                "DOCKER_HOST": docker_host,
            },
            cwd=cp_path,
        )
        logger.info(f"Started CP {self.cp} in Docker container.")
    
    def _compile_cp(self):
        expected_harness_binaries = [
            harness["binary"] for harness in self.project_configuration["harnesses"].values()
        ]
        harness_binaries = self.compile(expected_harness_binaries)
        if not harness_binaries:
            logger.error("Failed to build harnesses.")
            return
        self.available_harness_binaries = harness_binaries

        run_pov_command = self._read_run_pov_command()
        for command in run_pov_command:
            logger.info(f"Executing command: {command}")
            self.execute(command)

    def _connect(self):
        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(
                f"Connecting to the gRPC server at {self.grpc_server_address}... (attempt {attempt}/{MAX_RETRIES})"
            )
            try:
                self.channel = grpc.insecure_channel(self.grpc_server_address)
                health_stub = health_pb2_grpc.HealthStub(self.channel)
                health_check_response = self._perform_health_check(health_stub)
                if (
                    health_check_response.status
                    == health_pb2.HealthCheckResponse.SERVING
                ):
                    logger.info("Health check passed, service is healthy.")
                    self.stub = seedgeninj_pb2_grpc.SeedGenStub(self.channel)
                    return
                else:
                    logger.warning("Health check failed, service is not healthy.")
                    self.channel.close()
                    if attempt < MAX_RETRIES:
                        self._log_and_sleep(
                            f"Sleeping for {RETRY_INTERVAL} seconds before retrying...",
                            RETRY_INTERVAL,
                        )
                    else:
                        logger.error("Max retries reached, exiting.")
                        raise ConnectionError("Failed to connect to gRPC server.")
            except Exception as e:
                logger.error(f"Unexpected error during health check: {e}")
                if attempt < MAX_RETRIES:
                    self._log_and_sleep(
                        f"Sleeping for {RETRY_INTERVAL} seconds before retrying...",
                        RETRY_INTERVAL,
                    )
                else:
                    logger.error("Max retries reached, exiting.")
                    raise ConnectionError("Failed to connect to gRPC server.")

    def _perform_health_check(
        self, health_stub: health_pb2_grpc.HealthStub
    ) -> health_pb2.HealthCheckResponse:
        health_check_request = health_pb2.HealthCheckRequest(service=self.service_name)
        return health_stub.Check(health_check_request, timeout=self.timeout)

    def _log_and_sleep(self, message: str, interval: int) -> None:
        logger.info(message)
        time.sleep(interval)

    def _grpc_call(self, request, method_name: str):
        if not self.stub:
            raise ConnectionError("gRPC stub is not initialized.")

        try:
            logger.info(f"Calling {method_name} method with request: {request}")
            method = getattr(self.stub, method_name)
            response = method(request)
            logger.info(f"Received response: {response}")
            return response
        except grpc.RpcError as e:
            logger.error(f"RPC failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        return None

    def compile(self, expected_harness_binaries: List[str]) -> Optional[List[str]]:
        compile_request = seedgeninj_pb2.CompileRequest(
            expected_harness_binaries=expected_harness_binaries
        )
        response = self._grpc_call(compile_request, "Compile")
        if response and response.success:
            return response.harness_binaries
        return None

    def locate(self, harness_binary: str, function_name: str) -> Optional[tuple]:
        locate_request = seedgeninj_pb2.LocateRequest(
            harness_binary=harness_binary, function_name=function_name
        )
        response = self._grpc_call(locate_request, "Locate")
        if response and response.success:
            return response.filename, response.line
        return None

    def view(self, filename: str, line: int) -> Optional[str]:
        view_request = seedgeninj_pb2.ViewRequest(filename=filename, line=line)
        response = self._grpc_call(view_request, "View")
        if response and response.success:
            return response.source
        return None

    def run(self, harness_binary: str, seeds_path: List[str]) -> Optional[str]:
        run_request = seedgeninj_pb2.RunRequest(
            harness_binary=harness_binary, seeds_path=seeds_path
        )
        response = self._grpc_call(run_request, "Run")
        if response and response.success:
            return response.coverage
        return None
    
    def execute(self, command: str):
        execute_request = seedgeninj_pb2.ExecuteRequest(command=command)
        response = self._grpc_call(execute_request, "Execute")
        if response:
            logger.info(f"Execute return: {response.return_value}")
            logger.info(f"Execute stdout: {response.stdout}")
            logger.info(f"Execution stderr: {response.stderr}")

    def close(self):
        if self.channel:
            self.channel.close()
            logger.info("gRPC channel closed.")
