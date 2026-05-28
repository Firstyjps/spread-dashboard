#!/bin/bash
# Daily SQLite backup - run via cron:
# 0 3 * * * /home/deploy/spread-dashboard/scripts/backup_db.sh
set -e

DB_PATH="/home/deploy/spread-dashboard/backend/data/spread_dashboard.db"
BACKUP_DIR="/home/deploy/spread-dashboard/backend/data/backups"

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/spread_dashboard_$TIMESTAMP.db'"

# Keep only last 7 days.
find "$BACKUP_DIR" -name "*.db" -mtime +7 -delete

echo "Backup complete: $BACKUP_DIR/spread_dashboard_$TIMESTAMP.db"
