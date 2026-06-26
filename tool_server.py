"""
tool_server.py — minimal MCP tool server.

The tool's spans either nest under the caller's trace (heal/happy mode) or
start a fresh disconnected trace (break mode), depending on whether the
incoming request had trace context in _meta.
"""

import asyncio
from aiohttp import web
from opentelemetry import trace
from opentelemetry.trace import (
    SpanContext, TraceFlags, NonRecordingSpan, set_span_in_context,
)

from telemetry import init_tracer, extract_from_carrier


_tracer = init_tracer("mcp-tool-server")

# An OTel context whose "current span" is an invalid (all-zero) SpanContext.
# When this is passed as `context=` to start_as_current_span, OTel treats it
# as "no parent — this span starts a brand new root trace". Unambiguous.
_INVALID_PARENT_CTX = set_span_in_context(
    NonRecordingSpan(SpanContext(
        trace_id=0,
        span_id=0,
        is_remote=False,
        trace_flags=TraceFlags(0),
    ))
)


def _parent_context_for(meta: dict):
    """If `_meta` carries `traceparent`, return a Context that continues the
    upstream trace. Otherwise return a Context whose parent is an invalid
    SpanContext — forcing a fresh root trace."""
    if "traceparent" in meta:
        return extract_from_carrier(meta)
    return _INVALID_PARENT_CTX


async def handle_call(request: web.Request) -> web.Response:
    payload = await request.json()
    method = payload.get("method")
    params = payload.get("params", {})
    meta = params.get("_meta", {})

    if method == "tools/call":
        parent_ctx = _parent_context_for(meta)
        with _tracer.start_as_current_span(
            "mcp.tools.call",
            context=parent_ctx,
            attributes={
                "mcp.tool.name": params.get("name", "?"),
                "mcp.meta.has_traceparent": "traceparent" in meta,
            },
        ):
            return await _do_call(params)

    return web.json_response({"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}})


async def _do_call(params: dict) -> web.Response:
    tool_name = params.get("name")

    with _tracer.start_as_current_span(
        "tool.execute",
        attributes={"tool.name": tool_name},
    ):
        with _tracer.start_as_current_span("tool.fetch_data"):
            await asyncio.sleep(0.05)
        with _tracer.start_as_current_span("tool.compute"):
            await asyncio.sleep(0.05)

        if tool_name == "summarize":
            result = {
                "content": [{"type": "text", "text": "The document discusses protocol seams."}],
                "isError": False,
            }
        else:
            result = {
                "content": [{"type": "text", "text": f"unknown tool: {tool_name}"}],
                "isError": True,
            }

    return web.json_response({"jsonrpc": "2.0", "id": params.get("id", 1), "result": result})


def main():
    app = web.Application()
    app.router.add_post("/mcp", handle_call)
    print("MCP tool server listening on http://localhost:8002/mcp")
    web.run_app(app, port=8002, print=None)


if __name__ == "__main__":
    main()