#!/bin/bash
set -e

# ===== CONFIG =====
APP_NAME="app"
EC2_USER="ubuntu"
EC2_HOST="ec2-3-110-184-129.ap-south-1.compute.amazonaws.com"
PEM_KEY="/Users/maheswaranm/Downloads/makemystayrealty.pem"

REMOTE_DIR="/home/ubuntu/app"
VENV_DIR="$REMOTE_DIR/venv"

APP_MODULE="app.main:app"
PORT=8000

SSH="ssh -i $PEM_KEY -o StrictHostKeyChecking=no $EC2_USER@$EC2_HOST"

# ===== DISK SPACE CHECK =====
echo "💾 Checking server disk space..."
DISK_PCT=$($SSH "df / --output=pcent | tail -1 | tr -d ' %'")
echo "   Disk usage: ${DISK_PCT}%"

if [ "$DISK_PCT" -ge 90 ]; then
  echo "⚠️  Disk above 90% — running cleanup before deploy..."
  $SSH "bash -s" << 'CLEANUP'
    # Remove old logs older than 7 days
    find /home/ubuntu/app/logs -name "*.log" -mtime +7 -delete 2>/dev/null || true
    find /home/ubuntu/app/logs -name "*.zip" -mtime +7 -delete 2>/dev/null || true
    # Remove Python cache
    find /home/ubuntu/app -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find /home/ubuntu/app -name "*.pyc" -delete 2>/dev/null || true
    # Remove generated receipts older than 30 days
    find /home/ubuntu/app/receipts -name "*.pdf" -mtime +30 -delete 2>/dev/null || true
    # APT cache
    sudo apt-get clean -y 2>/dev/null || true
    echo "   Disk after cleanup: $(df / --output=pcent | tail -1 | tr -d ' ')"
CLEANUP
fi

# ===== CLEANUP & PREPARE =====
echo "🧹 Cleaning up old deployment..."
$SSH "mkdir -p $REMOTE_DIR && cd $REMOTE_DIR && rm -rf app dist build *.spec"

# ===== UPLOAD SOURCE =====
echo "📦 Uploading source files..."
scp -i "$PEM_KEY" -o StrictHostKeyChecking=no -r \
  app \
  alembic \
  alembic.ini \
  requirements.txt \
  .env.production \
  $EC2_USER@$EC2_HOST:$REMOTE_DIR/

# ===== SETUP & RUN ON EC2 =====
echo "🚀 Setting up & running FastAPI on EC2..."
$SSH "bash -s" << ENDSSH
set -e

LOCK_FILE="/tmp/deploy.lock"
if [ -f "\$LOCK_FILE" ]; then
  echo "❌ Deploy already running on server!"
  exit 1
fi
touch "\$LOCK_FILE"
trap "rm -f \"\$LOCK_FILE\"" EXIT

cd $REMOTE_DIR

echo "🔧 Installing system packages..."
sudo apt-get update -y -q
sudo apt-get install -y -q python3 python3-venv python3-pip \
  libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info

echo "🐍 Creating venv (if missing)..."
[ -d "$VENV_DIR" ] || python3 -m venv venv

source venv/bin/activate

echo "📦 Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "♻️ Stopping existing app..."
pkill -f "uvicorn $APP_MODULE" || true
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
sleep 2

echo "🌱 Loading production envs..."
set -a; source .env.production; set +a

echo "🗄️  Running database migrations..."
alembic upgrade head

echo "▶️ Starting FastAPI..."
nohup uvicorn $APP_MODULE \
  --host 0.0.0.0 \
  --port $PORT \
  --workers 2 \
  --log-level info \
  > app.log 2>&1 &

APP_PID=\$!
echo "   PID: \$APP_PID"

sleep 2
if ! ps -p \$APP_PID > /dev/null; then
  echo "❌ Uvicorn crashed immediately. Last logs:"
  tail -30 app.log
  exit 1
fi

echo "⏳ Waiting for app to be ready..."
for i in \$(seq 1 20); do
  sleep 1
  if curl -sf http://localhost:$PORT/health > /dev/null 2>&1; then
    echo "✅ App is healthy (attempt \$i)"
    break
  fi
  if [ \$i -eq 20 ]; then
    echo "❌ App failed to start after 20 seconds. Last logs:"
    tail -30 app.log
    exit 1
  fi
  echo "   Waiting... (\$i/20)"
done

echo ""
echo "📋 Last 10 log lines:"
tail -10 app.log

echo ""
DISK_AFTER=\$(df / --output=pcent | tail -1 | tr -d ' ')
echo "💾 Disk usage after deploy: \$DISK_AFTER"
ENDSSH

echo ""
echo "✅ Deploy complete — https://api.makemystay.ai/health"
