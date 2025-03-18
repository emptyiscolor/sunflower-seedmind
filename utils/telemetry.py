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


tracer = None

def parse_otlp_headers(headers_str: str) -> dict:
    headers = {}
    for pair in headers_str.split(','):
        if '=' in pair:
            key, value = pair.split('=', 1)
            headers[key.strip()] = value.strip()
    return headers


def init_opentelemetry(otel_endpoint: str, otel_headers: str, otel_protocol: str, service_name: str):
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)
    
    headers = parse_otlp_headers(otel_headers) if otel_headers else None
    resource = Resource(attributes={"service.name": service_name})
    
    tracer_provider = TracerProvider(resource=resource)

    if otel_protocol == "grpc":
        otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint, headers=headers)
    elif otel_protocol == "http/protobuf":
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHTTPSpanExporter
            otlp_exporter = OTLPHTTPSpanExporter(endpoint=otel_endpoint, headers=headers)
        except ImportError:
            logging.error("OTLP HTTP exporter is not installed; falling back to gRPC exporter.")
            otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint, headers=headers)
    else:
        logging.warning("Unsupported OTLP protocol '%s' provided, using gRPC exporter instead.", otel_protocol)
        otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint, headers=headers)
    
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(tracer_provider)
    
    global tracer
    tracer = trace.get_tracer(__name__)
    
    openlit.init(tracer=tracer, disable_metrics=True)


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


def log_action(crs_action_category: str, crs_action_name: str, task_metadata: dict, extra_attributes: dict | None = None):
    if not tracer:
        return
    
    extra_attributes = extra_attributes or {}
    with tracer.start_as_current_span(crs_action_category) as span:
        span.set_attribute("crs.action.category", crs_action_category)
        span.set_attribute("crs.action.name", crs_action_name)

        for key, value in task_metadata.items():
            span.set_attribute(key, value)

        for key, value in extra_attributes.items():
            span.set_attribute(key, value)

        span.set_status(Status(StatusCode.OK))

    print(f"Logged CRS action: {crs_action_category} - {crs_action_name}")


def log_seedgen(
    task_id: str,
    action: str,
    target: str = None,
    harness_name: str = None
):
    extra_attributes = {}
    if target:
        extra_attributes["crs.action.target"] = target
    if harness_name:
        extra_attributes["crs.action.target.harness"] = harness_name

    try:
        log_action("input_generation", action, get_task_metadata(task_id), extra_attributes)
    except Exception as e:
        print(f"Failed to log CRS action: input_generation - {action}: {e}")
