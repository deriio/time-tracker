#!/bin/bash
# Backup script for Time Tracker Bot sensitive files

BACKUP_DIR="/home/botuser/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

echo "Starting backup at $(date)"

# Backup sensitive files
tar -czf $BACKUP_DIR/time-tracker-$DATE.tar.gz \
    /home/botuser/time-tracker/.env \
    /home/botuser/time-tracker/credentials.json \
    /home/botuser/time-tracker/token.json \
    /home/botuser/time-tracker/oauth_credentials.json 2>/dev/null

if [ $? -eq 0 ]; then
    echo "Backup created: $BACKUP_DIR/time-tracker-$DATE.tar.gz"
else
    echo "Backup failed!"
    exit 1
fi

# Keep only last 7 backups
ls -t $BACKUP_DIR/*.tar.gz | tail -n +8 | xargs rm -f 2>/dev/null

echo "Old backups cleaned up. Keeping last 7 backups."
echo "Backup completed at $(date)"
