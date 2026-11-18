#!/bin/bash
# Simplified PM2 based zero-downtime deployment for FastAPI
#
# On every deploy:
#   1. Sync files over rsync
#   2. Install dependencies and run migrations
#   3. Zero-downtime reload via PM2

set -e

# ===== CONFIG & OVERRIDES =====
EC2_USER="ubuntu"
# Use DEPLOY_HOST environment variable if set, else fallback to default production IP.
EC2_HOST="${DEPLOY_HOST:-13.126.149.224}"
SERVER_HOST="$EC2_HOST"

# Use DEPLOY_PEM environment variable if set, else fallback to default local path.
PEM_KEY="${DEPLOY_PEM:-/Users/maheswaranm/Downloads/makemystayrealty.pem}"
REMOTE_DIR="/home/ubuntu/app"

# Common SSH options for reliability and automated environments
SSH_OPTS="-i $PEM_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o ServerAliveInterval=60"
SSH="ssh $SSH_OPTS $EC2_USER@$EC2_HOST"

echo "🚀 Starting Backend Deployment..."
# ===== TARGET SERVERS =====
# We have a Load Balancer (ELB) with two targets. We must deploy to BOTH.
ALL_SERVERS=("13.126.149.224" "13.201.61.117")

SEED_DONE=0
for EC2_HOST in "${ALL_SERVERS[@]}"; do
    echo "--------------------------------------------------------"
    echo "📍 Target Host: $EC2_HOST"
    SSH="ssh $SSH_OPTS $EC2_USER@$EC2_HOST"

# ===== PREFLIGHT CHECK =====
echo "🔍 Checking server reachability..."
if ! ssh $SSH_OPTS -o BatchMode=yes $EC2_USER@$EC2_HOST "exit" 2>/dev/null; then
  echo "❌ Error: Cannot reach server @ $EC2_HOST via SSH (Port 22)."
  echo "--------------------------------------------------------"
  echo "👉 Double-check the following:"
  echo "1. AWS Security Group: Is your current public IP whitelisted for TCP 22?"
  echo "2. Instance Status: Is the instance running in the AWS EC2 console?"
  echo "3. Public IP: Did the IP change? (Elastic IP usage recommended)."
  echo "4. Path to PEM: Is your $PEM_KEY correct? (Try setting DEPLOY_PEM)."
  echo "5. Local Network: Some Wi-Fi networks block Outbound Port 22."
  echo "--------------------------------------------------------"
  exit 1
fi
echo "✅ Server reachable. Proceeding..."

echo "💾 Checking server disk space..."
DISK_PCT=$($SSH "df / --output=pcent | tail -1 | tr -d ' %'")
echo "   Disk usage: ${DISK_PCT}%"

# When disk is tight, free space before rsync/pip (100% full → pip: "No usable temporary directory")
if [ "${DISK_PCT:-0}" -ge 70 ]; then
  echo "⚠️  Disk ≥ 70% — running auto-cleanup on server before deploy..."
  $SSH "bash -s" << 'CLEANUP'
set +e
find /home/ubuntu/app/logs -name "*.log" -mtime +3 -delete 2>/dev/null || true
find /home/ubuntu/app -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find /home/ubuntu/app -type f -name "*.log" -size +20M 2>/dev/null | while read -r f; do : > "$f" || true; done
sudo apt-get clean -y 2>/dev/null || true
sudo apt-get autoclean -y 2>/dev/null || true
sudo rm -rf /var/cache/apt/archives/*.deb 2>/dev/null || true
sudo journalctl --vacuum-size=80M 2>/dev/null || true
rm -rf /home/ubuntu/.cache/pip /home/ubuntu/.npm/_cacache 2>/dev/null || true
command -v pip >/dev/null 2>&1 && pip cache purge 2>/dev/null || true
command -v docker >/dev/null 2>&1 && docker system prune -af 2>/dev/null || true
sudo find /var/tmp -type f -atime +2 -delete 2>/dev/null || true
sudo mysql -e "PURGE BINARY LOGS BEFORE NOW() - INTERVAL 1 HOUR;" 2>/dev/null || true
CLEANUP
  DISK_PCT=$($SSH "df / --output=pcent | tail -1 | tr -d ' %'")
  echo "   Disk after cleanup: ${DISK_PCT}%"
fi

if [ "${DISK_PCT:-0}" -ge 95 ]; then
  echo "❌ Root filesystem is still ≥95% full after cleanup. pip cannot create temp files."
  echo "   SSH in and free space, e.g.: sudo du -xh / --max-depth=2 | sort -h | tail -30"
  echo "   Or resize the EBS volume / remove large files under /var/log, Docker data, or old backups."
  exit 1
fi

# ===== UPLOAD SOURCE =====
# Note: .env.production is preserved on EC2 and NOT overwritten from local dev config.
echo "📦 Uploading source files..."
rsync -az --delete \
  --exclude='.venv' --exclude='venv' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='*.egg-info' --exclude='.DS_Store' \
  --exclude='tests/' --exclude='logs/' \
  -e "ssh -i $PEM_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=30" \
  app alembic scripts alembic.ini requirements.txt ecosystem.config.js \
  $EC2_USER@$EC2_HOST:$REMOTE_DIR/ 2>/dev/null || \
  scp -i "$PEM_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=30 -r \
    app alembic scripts alembic.ini requirements.txt ecosystem.config.js \
    $EC2_USER@$EC2_HOST:$REMOTE_DIR/

# Seed runs once (shared DB) on the first host only when RUN_SEED_REVIEWS=1
REMOTE_RUN_SEED=0
if [ "${RUN_SEED_REVIEWS:-0}" = "1" ] && [ "$SEED_DONE" -eq 0 ]; then
  REMOTE_RUN_SEED=1
  SEED_DONE=1
fi

# ===== PM2 DEPLOY ON EC2 =====
echo "🚀 Starting PM2 zero-downtime reload..."
$SSH "bash -s" << ENDSSH
set -e
cd $REMOTE_DIR

# Ensure pip can use temp dirs (minimal cleanup every deploy; cheap on healthy disks)
DISK_NOW=\$(df / --output=pcent | tail -1 | tr -d ' %')
if [ "\${DISK_NOW:-0}" -ge 85 ]; then
  echo "⚠️  Disk \${DISK_NOW}% — pruning caches before pip..."
  find /home/ubuntu/app -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
  find /home/ubuntu/app -type f -name "*.log" -size +50M 2>/dev/null | while read -r f; do : > "\$f" || true; done
  rm -rf "\$HOME/.cache/pip" 2>/dev/null || true
  sudo journalctl --vacuum-size=50M 2>/dev/null || true
  sudo mysql -e "PURGE BINARY LOGS BEFORE NOW() - INTERVAL 1 HOUR;" 2>/dev/null || true
fi

export TMPDIR=/tmp
export PIP_NO_CACHE_DIR=1

if [ ! -f "venv/bin/activate" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
pip install --no-cache-dir -r requirements.txt

# Load environment variables for Alembic (same file PM2 uses via env_file)
if [ ! -f .env.production ]; then
  echo "❌ Missing .env.production in $REMOTE_DIR — create and manage it directly on the server."
  exit 1
fi
set -a
# shellcheck source=/dev/null
. ./.env.production
set +a
export ENV="${ENV:-production}"

# Fail fast with a clear message (common on EC2: MySQL not running, or DB_HOST still 127.0.0.1:3310 from a laptop template while nothing listens there — use RDS endpoint or start Docker MySQL on that port)
if [ "${SKIP_DB_CHECK:-0}" != "1" ]; then
  python3 << 'PY'
import os, socket, sys

host = os.environ.get("DB_HOST", "127.0.0.1")
try:
    port = int(os.environ.get("DB_PORT", "3306"))
except ValueError:
    print("ERROR: DB_PORT must be an integer.", file=sys.stderr)
    sys.exit(1)

try:
    socket.create_connection((host, port), timeout=8).close()
except OSError as e:
    print(f"ERROR: Cannot reach MySQL at {host}:{port} ({e}).", file=sys.stderr)
    print(
        "Fix: Start MySQL on the server (e.g. Docker publishing this port), or set DB_HOST/DB_PORT "
        "in .env.production to your RDS/Aurora hostname and 3306.",
        file=sys.stderr,
    )
    sys.exit(1)
PY
fi

alembic upgrade head

if [ "${REMOTE_RUN_SEED}" = "1" ]; then
  echo "🌱 Seeding trust reviews (once per deploy; shared RDS)..."
  python3 scripts/seed_trust_reviews.py --limit 8 --reviews-per 2
fi

echo "🔄 Reloading PM2 workers..."
# Install pm2 if missing, though it should be there
command -v pm2 >/dev/null 2>&1 || sudo npm install -g pm2
pm2 reload ecosystem.config.js || pm2 start ecosystem.config.js
pm2 save

# --- ADDED: Production Stability Cron Job ---
echo "⚙️  Ensuring disk-alert cron job is installed..."
# This job checks disk usage every 5 mins; if > 80%, restarts PM2 to clear memory/stuck processes
CRON_JOB="*/5 * * * * df / | awk 'NR==2 {if (\$5+0 > 80) system(\"pm2 restart makemystay-api\")}'"
(crontab -l 2>/dev/null | grep -v "pm2 restart makemystay-api"; echo "$CRON_JOB") | crontab -

# Add daily deep cleanup for logs/temp
CLEANUP_CRON="0 3 * * * sudo journalctl --vacuum-time=2d && sudo rm -rf /tmp/* && pm2 flush"
(crontab -l 2>/dev/null | grep -v "journalctl --vacuum-time"; echo "$CLEANUP_CRON") | crontab -

echo "💾 Disk after deploy: \$(df / --output=pcent | tail -1 | tr -d ' ')"
ENDSSH

# True when /api/v1/live body has {"status":"ok"} (FastAPI may omit spaces in JSON).
live_response_ok() {
  local body="$1"
  echo "$body" | grep -qE '"status"[[:space:]]*:[[:space:]]*"ok"' && return 0
  echo "$body" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("status")=="ok" else 1)' 2>/dev/null
}

echo ""
echo "🔍 Running post-deployment health check..."
echo "⏳ Waiting for workers to initialize..."
sleep 10
MAX_RETRIES=6
RETRY_DELAY=6
SUCCESS=0

set +e
for i in $(seq 1 $MAX_RETRIES); do
  echo "   Attempt $i/$MAX_RETRIES..."
  HEALTH_OUT=$(ssh -i "$PEM_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
    "$EC2_USER@$EC2_HOST" \
    'curl -sf --connect-timeout 5 --max-time 15 http://127.0.0.1:8000/api/v1/live 2>&1 || curl -sS --connect-timeout 5 --max-time 15 http://127.0.0.1:8000/api/v1/live 2>&1')
  SSH_EXIT=$?
  if [ "$SSH_EXIT" -ne 0 ]; then
    echo "⚠️  SSH failed (exit $SSH_EXIT)."
    HEALTH_OUT="ssh_error"
  elif live_response_ok "$HEALTH_OUT"; then
    echo "✅ Internal health check passed on $EC2_HOST"
    SUCCESS=1
    break
  else
    echo "⚠️  Health check attempt $i failed."
    if [ -n "$HEALTH_OUT" ]; then
      echo "--- Response ---"
      echo "$HEALTH_OUT" | tail -n 3
    fi
    if [ "$i" -lt "$MAX_RETRIES" ]; then
      echo "   Waiting ${RETRY_DELAY}s before retry..."
      sleep "$RETRY_DELAY"
    fi
  fi
done
set -e

if [ "$SUCCESS" -eq 0 ]; then
  echo "❌ All health check attempts failed for $EC2_HOST."
  echo "   PM2 status + recent API logs:"
  ssh -i "$PEM_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
    "$EC2_USER@$EC2_HOST" \
    "pm2 status; pm2 logs makemystay-api --lines 40 --nostream 2>/dev/null || true"
  exit 1
fi

echo "✅ Successfully deployed to $EC2_HOST"
done

echo "--------------------------------------------------------"
echo "✅ All-Server Backend Deployment complete!"
echo "🚀 PM2 Deploy complete — ALB liveness: /api/v1/live  |  full checks: /api/v1/health"

