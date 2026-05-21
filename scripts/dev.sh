#!/usr/bin/env bash
# Local FastAPI (from repo root, venv activated): ./scripts/dev.sh
# If 8000 is busy: PORT=8001 ./scripts/dev.sh  (and point VITE_API_BASE_URL at that port)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-8000}"
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use:" >&2
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >&2
  echo "Run: ./scripts/stop-dev.sh   (or: PORT=$PORT ./scripts/stop-dev.sh)" >&2
  echo "Or use another port: PORT=8001 $0" >&2
  exit 1
fi
exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
