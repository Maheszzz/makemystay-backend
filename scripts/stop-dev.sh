#!/usr/bin/env bash
# Free port 8000 (or PORT=…) used by ./scripts/dev.sh
set -euo pipefail
PORT="${PORT:-8000}"
if ! command -v lsof >/dev/null 2>&1; then
  echo "lsof not found" >&2
  exit 1
fi
PIDS=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
if [[ -z "$PIDS" ]]; then
  echo "Nothing listening on port $PORT"
  exit 0
fi
echo "Stopping process(es) on port $PORT: $PIDS"
kill $PIDS 2>/dev/null || true
sleep 1
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Force kill..." >&2
  kill -9 $(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t) 2>/dev/null || true
fi
echo "Port $PORT is free"
