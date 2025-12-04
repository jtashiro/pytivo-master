#!/bin/bash
#
# PyTivo Watcher Cron Script
# Add to crontab to run every 5 minutes:
#   */5 * * * * /usr/local/bin/pytivo_watcher_cron.sh
#
# To set email config outside this script, create /usr/local/etc/pytivo_watcher.conf with:
#   export SMTP_SERVER=hp.local
#   export SMTP_PORT=25
#   export FROM_EMAIL=no-reply@fiospace.com
#   export TO_EMAIL=jtashiro@fiospace.com
#
# Or set in crontab:
#   SMTP_SERVER=hp.local
#   SMTP_PORT=25
#   */5 * * * * /usr/local/bin/pytivo_watcher_cron.sh

# Load external configuration if it exists
if [ -f "/usr/local/etc/pytivo_watcher.conf" ]; then
    source "/usr/local/etc/pytivo_watcher.conf"
fi

# Configuration
TIVO_IP="${TIVO_IP:-192.168.1.185}"
WATCH_DIR="${WATCH_DIR:-/mnt/cloud/pytivo-watcher}"
SEQUENCE="${SEQUENCE:-watcher}"
LOG_FILE="${LOG_FILE:-/home/jtashiro/logs/pytivo-watcher-cron.log}"
LOCK_FILE="/tmp/pytivo-watcher.lock"

# Auto-detect SHARE_NAME from pyTivo.conf by matching WATCH_DIR path
if [ -z "$SHARE_NAME" ]; then
    # Try to find share name by matching the watch directory path
    SHARE_NAME=$(python3 /usr/local/bin/pytivo_transfer.py --share-for-path "$WATCH_DIR" 2>/dev/null)
    
    # Fall back to "Watcher" if detection fails
    if [ -z "$SHARE_NAME" ]; then
        SHARE_NAME="Watcher"
    fi
fi

# Export SHARE_NAME so pytivo_transfer.py can use it
export SHARE_NAME

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Log function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Email Configuration
# NOTE: .profile/.bash_aliases are NOT reliably sourced in cron environments.
# Set email configuration directly here:

# SMTP Server Configuration
: ${SMTP_SERVER:=hp.local}              # Your SMTP server hostname/IP
: ${SMTP_PORT:=25}                      # SMTP port (25 for local relay, 587 for TLS)
: ${SMTP_USER:=}                        # SMTP username (leave empty if no auth)
: ${SMTP_PASS:=}                        # SMTP password (leave empty if no auth)

# Email Addresses
: ${FROM_EMAIL:=no-reply@fiospace.com}  # Sender email address
: ${TO_EMAIL:=jtashiro@fiospace.com}    # Recipient email address

# Ensure they are exported for pytivo_transfer.py
export TO_EMAIL
export FROM_EMAIL
export SMTP_SERVER
export SMTP_PORT
export SMTP_USER
export SMTP_PASS

log "Email Config: SMTP=$SMTP_SERVER:$SMTP_PORT FROM=$FROM_EMAIL TO=$TO_EMAIL"

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
log "Checking watch directory: $WATCH_DIR"
file_count=$(find "$WATCH_DIR" -maxdepth 1 \( -type f -o -type l \) \( -iname "*.mkv" -o -iname "*.mp4" -o -iname "*.avi" -o -iname "*.m4v" \) | wc -l)

if [ "$file_count" -eq 0 ]; then
    log "No files in $WATCH_DIR, exiting"
    exit 0
fi

log "Found $file_count file(s)"
log "Using pyTivo share: $SHARE_NAME"
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
