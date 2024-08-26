import threading
import grpc
import logging
import time
from typing import List, Optional

import grpc._channel
from grpc_health.v1 import health_pb2, health_pb2_grpc

from . import seedgeninj_pb2
from . import seedgeninj_pb2_grpc

# Configure logging
logger = logging.getLogger(__name__)

RETRY_INTERVAL = 10

class SeedGenRuntime:
    def __init__(self):
        self.grpc_server_address = "localhost:9002"
        self.service_name = "seedgen-injected"
        self.timeout = 5
        self.channel = None
        self.stub = None
        self.ready_event = threading.Event()
        self.available_harness_binaries = []

        # prepare the service
        self._prepare()

    def _prepare(self):
        self._connect()
        self.ready_event.set()

    def wait_until_ready(self):
        logger.info("Waiting for SeedGen service to be ready...")
        self.ready_event.wait()
        logger.info("SeedGen service is ready.")
    
    def _connect(self):
        while True:
            logger.info(
                f"Connecting to the gRPC server at {self.grpc_server_address}..."
            )
            try:
                options = [
                    ('grpc.max_send_message_length', 1024 * 1024 * 1024),
                    ('grpc.max_receive_message_length', 1024 * 1024 * 1024)
                ]
                self.channel = grpc.insecure_channel(self.grpc_server_address, options=options)
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
                    self._log_and_sleep(
                        f"Sleeping for {RETRY_INTERVAL} seconds before retrying...",
                        RETRY_INTERVAL,
                    )
            except grpc._channel._InactiveRpcError as e:
                # this is expected when the server is not ready, just retry
                self._log_and_sleep(
                    f"Sleeping for {RETRY_INTERVAL} seconds before retrying...",
                    RETRY_INTERVAL,
                )
            except Exception as e:
                logger.error(f"Unexpected error during health check: {e}")
                self._log_and_sleep(
                    f"Sleeping for {RETRY_INTERVAL} seconds before retrying...",
                    RETRY_INTERVAL,
                )

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

    def share(self, filename: str) -> Optional[str]:
        share_request = seedgeninj_pb2.ShareRequest(filename=filename)
        response = self._grpc_call(share_request, "Share")
        if response and response.success:
            return response.filename
        return None

    def run(self, harness_binary: str, seeds_path: List[str]) -> Optional[str]:
        run_request = seedgeninj_pb2.RunRequest(
            harness_binary=harness_binary, seeds_path=seeds_path
        )
        response = self._grpc_call(run_request, "Run")
        if response and response.success:
            return response.coverage
        return None
    
    def export_calls(self, harness_binary: str, seeds_path: List[str]) -> Optional[str]:
        export_calls_request = seedgeninj_pb2.ExportCallsRequest(
            harness_binary=harness_binary, seeds_path=seeds_path
        )
        response = self._grpc_call(export_calls_request, "ExportCalls")
        if response and response.success:
            return response.filename
        return None

    def close(self):
        if self.channel:
            self.channel.close()
            logger.info("gRPC channel closed.")

