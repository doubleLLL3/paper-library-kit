#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/.server.pid"

if [ -f "$PIDFILE" ]; then
  PID=$(cat "$PIDFILE")
  kill "$PID" 2>/dev/null && echo "Server stopped (PID $PID)" || echo "Process $PID not found"
  rm -f "$PIDFILE"
else
  echo "No running server found."
fi
