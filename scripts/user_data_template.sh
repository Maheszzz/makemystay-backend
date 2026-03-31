#!/bin/bash
set -e

# AWS HA: Robust User Data Script for Auto Scaling Group Instances
# Redirect all output to a custom log file for easy debugging
exec > >(tee /var/log/user-data-setup.log | logger -t user-data -s 2>/dev/console) 2>&1

echo "[$(date)] Starting AWS HA User Data execution..."

# 1. Self-Healing Phase: Wait for apt/dpkg locks to be released
# Common cause of timeouts on fresh Ubuntu AMIs: unattended-upgrades locking apt on boot
while fuser /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock >/dev/null 2>&1; do
    echo "[$(date)] Waiting for other package managers (unattended-upgrades) to finish..."
    sleep 5
done

# 2. System Dependencies
echo "[$(date)] Installing base system dependencies..."
apt-get update
apt-get install -y python3-pip python3-venv awscli jq curl
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs
npm install -g pm2

# 3. Source Code Retrieval Phase
# NOTE TO USER: Since your deploy.sh uses rsync from local, your Launch Template 
# MUST either use an AMI that already has the code baked in, OR you must pull it here.
# Example: Pulling a deployment tarball from S3:
# echo "[$(date)] Pulling code from S3..."
# aws s3 cp s3://makemystay-artifacts/backend-latest.tar.gz /tmp/
# mkdir -p /home/ubuntu/app && tar -xzf /tmp/backend-latest.tar.gz -C /home/ubuntu/app/
# chown -R ubuntu:ubuntu /home/ubuntu/app

# 4. App Setup & PM2 Auto-start
echo "[$(date)] Configuring Application & PM2..."
su - ubuntu -c "
cd /home/ubuntu/app

# Load Production Environment Let PM2 pick up the environment
export ENV=\"production\"
if [ -f .env.production ]; then
    set -a
    source .env.production
    set +a
fi

# Ensure Python Virtual Environment is ready
if [ ! -d \"venv\" ]; then
    echo '[$(date)] Creating Python venv...'
    python3 -m venv venv
fi
source venv/bin/activate

echo '[$(date)] Installing Python dependencies...'
pip install --no-cache-dir -r requirements.txt

# Start PM2 using ecosystem file
echo '[$(date)] Starting API and Celery workers with PM2...'
pm2 reload ecosystem.config.js || pm2 start ecosystem.config.js
pm2 save
"

# 5. Enable PM2 to start on system boot
echo "[$(date)] Creating PM2 Startup Script..."
env PATH=$PATH:/usr/bin /usr/lib/node_modules/pm2/bin/pm2 startup systemd -u ubuntu --hp /home/ubuntu

echo "[$(date)] ✅ User Data execution completed successfully."
