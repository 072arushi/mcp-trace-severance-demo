# `mcp-a2a-seam-demo`

A runnable, visual demonstration of the trace-severance failure at the A2A↔MCP seam — and how a named bridge component heals it.

---

## What you'll see

Three runs of the **same multi-agent task**, with one env var toggling between modes:

| Mode | Behavior | Trace UI shows |
|------|----------|----------------|
| `happy` | OTel context injected manually | One trace tree, end-to-end |
| `break` | Naive seam — no injection | Two disconnected trace trees |
| `heal` | Bridge interceptor enabled | One trace tree, with bridge spans visible |

The task itself **succeeds in all three modes**. Only the trace UI tells you something is wrong. That's the silent failure.

---

## Architecture

```
                          ┌──────────────────────────────┐
                          │  Jaeger (trace UI)           │
                          │  http://localhost:16686      │
                          └────────────▲─────────────────┘
                                       │ OTLP spans (all processes)
                                       │
   ┌──────────────────┐  A2A   ┌──────────────────┐  MCP   ┌──────────────────┐
   │  Orchestrator    │ ─────► │  Skilled Agent   │ ─────► │  MCP Tool Server │
   │  :8000           │        │  :8001           │        │  :8002           │
   │  A2A client      │        │  A2A server +    │        │  MCP server      │
   │                  │        │  MCP client      │        │                  │
   └──────────────────┘        └──────────────────┘        └──────────────────┘
                                       │
                                       │ ⟵ THE SEAM lives here
                                       │   (inside the agent,
                                       │    at the MCP call site)
```

The seam is **inside the skilled agent's process** — at the moment its in-process MCP client constructs a `tools/call` request. That's the boundary the bridge wraps.

---

## Quick start

```bash
# one-time
docker compose up -d jaeger

# install deps
pip install -r requirements.txt

# run the three processes (in separate terminals or via the run script)
./run.sh
```

Then in a fourth terminal, drive the demo:

```bash
# Run 1 — happy path (default)
BRIDGE_MODE=happy python orchestrator.py "summarize this document"

# Run 2 — the break (one env var change)
BRIDGE_MODE=break python orchestrator.py "summarize this document"

# Run 3 — the heal
BRIDGE_MODE=heal python orchestrator.py "summarize this document"
```

After each run, open Jaeger at **http://localhost:16686** and look at the trace.

---

## The demo flow (what the speaker says)

### Setup (30 sec)
> "Three processes: an A2A orchestrator, a skilled agent, an MCP tool server. They're connected exactly the way the spec recommends. Let's run the happy path."

Run mode `happy`. Open Jaeger. Show **one trace tree, end-to-end** — five spans nested cleanly.

### The break (90 sec)
> "Now I'm going to change one thing. One environment variable. Watch what happens."

Run mode `break`. Open Jaeger. The same task succeeds — same final answer, same task lifecycle, no errors anywhere. But the trace UI now shows **two disconnected trees**:
- Tree 1: orchestrator → agent → `mcp_client.call_tool` (ends here)
- Tree 2: `tool_server.handle_call` → `tool.execute` (starts fresh)

Point at the screen: *"That's the silent failure. The task worked. The user is happy. But your observability is lying to you. You can never debug a production incident across that gap."*

### The heal (90 sec)
> "Now the bridge."

Run mode `heal`. Open Jaeger. **One trace tree again** — and there's a new span: `bridge.inject_context`. The bridge is now a first-class, observable component sitting at the seam.

> "Same code. Same protocols. Same agent. The only change: the seam has a name."

---

## What's inside each file

- `tool_server.py` — minimal MCP server, returns a hardcoded summary
- `agent.py` — skilled agent. Receives A2A tasks, calls the MCP tool. **The seam lives in `call_tool()`.**
- `orchestrator.py` — driver. Sends one A2A task, prints the result.
- `bridge.py` — the named bridge component. Has three behaviors keyed off `BRIDGE_MODE`.
- `protocols.py` — minimal A2A and MCP wire-format implementations (JSON-RPC over HTTP).
- `telemetry.py` — OTel boilerplate, shared by all three processes.
- `docker-compose.yml` — Jaeger all-in-one.
- `run.sh` — starts the three Python processes with logging.

---

## What this demo does *not* do

- **Doesn't use real LLMs.** The "agent" is deterministic. We're showing protocol behavior, not model behavior.
- **Doesn't use the official SDKs.** Wire-compatible JSON-RPC implementation that follows MCP and A2A specs exactly where it matters (`_meta` envelope, task lifecycle, OAuth-bearer headers). Lets the demo run offline and stay stable across SDK releases.
- **Doesn't show the other three failures.** Trace severance is enough to make the point. The slides cover the rest.

---

## Variants you can demo if time permits

The bridge module also has stubs for the other three failures, gated by the same env var:

- `BRIDGE_MODE=auth-leak` — shows the agent forwarding the full upstream token
- `BRIDGE_MODE=auth-heal` — shows token exchange (mocked IdP, returns scoped token)
- `BRIDGE_MODE=orphan` — agent cancels its A2A task; MCP task keeps running (visible as a still-emitting span)
- `BRIDGE_MODE=orphan-heal` — bridge fan-out cancels MCP when A2A terminates
