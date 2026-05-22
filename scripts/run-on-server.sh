#!/usr/bin/env bash
# Run a command on production app servers (same DB network as RDS).
#
# Usage:
#   ./scripts/run-on-server.sh alembic upgrade head
#   ./scripts/run-on-server.sh python3 scripts/seed_trust_reviews.py --limit 8 --reviews-per 2
#
# Env:
#   DEPLOY_PEM  — path to SSH key (default: ~/Downloads/makemystayrealty.pem)
#   DEPLOY_HOST — single host IP (default: all app servers)

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <command...>"
  echo "Example: $0 alembic upgrade head"
  exit 1
fi

PEM_KEY="${DEPLOY_PEM:-/Users/maheswaranm/Downloads/makemystayrealty.pem}"
REMOTE_DIR="/home/ubuntu/app"
CMD="$*"

if [ -n "${DEPLOY_HOST:-}" ]; then
  HOSTS=("$DEPLOY_HOST")
else
  HOSTS=("13.126.149.224" "13.201.61.117")
fi

SSH_OPTS=(-i "$PEM_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=20)

for HOST in "${HOSTS[@]}"; do
  echo "--------------------------------------------------------"
  echo "📍 $HOST → $CMD"
  ssh "${SSH_OPTS[@]}" "ubuntu@$HOST" bash -s <<ENDSSH
set -e
cd $REMOTE_DIR
source venv/bin/activate
set -a
. ./.env.production
set +a
export ENV=production
$CMD
ENDSSH
  echo "✅ Done on $HOST"
done

echo "--------------------------------------------------------"
echo "✅ Completed on all hosts (DB is shared — one successful run is enough for migrations/seed)."
