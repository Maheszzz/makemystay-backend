#!/bin/bash

# Navigate to application directory
cd /home/ubuntu/app

# Activate virtual environment
# This ensures the correct python version and dependencies are used by PM2
source venv/bin/activate

# Start the application using PM2 and save the process list
echo "🚀 Starting backend with PM2..."
pm2 start ecosystem.config.js
pm2 save

# Restart Nginx to ensure it's pointing to the fresh backend process
echo "🔄 Restarting Nginx..."
sudo systemctl restart nginx

# Success check (local)
echo "🔍 Performing local health check..."
curl -s -f http://localhost:8000/api/v1/live && echo "✅ High Availability Boot Sequence Complete!"
