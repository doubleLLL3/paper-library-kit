#!/usr/bin/env bash
# Start the paper library server in the background.
# Usage: bash start.sh [port]

PORT="${1:-8765}"
DIR="$(cd "$(dirname "$0")" && pwd)"
LOGFILE="$DIR/.server.log"
PIDFILE="$DIR/.server.pid"

# Kill any previous instance
if [ -f "$PIDFILE" ]; then
  OLD_PID=$(cat "$PIDFILE")
  kill "$OLD_PID" 2>/dev/null && echo "Stopped previous server (PID $OLD_PID)"
  rm -f "$PIDFILE"
fi

# Start in background
nohup python3 "$DIR/server.py" "$PORT" > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
PID=$!

sleep 1

# Verify the server actually started
if ! kill -0 "$PID" 2>/dev/null; then
  echo ""
  echo "  ❌ Server failed to start. Error:"
  cat "$LOGFILE"
  rm -f "$PIDFILE"
  exit 1
fi

echo ""
echo "  Paper Library is running at: http://localhost:$PORT"
echo "  To stop:  bash stop.sh"
echo "  Logs:     $LOGFILE"
echo ""
