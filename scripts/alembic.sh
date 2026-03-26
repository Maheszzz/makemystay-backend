#!/usr/bin/env bash
# Run Alembic using the project venv (same as deploy.sh on the server).
# Usage: ./scripts/alembic.sh upgrade head
#        ./scripts/alembic.sh current
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
elif [[ -f venv/bin/activate ]]; then
  # shellcheck source=/dev/null
  source venv/bin/activate
else
  echo "No virtualenv found. Create one and install deps:" >&2
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi
exec alembic "$@"
