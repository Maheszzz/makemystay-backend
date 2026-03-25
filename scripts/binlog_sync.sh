#!/bin/bash
# Sync MySQL binary logs to S3
# Run this every 5 minutes via crontab

# Load environment variables
ENV_FILE="/home/ubuntu/app/.env.production"
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
else
    echo "Error: .env.production not found at $ENV_FILE" >&2
    exit 1
fi

LOCAL_BINLOG_DIR="/var/log/mysql"
S3_BINLOG_PATH="s3://$S3_BUCKET_NAME/binlogs"

echo "Syncing binary logs to $S3_BINLOG_PATH..."

# Use sudo -E to preserve environment variables (AWS_ACCESS_KEY_ID, etc.)
if sudo -E aws s3 sync "$LOCAL_BINLOG_DIR" "$S3_BINLOG_PATH" --exclude "*" --include "mysql-bin.*"; then
    echo "Binlog sync successful."
else
    echo "Binlog sync failed!" >&2
    exit 1
fi
