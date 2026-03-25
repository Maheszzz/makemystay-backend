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
EC2_HOST="ec2-3-110-184-129.ap-south-1.compute.amazonaws.com"
PEM_KEY="/Users/maheswaranm/Downloads/makemystayrealty.pem"
REMOTE_DIR="/home/ubuntu/app"

SSH="ssh -i $PEM_KEY -o StrictHostKeyChecking=no $EC2_USER@$EC2_HOST"

echo "💾 Checking server disk space..."
DISK_PCT=$($SSH "df / --output=pcent | tail -1 | tr -d ' %'")
echo "   Disk usage: ${DISK_PCT}%"

if [ "$DISK_PCT" -ge 85 ]; then
  echo "⚠️  Disk ≥ 85% — running auto-cleanup before deploy..."
  $SSH "bash -s" << 'CLEANUP'
    find /home/ubuntu/app/logs  -name "*.log" -mtime +7  -delete 2>/dev/null || true
    find /home/ubuntu/app       -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    sudo apt-get clean -y 2>/dev/null || true
CLEANUP
fi

# ===== UPLOAD SOURCE =====
echo "📦 Uploading source files..."
rsync -az --delete \
  --exclude='.venv' --exclude='venv' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='*.egg-info' --exclude='.DS_Store' \
  --exclude='tests/' --exclude='logs/' \
  -e "ssh -i $PEM_KEY -o StrictHostKeyChecking=no" \
  app alembic scripts alembic.ini requirements.txt .env.production ecosystem.config.js \
  $EC2_USER@$EC2_HOST:$REMOTE_DIR/ 2>/dev/null || \
  scp -i "$PEM_KEY" -o StrictHostKeyChecking=no -r \
    app alembic scripts alembic.ini requirements.txt .env.production ecosystem.config.js \
    $EC2_USER@$EC2_HOST:$REMOTE_DIR/

# ===== PM2 DEPLOY ON EC2 =====
echo "🚀 Starting PM2 zero-downtime reload..."
$SSH "bash -s" << ENDSSH
set -e
cd $REMOTE_DIR

if [ ! -f "venv/bin/activate" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt

# Load environment variables for Alembic migrations
set -a; source .env.production; set +a
alembic upgrade head

echo "🔄 Reloading PM2 workers..."
# Install pm2 if missing, though it should be there
command -v pm2 >/dev/null 2>&1 || sudo npm install -g pm2
pm2 reload ecosystem.config.js || pm2 start ecosystem.config.js
pm2 save

echo "💾 Disk after deploy: \$(df / --output=pcent | tail -1 | tr -d ' ')"
ENDSSH

echo ""
echo "✅ PM2 Deploy complete → https://api.makemystay.ai/health"
