#!/bin/bash
# Zero-downtime blue/green deployment for FastAPI on a single EC2 instance.
#
# How it works:
#   Blue  → runs on port 8000
#   Green → runs on port 8001
#   Nginx → reverse-proxies to whichever colour is active (tracked in ACTIVE_FILE)
#
# On every deploy:
#   1. Detect currently active colour and pick the other one.
#   2. Start the new version on the inactive port.
#   3. Health-check the new version for up to 20 seconds.
#   4. Hot-reload Nginx to point at the new colour (< 1 ms, zero dropped connections).
#   5. Kill the old colour.

set -e

# ===== CONFIG =====
EC2_USER="ubuntu"
EC2_HOST="ec2-3-110-184-129.ap-south-1.compute.amazonaws.com"
PEM_KEY="/Users/maheswaranm/Downloads/makemystayrealty.pem"
REMOTE_DIR="/home/ubuntu/app"
VENV_DIR="$REMOTE_DIR/venv"
APP_MODULE="app.main:app"

BLUE_PORT=8000
GREEN_PORT=8001
NGINX_CONF="/etc/nginx/sites-available/makemystay"
ACTIVE_FILE="$REMOTE_DIR/.active_colour"   # contains "blue" or "green"

SSH="ssh -i $PEM_KEY -o StrictHostKeyChecking=no $EC2_USER@$EC2_HOST"

# ===== DISK SPACE CHECK =====
echo "💾 Checking server disk space..."
DISK_PCT=$($SSH "df / --output=pcent | tail -1 | tr -d ' %'")
echo "   Disk usage: ${DISK_PCT}%"

if [ "$DISK_PCT" -ge 85 ]; then
  echo "⚠️  Disk ≥ 85% — running auto-cleanup before deploy..."
  $SSH "bash -s" << 'CLEANUP'
    find /home/ubuntu/app/logs  -name "*.log" -mtime +7  -delete 2>/dev/null || true
    find /home/ubuntu/app/logs  -name "*.zip" -mtime +7  -delete 2>/dev/null || true
    find /home/ubuntu/app       -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find /home/ubuntu/app       -name "*.pyc" -delete 2>/dev/null || true
    find /home/ubuntu/app/receipts -name "*.pdf" -mtime +30 -delete 2>/dev/null || true
    sudo apt-get clean -y 2>/dev/null || true
    echo "   Disk after cleanup: $(df / --output=pcent | tail -1 | tr -d ' ')"
CLEANUP
fi

# ===== UPLOAD SOURCE =====
echo "📦 Uploading source files..."
# Only send application code, not test artefacts or local venvs.
rsync -az --delete \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='*.egg-info' --exclude='.DS_Store' --exclude='tests/' \
  -e "ssh -i $PEM_KEY -o StrictHostKeyChecking=no" \
  app/ alembic/ alembic.ini requirements.txt .env.production \
  $EC2_USER@$EC2_HOST:$REMOTE_DIR/ 2>/dev/null || \
  scp -i "$PEM_KEY" -o StrictHostKeyChecking=no -r \
    app alembic alembic.ini requirements.txt .env.production \
    $EC2_USER@$EC2_HOST:$REMOTE_DIR/

# ===== BLUE/GREEN DEPLOY ON EC2 =====
echo "🟢🔵 Starting zero-downtime blue/green deploy..."
$SSH "bash -s" << ENDSSH
set -e
cd $REMOTE_DIR

# --- Ensure nginx is installed ---
if ! command -v nginx >/dev/null 2>&1; then
  echo "🔧 Installing nginx..."
  sudo apt-get install -y -q nginx
fi

# --- Write the nginx config (idempotent) ---
sudo tee $NGINX_CONF > /dev/null << 'NGINX'
upstream makemystay_active {
    server 127.0.0.1:ACTIVE_PORT;
    keepalive 32;
}
server {
    listen 80;
    server_name api.makemystay.ai _;

    location / {
        proxy_pass         http://makemystay_active;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_set_header   Connection        "";
        proxy_read_timeout 60s;
        proxy_connect_timeout 5s;
    }
}
NGINX
sudo ln -sf $NGINX_CONF /etc/nginx/sites-enabled/makemystay 2>/dev/null || true
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# --- Determine active colour ---
if [ -f $ACTIVE_FILE ]; then
  ACTIVE=\$(cat $ACTIVE_FILE)
else
  ACTIVE="green"   # first deploy: nothing running yet, we'll start blue
fi

if [ "\$ACTIVE" = "blue" ]; then
  NEW_COLOUR="green"; NEW_PORT=$GREEN_PORT; OLD_PORT=$BLUE_PORT
else
  NEW_COLOUR="blue";  NEW_PORT=$BLUE_PORT;  OLD_PORT=$GREEN_PORT
fi

echo "   Active: \$ACTIVE (\$OLD_PORT) → deploying \$NEW_COLOUR (\$NEW_PORT)"

# --- Stop anything already on the new port (stale process) ---
fuser -k \${NEW_PORT}/tcp 2>/dev/null || true
sleep 1

# --- Start new colour ---
source venv/bin/activate
set -a; source .env.production; set +a
alembic upgrade head

echo "▶️  Starting \$NEW_COLOUR on port \$NEW_PORT..."
nohup uvicorn $APP_MODULE \
  --host 127.0.0.1 \
  --port \$NEW_PORT \
  --workers 2 \
  --log-level info \
  > \${NEW_COLOUR}.log 2>&1 &
NEW_PID=\$!
echo "   PID: \$NEW_PID"

# --- Health-check the new instance ---
echo "⏳ Health-checking \$NEW_COLOUR..."
for i in \$(seq 1 20); do
  sleep 1
  if curl -sf http://127.0.0.1:\${NEW_PORT}/health >/dev/null 2>&1; then
    echo "✅ \$NEW_COLOUR is healthy (took \${i}s)"
    break
  fi
  if [ \$i -eq 20 ]; then
    echo "❌ \$NEW_COLOUR failed to start. Logs:"
    tail -30 \${NEW_COLOUR}.log
    kill \$NEW_PID 2>/dev/null || true
    exit 1
  fi
  echo "   Waiting... (\$i/20)"
done

# --- Switch nginx to new colour (< 1ms, zero dropped connections) ---
sudo sed -i "s|server 127.0.0.1:[0-9]*;|server 127.0.0.1:\${NEW_PORT};|g" $NGINX_CONF
sudo nginx -t && sudo nginx -s reload
echo "🔀 Nginx reloaded → pointing to \$NEW_COLOUR (\$NEW_PORT)"

# --- Record new active colour ---
echo "\$NEW_COLOUR" > $ACTIVE_FILE

# --- Gracefully drain then stop the old colour ---
sleep 3   # allow in-flight requests to complete
fuser -k \${OLD_PORT}/tcp 2>/dev/null || true
echo "🛑 Stopped old \$ACTIVE instance on port \$OLD_PORT"

deactivate

echo ""
echo "📋 Last 10 log lines (\$NEW_COLOUR):"
tail -10 \${NEW_COLOUR}.log
echo ""
echo "💾 Disk after deploy: \$(df / --output=pcent | tail -1 | tr -d ' ')"
ENDSSH

echo ""
echo "✅ Zero-downtime deploy complete → https://api.makemystay.ai/health"
