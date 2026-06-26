"""
bridge.py — the Protocol Bridge.

This is the component the talk is about. It sits at the seam between A2A and
MCP. The skilled agent routes every outbound MCP call through `bridge.call_tool`
instead of calling MCP directly.

Three modes (set via BRIDGE_MODE env var):

  happy : caller injects manually before calling — vanilla path
  break : seam is naive — no _meta injection, trace dies at the boundary
  heal  : bridge owns context propagation — injects per SEP-414, emits its
          own observable span

This is the SINGLE place where the failure modes happen and get fixed. That
fact is the architectural argument of the talk: when this logic is named and
centralized, it becomes testable, observable, and ownable. When it's scattered
across agent code, it's invisible.
"""

from __future__ import annotations
import os
from opentelemetry import trace

from protocols import MCPRequest, MCPResponse, mcp_call
from telemetry import inject_into_carrier


# Single source of truth for which mode we're in.
def mode() -> str:
    return os.environ.get("BRIDGE_MODE", "happy").lower()


# A separate tracer for the bridge itself. The point: in `heal` mode, the
# bridge emits its OWN spans, visible in the trace UI as a named component.
# In `break` mode, those spans don't appear — illustrating that the bridge
# is invisible exactly when you most need to see it.
_tracer = trace.get_tracer("protocol.bridge")


async def call_tool(
    mcp_server_url: str,
    tool_name: str,
    arguments: dict,
    upstream_auth_header: str,
    mode_override: str | None = None,
) -> MCPResponse:
    """
    Bridge-mediated MCP call. The agent never calls mcp_call() directly;
    it always goes through here. That's what makes the bridge a real
    architectural component instead of scattered glue code.
    """
    current_mode = mode_override if mode_override is not None else mode()

    if current_mode == "happy":
        # Vanilla path: caller is expected to have injected trace context
        # into _meta themselves. Works, but every call site has to remember
        # to do this. Forget once → silent failure.
        request = MCPRequest(tool_name=tool_name, arguments=arguments)
        inject_into_carrier(request.meta)  # caller does the injection here
        return await mcp_call(
            mcp_server_url,
            request,
            headers={"Authorization": upstream_auth_header},
        )

    elif current_mode == "break":
        # THE BREAK: no _meta injection. The MCP server has no idea what trace
        # this call belongs to. It starts a fresh trace. Two disconnected trees
        # in the UI. Task succeeds. No alarm fires.
        request = MCPRequest(tool_name=tool_name, arguments=arguments)
        # ← no inject_into_carrier(request.meta) here.
        return await mcp_call(
            mcp_server_url,
            request,
            headers={"Authorization": upstream_auth_header},
        )

    elif current_mode == "heal":
        # THE HEAL: bridge owns context propagation. Emits its own span
        # ("bridge.call") that the audience can see in the trace UI. Injects
        # trace context into _meta per SEP-414 BEFORE the call leaves.
        with _tracer.start_as_current_span(
            "bridge.call",
            attributes={
                "bridge.tool": tool_name,
                "bridge.target": mcp_server_url,
            },
        ) as span:
            request = MCPRequest(tool_name=tool_name, arguments=arguments)
            inject_into_carrier(request.meta)  # SEP-414: traceparent → _meta
            span.set_attribute("bridge.injected_keys", ",".join(request.meta.keys()))

            # Stub points for the other three failure modes (auth exchange,
            # validation, lifecycle registry) would also live here.
            response = await mcp_call(
                mcp_server_url,
                request,
                headers={"Authorization": upstream_auth_header},
            )
            span.set_attribute("bridge.result.is_error", response.is_error)
            return response

    else:
        raise ValueError(f"Unknown BRIDGE_MODE: {current_mode!r}. "
                         f"Use one of: happy, break, heal")
