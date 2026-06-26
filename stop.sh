#!/usr/bin/env bash
# stop.sh — kill background processes started by run.sh
if [ -f /tmp/mcp-a2a-demo.pids ]; then
  read PIDS < /tmp/mcp-a2a-demo.pids
  kill $PIDS 2>/dev/null && echo "Stopped: $PIDS"
  rm /tmp/mcp-a2a-demo.pids
else
  echo "No PID file. Run ps to find them."
fi
