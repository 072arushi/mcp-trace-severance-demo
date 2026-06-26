"""
telemetry.py — OpenTelemetry setup shared by all three processes.

Each process calls `init_tracer("name")` once at startup. After that, any code
in the process can grab `tracer = get_tracer(__name__)` and create spans.

Spans go to Jaeger via OTLP over gRPC. Jaeger runs on localhost:4317 by default
(the docker-compose.yml maps that port).

The point of this module: keep OTel boilerplate out of the demo code. The
business logic just calls `with tracer.start_as_current_span("..."):`.
"""

import os
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import inject as _otel_inject, extract as _otel_extract


def init_tracer(service_name: str) -> trace.Tracer:
    """Wire up OTel for one process. Call once at startup."""
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def inject_into_carrier(carrier: dict) -> None:
    """Mutate `carrier` so it carries the current trace context. Used to inject
    into HTTP headers OR into MCP _meta — same call, different carrier."""
    _otel_inject(carrier)


def extract_from_carrier(carrier: dict):
    """Inverse: pull trace context out of a carrier dict. Used by the receiving
    side to continue the parent trace."""
    return _otel_extract(carrier)
