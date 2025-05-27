import logging
import json
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.status import Status, StatusCode
import openlit

from utils.redis import get_redis_client


def init_opentelemetry(otel_endpoint: str, otel_headers: str, otel_protocol: str, service_name: str):
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)

    resource = Resource(attributes={"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)

    if otel_protocol == "grpc":
        otlp_exporter = OTLPSpanExporter(
            endpoint=otel_endpoint, headers=otel_headers)
    elif otel_protocol == "http/protobuf":
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHTTPSpanExporter
            otlp_exporter = OTLPHTTPSpanExporter(
                endpoint=otel_endpoint, headers=otel_headers)
        except ImportError:
            logging.error(
                "OTLP HTTP exporter is not installed; falling back to gRPC exporter.")
            otlp_exporter = OTLPSpanExporter(
                endpoint=otel_endpoint, headers=otel_headers)
    else:
        logging.warning(
            "Unsupported OTLP protocol '%s' provided, using gRPC exporter instead.", otel_protocol)
        otlp_exporter = OTLPSpanExporter(
            endpoint=otel_endpoint, headers=otel_headers)

    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(tracer_provider)

    openlit.init(tracer=trace.get_tracer(__name__), disable_metrics=True)


def get_task_metadata(task_id: str):
    redis_client = get_redis_client()
    if redis_client:
        task_metadata = redis_client.get(f"global:task_metadata:{task_id}")
        if task_metadata:
            return json.loads(task_metadata)

    return {
        "round.id": "test-round",
        "task.id": task_id,
        "team.id": "test-team",
    }
