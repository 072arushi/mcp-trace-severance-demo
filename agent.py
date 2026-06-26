"""
agent.py — skilled agent.

It's two things at once:
  1. An A2A server: accepts `tasks/send` requests from the orchestrator.
  2. An MCP client: calls the tool server when it needs a tool.

THE SEAM LIVES INSIDE THIS PROCESS. It's the moment between receiving an
A2A task (with its trace context flowing in via HTTP headers) and constructing
the outbound MCP `tools/call` request (which needs trace context in `_meta`).

The bridge module owns that transition. In `happy` mode the agent calls
bridge.call_tool() which manually injects. In `break` mode bridge.call_tool()
deliberately skips injection. In `heal` mode bridge.call_tool() owns it
properly with its own observable span.
"""

import asyncio
from aiohttp import web
from opentelemetry import trace, context as otel_context

from telemetry import init_tracer, extract_from_carrier
from bridge import call_tool


_tracer = init_tracer("skilled-agent")

MCP_TOOL_URL = "http://localhost:8002/mcp"


async def handle_a2a_request(request: web.Request) -> web.Response:
    """A2A server side. Receives a task from the orchestrator over HTTP."""
    payload = await request.json()
    method = payload.get("method")
    params = payload.get("params", {})

    # A2A propagates trace context via HTTP headers (the standard W3C way).
    # We pull it out so all our spans nest under the orchestrator's parent.
    incoming_headers = dict(request.headers)
    ctx = extract_from_carrier(incoming_headers)

    if method == "tasks/send":
        bridge_mode = request.headers.get("X-Bridge-Mode", "happy")
        with _tracer.start_as_current_span(
            "a2a.task.handle",
            context=ctx,
            attributes={
                "a2a.task_id": params.get("taskId", "?"),
                "a2a.context_id": params.get("contextId", "?"),
            },
        ):
            artifact = await _process_task(params, request.headers.get("Authorization", ""), bridge_mode)
            return web.json_response({
                "jsonrpc": "2.0",
                "id": payload.get("id", 1),
                "result": {
                    "taskId": params["taskId"],
                    "contextId": params["contextId"],
                    "state": "completed",
                    "artifact": artifact,
                },
            })

    return web.json_response({"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}})


async def _process_task(params: dict, upstream_auth: str, bridge_mode: str = "happy") -> str:
    """Agent's planning step + tool call. This is where 'agent reasoning'
    would happen in a real system — here it's deterministic."""

    with _tracer.start_as_current_span("agent.plan") as plan_span:
        await asyncio.sleep(0.03)
        plan_span.set_attribute("agent.decision", "call_tool:summarize")

    # ─────────────────── THE SEAM ───────────────────
    # This is the protocol boundary. We're about to leave A2A semantics and
    # enter MCP. The bridge module owns this transition.
    with _tracer.start_as_current_span("agent.call_tool") as call_span:
        call_span.set_attribute("tool.name", "summarize")
        response = await call_tool(
            mcp_server_url=MCP_TOOL_URL,
            tool_name="summarize",
            arguments={"document_id": "doc-123"},
            upstream_auth_header=upstream_auth,
            mode_override=bridge_mode,
        )
        call_span.set_attribute("tool.is_error", response.is_error)
    # ────────────────────────────────────────────────

    # Extract the result text out of the MCP response format.
    if response.content and response.content[0].get("type") == "text":
        return response.content[0]["text"]
    return "(no result)"


def main():
    app = web.Application()
    app.router.add_post("/a2a", handle_a2a_request)
    print("Skilled agent listening on http://localhost:8001/a2a")
    web.run_app(app, port=8001, print=None)


if __name__ == "__main__":
    main()
