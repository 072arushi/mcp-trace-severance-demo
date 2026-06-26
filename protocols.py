"""
protocols.py — minimal A2A and MCP wire implementations.

These are intentionally simple. The point of the demo is the SEAM, not the
protocols themselves. What matters:
  - Both use JSON-RPC 2.0 over HTTP.
  - MCP requests carry a `_meta` envelope (this is where trace context lives).
  - A2A tasks have a `contextId` and `taskId`; MCP tasks have a separate `taskId`.

If the real SDKs change between now and your talk, this code doesn't break.
The seam behavior is what we're demonstrating.
"""

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import httpx


# ─────────────────────────────────────────────────────────────────────────────
# A2A
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class A2ATask:
    """Minimal A2A task representation. Real A2A has more fields; these are
    the ones that matter for showing the seam problem."""
    task_id: str
    context_id: str
    state: str  # submitted | working | input-required | completed | failed | canceled | rejected
    message: str
    result: Optional[str] = None


def new_task(message: str) -> A2ATask:
    return A2ATask(
        task_id=f"a2a-{uuid.uuid4().hex[:8]}",
        context_id=f"ctx-{uuid.uuid4().hex[:8]}",
        state="submitted",
        message=message,
    )


async def a2a_send(agent_url: str, task: A2ATask, headers: dict[str, str]) -> A2ATask:
    """A2A client side: send a task to an agent and get the completed task back.

    Sends the OAuth bearer token in the Authorization header (the way A2A does it).
    The orchestrator caller is responsible for putting OTel trace headers in too.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tasks/send",
        "params": {
            "taskId": task.task_id,
            "contextId": task.context_id,
            "message": {"role": "user", "parts": [{"type": "text", "text": task.message}]},
        },
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(agent_url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        result = data["result"]
        return A2ATask(
            task_id=result["taskId"],
            context_id=result["contextId"],
            state=result["state"],
            message=task.message,
            result=result.get("artifact"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# MCP
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MCPRequest:
    """A `tools/call` request. The interesting field is `_meta` — that's where
    trace context, correlation IDs, and bridge-relevant data ride along."""
    tool_name: str
    arguments: dict
    meta: dict = field(default_factory=dict)  # this is `_meta` on the wire

    def to_jsonrpc(self) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": self.tool_name,
                "arguments": self.arguments,
                "_meta": self.meta,
            },
        }


@dataclass
class MCPResponse:
    """Tool result. Shape matches the MCP spec for tools/call response."""
    content: list[dict]
    is_error: bool = False


async def mcp_call(server_url: str, request: MCPRequest, headers: dict[str, str]) -> MCPResponse:
    """Send an MCP tools/call to a server. This is what crosses THE SEAM.

    NOTE: it is the *caller's* responsibility to populate `request.meta` with
    trace context. The MCP spec says `_meta` is "reserved by MCP to allow
    clients and servers to attach additional metadata to their interactions."
    SEP-414 reserves `traceparent`, `tracestate`, `baggage` as well-known keys.

    Whether anything actually populates _meta is what determines whether the
    demo breaks or heals.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(server_url, json=request.to_jsonrpc(), headers=headers)
        r.raise_for_status()
        data = r.json()
        result = data["result"]
        return MCPResponse(
            content=result.get("content", []),
            is_error=result.get("isError", False),
        )
