#!/bin/bash
set -e

# Redirect output to log file for debugging
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "Updating system and installing Docker..."
apt-get update -y
apt-get install -y docker.io unzip curl jq awscli

systemctl start docker
systemctl enable docker

# Variables (Ensure these match your environment!)
AWS_REGION="ap-south-1"
# Format: 123456789012.dkr.ecr.ap-south-1.amazonaws.com/makemystay-backend
ECR_REPO_URL="614399201534.dkr.ecr.ap-south-1.amazonaws.com/makemystay-backend"

echo "Authenticating to ECR..."
# The EC2 instance MUST have an IAM role attached with AmazonEC2ContainerRegistryReadOnly permissions!
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPO_URL

echo "Pulling latest backend image..."
docker pull $ECR_REPO_URL:latest

echo "Starting backend container..."
# Run the container, mapping container port 80 to host port 80 for the ALB
docker run -d \
  --name makemystay-backend \
  --restart always \
  -p 80:80 \
  -e ENV=production \
  $ECR_REPO_URL:latest

echo "UserData script execution complete!"
