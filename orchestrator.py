"""
orchestrator.py — A2A orchestrator client.

The driver. Sends one A2A task to the skilled agent, prints the result and
the trace ID so you can find it in Jaeger.

Usage:
    BRIDGE_MODE=happy  python orchestrator.py
    BRIDGE_MODE=break  python orchestrator.py
    BRIDGE_MODE=heal   python orchestrator.py
"""

import asyncio
import os
import sys
from opentelemetry import trace

from telemetry import init_tracer, inject_into_carrier
from protocols import new_task, a2a_send


_tracer = init_tracer("orchestrator")

AGENT_URL = "http://localhost:8001/a2a"


async def run(user_message: str) -> None:
    mode = os.environ.get("BRIDGE_MODE", "happy")

    with _tracer.start_as_current_span(
        "orchestrator.run",
        attributes={"bridge.mode": mode, "user.message": user_message},
    ) as root_span:
        trace_id = format(root_span.get_span_context().trace_id, "032x")

        print(f"\n{'─' * 64}")
        print(f"BRIDGE_MODE = {mode}")
        print(f"trace ID   = {trace_id}")
        print(f"Jaeger     = http://localhost:16686/trace/{trace_id}")
        print(f"{'─' * 64}\n")

        task = new_task(user_message)

        with _tracer.start_as_current_span("orchestrator.dispatch_task"):
            # A2A propagates trace context via HTTP headers — the standard
            # W3C Trace Context way. Same call as the bridge does for MCP,
            # but the carrier is headers instead of _meta.
            headers = {
                "Authorization": "Bearer fake-oauth-token-with-broad-scope",
                "X-Bridge-Mode": mode,
            }
            inject_into_carrier(headers)

            completed = await a2a_send(AGENT_URL, task, headers)

        print(f"task state : {completed.state}")
        print(f"task result: {completed.result}")
        print()

    # Force span flush before exiting so traces actually reach Jaeger.
    trace.get_tracer_provider().shutdown()


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "summarize this document"
    asyncio.run(run(msg))
