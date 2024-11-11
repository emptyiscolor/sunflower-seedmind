# utils/grpc.py
# This file contains a helper wrapper for gRPC calls to SeedD.

import functools
import time
import grpc
import grpc_health.v1.health_pb2 as health_pb2
import grpc_health.v1.health_pb2_grpc as health_pb2_grpc
from typing import List, Optional

from protobuf import seedd_pb2
from protobuf import seedd_pb2_grpc

DEFAULT_PORT = 9002
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_RETRY_INTERVAL = 1  # second


def grpc_call(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        start_time = time.time()
        last_error = None

        while time.time() - start_time < DEFAULT_TIMEOUT:
            try:
                self.health_check()
                return func(self, *args, **kwargs)
            except grpc.RpcError as rpc_error:
                last_error = rpc_error
                if rpc_error.code() == grpc.StatusCode.UNAVAILABLE:
                    time.sleep(DEFAULT_RETRY_INTERVAL)
                    continue
                # For other gRPC errors, raise immediately
                if rpc_error.code() == grpc.StatusCode.INVALID_ARGUMENT:
                    raise ValueError(
                        "Invalid arguments provided to gRPC call") from rpc_error
                elif rpc_error.code() == grpc.StatusCode.NOT_FOUND:
                    raise FileNotFoundError(
                        "Requested resource not found") from rpc_error
                else:
                    raise RuntimeError(
                        f"gRPC call failed: {rpc_error.details()} (Code: {rpc_error.code().name})") from rpc_error

        # If we've exhausted our retries, raise the last error
        raise RuntimeError(
            f"gRPC server remained unavailable after {DEFAULT_TIMEOUT} seconds"
        ) from last_error
    return wrapper


class SeedD:
    def __init__(self, ip_addr: str):
        self.ip_addr = ip_addr
        self.channel = grpc.insecure_channel(f"{ip_addr}:{DEFAULT_PORT}")
        self.stub = seedd_pb2_grpc.SeedDStub(self.channel)

    def health_check(self):
        """Performs a health check on the gRPC server."""
        health_stub = health_pb2_grpc.HealthStub(self.channel)
        health_stub.Check(health_pb2.HealthCheckRequest())

    @grpc_call
    def run_seeds(self, harness_binary: str, seeds_path: List[str]) -> seedd_pb2.RunSeedsResponse:
        """Runs the seeds and returns the coverage."""
        request = seedd_pb2.RunSeedsRequest(
            harness_binary=harness_binary, seeds_path=seeds_path)
        return self.stub.RunSeeds(request, compression=grpc.Compression.Gzip)

    @grpc_call
    def get_region_source(
        self,
        filepath: str,
        start_line: int,
        start_column: int,
        end_line: int,
        end_column: int
    ) -> seedd_pb2.GetRegionSourceResponse:
        """Gets the source code for a region."""
        request = seedd_pb2.GetRegionSourceRequest(
            filepath=filepath,
            start_line=start_line,
            start_column=start_column,
            end_line=end_line,
            end_column=end_column
        )
        return self.stub.GetRegionSource(request, compression=grpc.Compression.Gzip)

    @grpc_call
    def extract_function_source(
        self,
        harness_binary: str,
        filepath: str,
        line: Optional[int] = None,
        function_name: Optional[str] = None
    ) -> seedd_pb2.ExtractFunctionSourceResponse:
        """Extracts the source code for a function."""
        if not (line or function_name):
            raise ValueError(
                "Must provide either line number or function name")
        if line and function_name:
            raise ValueError(
                "Cannot provide both line number and function name")
        request = seedd_pb2.ExtractFunctionSourceRequest(
            harness_binary=harness_binary,
            filepath=filepath
        )
        if line:
            request.line = line
        else:
            request.function_name = function_name
        return self.stub.ExtractFunctionSource(request, compression=grpc.Compression.Gzip)

    @grpc_call
    def get_call_graph(self) -> seedd_pb2.GetCallGraphResponse:
        """Gets the call graph for a harness."""
        request = seedd_pb2.GetCallGraphRequest()
        return self.stub.GetCallGraph(request, compression=grpc.Compression.Gzip)
