#!/bin/bash
# Simplified PM2 based zero-downtime deployment for FastAPI
#
# On every deploy:
#   1. Sync files over rsync
#   2. Install dependencies and run migrations
#   3. Zero-downtime reload via PM2

set -e

# ===== CONFIG =====
EC2_USER="ubuntu"
# Public DNS for this instance (updates if you stop/start without Elastic IP)
EC2_HOST="ec2-43-205-233-181.ap-south-1.compute.amazonaws.com"
PEM_KEY="/Users/maheswaranm/Downloads/makemystayrealty.pem"
REMOTE_DIR="/home/ubuntu/app"

SSH="ssh -i $PEM_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=20 $EC2_USER@$EC2_HOST"

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
echo "📦 Uploading source files..."
rsync -az --delete \
  --exclude='.venv' --exclude='venv' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='*.egg-info' --exclude='.DS_Store' \
  --exclude='tests/' --exclude='logs/' \
  -e "ssh -i $PEM_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=30" \
  app alembic scripts alembic.ini requirements.txt .env.production ecosystem.config.js \
  $EC2_USER@$EC2_HOST:$REMOTE_DIR/ 2>/dev/null || \
  scp -i "$PEM_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=30 -r \
    app alembic scripts alembic.ini requirements.txt .env.production ecosystem.config.js \
    $EC2_USER@$EC2_HOST:$REMOTE_DIR/

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
  echo "❌ Missing .env.production in $REMOTE_DIR — create it on the server or rsync it with deploy."
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

echo "🔄 Reloading PM2 workers..."
# Install pm2 if missing, though it should be there
command -v pm2 >/dev/null 2>&1 || sudo npm install -g pm2
pm2 reload ecosystem.config.js || pm2 start ecosystem.config.js
pm2 save

echo "💾 Disk after deploy: \$(df / --output=pcent | tail -1 | tr -d ' ')"
ENDSSH

echo ""
echo "✅ PM2 Deploy complete — ALB liveness: /live  |  full checks: /health"
