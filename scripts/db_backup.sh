#!/bin/bash
# Backup MySQL Database with S3 Synchronization
# Retention: 7 days locally, 30 days on S3 via bucket lifecycle (if configured)

# Load environment variables
ENV_FILE="/home/ubuntu/app/.env.production"
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
else
    echo "Error: .env.production not found at $ENV_FILE" >&2
    exit 1
fi

TEMP_BACKUP_DIR="/home/ubuntu/db-backups"
DB_NAME="$DB_NAME"
DB_USER="$DB_USER"
DB_PASS="$DB_PASSWORD"
DB_HOST="$DB_HOST"
S3_PATH="s3://$S3_BUCKET_NAME/db-backups"

if [ -z "$DB_NAME" ]; then
    echo "Error: MYSQL_DB not defined in environment." >&2
    exit 1
fi

DATE=$(date +"%Y%m%d_%H%M%S")
FILENAME="$DB_NAME-$DATE.sql.gz"
BACKUP_PATH="$TEMP_BACKUP_DIR/$FILENAME"

echo "Starting DB backup for $DB_NAME on $DB_HOST..."
mkdir -p "$TEMP_BACKUP_DIR"

if mysqldump -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" | gzip > "$BACKUP_PATH"; then
    echo "Local backup completed: $BACKUP_PATH"
else
    echo "Backup failed!" >&2
    exit 1
fi

echo "Uploading to S3: $S3_PATH/$FILENAME..."
if aws s3 cp "$BACKUP_PATH" "$S3_PATH/$FILENAME"; then
    echo "S3 upload successful."
else
    echo "S3 upload failed!" >&2
fi

echo "Rotating local backups older than 7 days..."
find "$TEMP_BACKUP_DIR" -type f -name "$DB_NAME-*.sql.gz" -mtime +7 -delete

echo "Done."
