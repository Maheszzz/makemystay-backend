#!/bin/bash
# Backup MySQL Database with a 7-day retention schedule

BACKUP_DIR="/var/backups/mysql"
DB_NAME="makemystay"
DB_USER="root"
# In a real environment, read passwords securely via SSM or secure dotfiles.
DB_PASS="${DB_PASSWORD:-makemystay_secure}"

DATE=$(date +"%Y%m%d_%H%M%S")
BACKUP_PATH="$BACKUP_DIR/$DB_NAME-$DATE.sql.gz"

echo "Starting DB backup..."
mkdir -p "$BACKUP_DIR"

if mysqldump -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" | gzip > "$BACKUP_PATH"; then
    echo "Backup completed successfully at $BACKUP_PATH"
else
    echo "Backup failed!" >&2
    exit 1
fi

echo "Rotating backups older than 7 days..."
find "$BACKUP_DIR" -type f -name "$DB_NAME-*.sql.gz" -mtime +7 -delete

echo "Done."
