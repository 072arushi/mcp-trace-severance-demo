"""
verify_break.py — proves the tool_server's break-mode logic in isolation.

Runs offline, no network, no Jaeger needed. Just emits spans via a console
exporter so you can see by eye whether the trace IDs differ.

Expected output:
  HAPPY mode: parent.trace_id == child.trace_id  (same trace)
  BREAK mode: parent.trace_id != child.trace_id  (separate traces)

If BREAK fails here, the production demo will also fail, and we need a
different fix before re-running Jaeger.
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import (
    SpanContext, TraceFlags, NonRecordingSpan, set_span_in_context,
)
from opentelemetry.propagate import extract


# Wire up OTel with a console exporter so we can see span IDs.
provider = TracerProvider(resource=Resource.create({"service.name": "verify"}))
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("verify")


_INVALID_PARENT_CTX = set_span_in_context(
    NonRecordingSpan(SpanContext(
        trace_id=0,
        span_id=0,
        is_remote=False,
        trace_flags=TraceFlags(0),
    ))
)


def parent_context_for(meta: dict):
    if "traceparent" in meta:
        return extract(meta)
    return _INVALID_PARENT_CTX


print("=" * 72)
print("Test: simulate the tool server receiving a request, with an outer span")
print("active in the current process (mimicking event-loop context bleed).")
print("=" * 72)

# This outer span simulates whatever stale parent might be in the OTel context.
with tracer.start_as_current_span("outer.stale_parent") as outer:
    outer_trace_id = format(outer.get_span_context().trace_id, "032x")
    print(f"\nOuter span trace_id: {outer_trace_id}")

    # ---------- HAPPY mode ----------
    print("\n--- HAPPY mode (meta has traceparent) ---")
    meta_happy = {"traceparent": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"}
    parent_ctx = parent_context_for(meta_happy)
    with tracer.start_as_current_span("mcp.tools.call", context=parent_ctx) as call_span:
        happy_trace_id = format(call_span.get_span_context().trace_id, "032x")
        print(f"  child trace_id: {happy_trace_id}")
        print(f"  → expected to continue upstream trace (aaaa...)")
        assert happy_trace_id.startswith("aaaa"), \
            f"HAPPY mode failed: expected to continue aaaa... trace, got {happy_trace_id}"
        print("  ✓ continued upstream trace")

    # ---------- BREAK mode ----------
    print("\n--- BREAK mode (meta empty) ---")
    meta_break = {}
    parent_ctx = parent_context_for(meta_break)
    with tracer.start_as_current_span("mcp.tools.call", context=parent_ctx) as call_span:
        break_trace_id = format(call_span.get_span_context().trace_id, "032x")
        print(f"  child trace_id: {break_trace_id}")
        print(f"  outer trace_id: {outer_trace_id}")
        if break_trace_id == outer_trace_id:
            print("  ✗ FAIL — child inherited the outer (stale) trace")
            print("    The invalid-parent trick didn't work. Need a different fix.")
        else:
            print("  ✓ child started a brand-new root trace (different ID)")

print("\n" + "=" * 72)
print("If both checks above are ✓, the v3 patch will work in the live demo.")
print("=" * 72)