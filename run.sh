#!/usr/bin/env bash
# run.sh — starts the MCP tool server and the skilled agent in background.
# Run the orchestrator separately so you can change BRIDGE_MODE between runs.

set -e

cd "$(dirname "$0")"

echo "Starting MCP tool server (port 8002)..."
python tool_server.py > /tmp/mcp-tool-server.log 2>&1 &
TOOL_PID=$!

echo "Starting skilled agent (port 8001)..."
python agent.py > /tmp/agent.log 2>&1 &
AGENT_PID=$!

echo ""
echo "PIDs: tool=$TOOL_PID agent=$AGENT_PID"
echo "Logs: /tmp/mcp-tool-server.log  /tmp/agent.log"
echo ""
echo "Now run the orchestrator (in this or another terminal):"
echo ""
echo "  BRIDGE_MODE=happy  python orchestrator.py"
echo "  BRIDGE_MODE=break  python orchestrator.py"
echo "  BRIDGE_MODE=heal   python orchestrator.py"
echo ""
echo "After each run, open Jaeger: http://localhost:16686"
echo ""
echo "Stop the background processes with:  kill $TOOL_PID $AGENT_PID"

# write PIDs out so a stop script can find them
echo "$TOOL_PID $AGENT_PID" > /tmp/mcp-a2a-demo.pids
