#!/bin/bash
# AWS Launch Template User Data Script for MakeMyStay Backend
# This script runs automatically on every new instance launch.

set -e

# 1. Cleanup old environments & stray processes
sudo fuser -k 8000/tcp || true
sudo pm2 kill || true

# 2. Prepare Work Directory
APP_DIR="/home/ubuntu/app"
cd $APP_DIR

# 3. Pull latest code (Optional: if using git)
# git reset --hard HEAD
# git pull origin production

# 4. Initialize Virtual Environment
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt

# 5. Start Application via PM2
# We use 'ubuntu' user context for PM2 to match existing setup
sudo -u ubuntu bash -c "cd $APP_DIR && pm2 start ecosystem.config.js && pm2 save"

# 6. Setup Daily Cleanup Crons (Disk health)
CRON_JOB="0 3 * * * sudo journalctl --vacuum-time=2d && sudo rm -rf /tmp/* && pm2 flush"
(crontab -l 2>/dev/null | grep -v "journalctl --vacuum-time"; echo "$CRON_JOB") | crontab -

echo "✅ Instance Initialization Complete"
