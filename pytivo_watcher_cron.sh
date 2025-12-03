#!/bin/bash
#
# PyTivo Watcher Cron Script
# Add to crontab to run every 5 minutes:
#   */5 * * * * /usr/local/bin/pytivo_watcher_cron.sh
#

# Load environment variables from .profile (for SMTP_* variables)
if [ -f "$HOME/.profile" ]; then
    source "$HOME/.profile"
fi

# Configuration
TIVO_IP="${TIVO_IP:-192.168.1.185}"
WATCH_DIR="${WATCH_DIR:-/mnt/cloud/pytivo-watcher}"
SEQUENCE="${SEQUENCE:-watcher}"
LOG_FILE="${LOG_FILE:-/home/jtashiro/logs/pytivo-watcher-cron.log}"
LOCK_FILE="/tmp/pytivo-watcher.lock"

# Email Configuration (optional - for transfer notifications)
# Set these in $HOME/.profile or uncomment here to enable email notifications:
# export SMTP_SERVER="localhost"                       # SMTP server
# export SMTP_PORT="25"                                # SMTP port
# export SMTP_USER=""                                  # SMTP username (if auth required)
# export SMTP_PASS=""                                  # SMTP password (if auth required)
export TO_EMAIL="jtashiro@fiospace.com"              # Required for emails
export FROM_EMAIL="no-reply@fiospace.com"                 # Sender address


# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Log function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Check for lock file (prevent concurrent runs)
if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(cat "$LOCK_FILE")
    if ps -p "$LOCK_PID" > /dev/null 2>&1; then
        log "Another instance is running (PID: $LOCK_PID), exiting"
        exit 0
    else
        log "Stale lock file found, removing"
        rm -f "$LOCK_FILE"
    fi
fi

# Create lock file
echo $$ > "$LOCK_FILE"

# Cleanup function
cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# Check if watch directory has files (including symlinks)
file_count=$(find "$WATCH_DIR" -maxdepth 1 \( -type f -o -type l \) \( -iname "*.mkv" -o -iname "*.mp4" -o -iname "*.avi" -o -iname "*.m4v" \) | wc -l)

if [ "$file_count" -eq 0 ]; then
    log "No files in watch directory, exiting"
    exit 0
fi

log "Found $file_count file(s) in $WATCH_DIR"
log "Starting transfer to TiVo ($TIVO_IP) using sequence: $SEQUENCE"
log "========================================"

# Run transfer (pytivo_transfer.py is in /usr/local/bin/)
# Use unbuffered output to ensure real-time logging
python3 -u /usr/local/bin/pytivo_transfer.py "$TIVO_IP" "$SEQUENCE" 2>&1 | while IFS= read -r line; do
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $line" >> "$LOG_FILE"
done

exit_code=${PIPESTATUS[0]}

log "========================================"
if [ $exit_code -eq 0 ]; then
    log "Transfer completed successfully"
else
    log "Transfer failed with exit code: $exit_code"
fi

exit $exit_code
