#!/bin/bash
set -e

# Redirect output to log file for debugging
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "Updating system and installing Docker..."
apt-get update -y
apt-get install -y docker.io awscli

echo "Starting Docker..."
systemctl start docker
systemctl enable docker

echo "Updating system and installing Nginx..."
apt-get update -y
apt-get install -y nginx awscli

echo "Configuring Nginx for Frontend and API Proxy..."
# Create directory for frontend
mkdir -p /var/www/react-app
chown -R ubuntu:ubuntu /var/www/react-app

# Write Nginx configuration
cat > /etc/nginx/sites-available/makemystay << 'EOF_NGINX'
server {
    listen 80;
    server_name _; 

    root /var/www/react-app;
    index index.html;

    # Proxy /api/* to FastAPI backend (Docker container on port 8000)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SPA routing — all other routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF_NGINX

# Enable the site and clean up defaults
ln -sf /etc/nginx/sites-available/makemystay /etc/nginx/sites-enabled/makemystay
rm -f /etc/nginx/sites-enabled/default
rm -f /etc/nginx/sites-enabled/makemystay-admin
rm -f /etc/nginx/sites-enabled/makemystay-api

# Restart Nginx
nginx -t && systemctl restart nginx

# Variables
AWS_REGION="ap-south-1"
ECR_REPO="614399201534.dkr.ecr.ap-south-1.amazonaws.com/makemystay-backend"

echo "Authenticating to ECR..."
# Ensure the EC2 instance has an IAM role with AmazonEC2ContainerRegistryReadOnly!
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPO

echo "Pulling latest backend image..."
docker pull $ECR_REPO:latest

echo "Cleaning up existing container if it exists..."
docker stop backend || true
docker rm backend || true

echo "Starting backend container in --network host mode..."
# Mapping to host network ensures FastAPI on 8000 is accessible to Host Nginx or ALB
docker run -d \
  --name backend \
  --restart always \
  --network host \
  --env-file /home/ubuntu/app/.env.production \
  $ECR_REPO:latest

echo "UserData script execution complete!"
