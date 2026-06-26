"""
smoke_test.py — verify the demo's logic without running the network stack.

Useful at the venue before the talk to make sure nothing's broken in the
plumbing. Doesn't replace the real demo — but catches dumb errors fast.

Run: python smoke_test.py
"""

import os
import sys
import asyncio


# ─────────────────────────────────────────────────────────────────────────────
# Stub out OTel and aiohttp/httpx BEFORE any demo modules are imported.
# This lets the smoke test run on a clean Python install with no deps.
# ─────────────────────────────────────────────────────────────────────────────
def _install_stubs():
    # Stub opentelemetry
    otel = type(sys)('opentelemetry')
    otel_trace = type(sys)('opentelemetry.trace')

    class _NoopSpan:
        def __init__(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def set_attribute(self, *a, **k): pass
        def get_span_context(self):
            class _Ctx:
                trace_id = 0xdeadbeef
            return _Ctx()
    class _NoopTracer:
        def start_as_current_span(self, *a, **k): return _NoopSpan()
    otel_trace.get_tracer = lambda *a, **k: _NoopTracer()

    otel_context = type(sys)('opentelemetry.context')

    sys.modules['opentelemetry'] = otel
    sys.modules['opentelemetry.trace'] = otel_trace
    sys.modules['opentelemetry.context'] = otel_context

    # Stub telemetry.py
    telemetry = type(sys)('telemetry')
    telemetry.init_tracer = lambda name: _NoopTracer()
    telemetry.extract_from_carrier = lambda c: None
    sys.modules['telemetry'] = telemetry

    # Stub httpx and aiohttp (protocols.py imports them at top)
    httpx = type(sys)('httpx')
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, *a, **k): raise RuntimeError("not used in smoke test")
    httpx.AsyncClient = _Client
    sys.modules['httpx'] = httpx


_install_stubs()


def test_bridge_modes():
    """Verify bridge.call_tool produces the right _meta in each mode."""
    print("Testing bridge modes...")

    injected = []
    def fake_inject(carrier):
        carrier["traceparent"] = "00-deadbeef-cafebabe-01"
        injected.append(carrier)

    sys.modules['telemetry'].inject_into_carrier = fake_inject

    # Now import bridge — its `from telemetry import ...` will pick up our stub
    import bridge

    captured_requests = []

    async def fake_mcp_call(url, request, headers):
        captured_requests.append((url, request, headers))
        from protocols import MCPResponse
        return MCPResponse(content=[{"type": "text", "text": "ok"}])

    bridge.mcp_call = fake_mcp_call

    async def run_one(mode):
        captured_requests.clear()
        os.environ["BRIDGE_MODE"] = mode
        await bridge.call_tool(
            mcp_server_url="http://test/mcp",
            tool_name="summarize",
            arguments={"document_id": "doc-1"},
            upstream_auth_header="Bearer xyz",
        )
        return captured_requests[0][1]

    # happy
    req = asyncio.run(run_one("happy"))
    assert "traceparent" in req.meta, f"happy mode: expected traceparent, got {req.meta}"
    print(f"  happy: _meta = {req.meta}")
    print(f"         ✓ traceparent was injected before the call")

    # break
    req = asyncio.run(run_one("break"))
    assert "traceparent" not in req.meta, f"break mode: expected NO traceparent, got {req.meta}"
    print(f"  break: _meta = {req.meta}")
    print(f"         ✓ no traceparent (this is what dies the trace)")

    # heal — exercises the bridge.call span path
    req = asyncio.run(run_one("heal"))
    assert "traceparent" in req.meta, f"heal mode: expected traceparent via bridge, got {req.meta}"
    print(f"  heal:  _meta = {req.meta}")
    print(f"         ✓ traceparent injected by the bridge component")


def test_protocol_shapes():
    """Verify the MCP and A2A wire shapes match what the spec expects."""
    print("\nTesting protocol shapes...")

    from protocols import MCPRequest, new_task

    req = MCPRequest(
        tool_name="summarize",
        arguments={"doc": "x"},
        meta={"traceparent": "00-aaaa-bbbb-01"},
    )
    payload = req.to_jsonrpc()

    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "tools/call"
    assert payload["params"]["name"] == "summarize"
    assert payload["params"]["_meta"]["traceparent"] == "00-aaaa-bbbb-01"
    print(f"  MCP request: method={payload['method']}, _meta carries traceparent ✓")

    task = new_task("summarize this")
    assert task.task_id.startswith("a2a-")
    assert task.context_id.startswith("ctx-")
    assert task.state == "submitted"
    print(f"  A2A task: task_id={task.task_id}, state={task.state} ✓")


def main():
    print("=" * 64)
    print("smoke test — verifies bridge logic without network or OTel install")
    print("=" * 64)
    test_bridge_modes()
    test_protocol_shapes()
    print("\n" + "=" * 64)
    print("✓ all smoke tests passed")
    print("=" * 64)
    print("\nFor the real demo:")
    print("  1. pip install -r requirements.txt")
    print("  2. docker compose up -d jaeger")
    print("  3. ./run.sh")
    print("  4. BRIDGE_MODE=happy python orchestrator.py   (then break, then heal)")


if __name__ == "__main__":
    main()

