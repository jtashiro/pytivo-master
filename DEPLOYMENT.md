# PyTivo Watcher - Installation and Setup Guide

## Deployment Options

### Option 1: Systemd Service (Recommended)
**Best for:** Continuous monitoring, automatic restarts, production use

**Advantages:**
- Runs continuously in background
- Auto-starts on boot
- Auto-restarts on failure
- Integrated with system logging (journalctl)
- Easy to start/stop/monitor

**Installation:**
```bash
# 1. Copy files to system locations
sudo cp pytivo_watcher_service.py /usr/local/bin/
sudo chmod +x /usr/local/bin/pytivo_watcher_service.py

# 2. Copy systemd unit file
sudo cp pytivo-watcher.service /etc/systemd/system/

# 3. Edit service file to match your environment
sudo nano /etc/systemd/system/pytivo-watcher.service
# Update: User, Group, TIVO_IP, WATCH_DIR, WorkingDirectory

# 4. Create log directory
sudo mkdir -p /var/log
sudo touch /var/log/pytivo-watcher.log
sudo chown jtashiro:jtashiro /var/log/pytivo-watcher.log

# 5. Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable pytivo-watcher.service
sudo systemctl start pytivo-watcher.service

# 6. Check status
sudo systemctl status pytivo-watcher.service

# 7. View logs
sudo journalctl -u pytivo-watcher.service -f
# or
tail -f /var/log/pytivo-watcher.log
```

**Management Commands:**
```bash
# Start service
sudo systemctl start pytivo-watcher

# Stop service
sudo systemctl stop pytivo-watcher

# Restart service
sudo systemctl restart pytivo-watcher

# Check status
sudo systemctl status pytivo-watcher

# View recent logs
sudo journalctl -u pytivo-watcher -n 100

# Follow logs in real-time
sudo journalctl -u pytivo-watcher -f

# Disable auto-start
sudo systemctl disable pytivo-watcher

# Enable auto-start
sudo systemctl enable pytivo-watcher
```

---

### Option 2: Cron Job (Simpler)
**Best for:** Periodic checks, simpler setup, learning/testing

**Advantages:**
- Simpler to set up
- No daemon process
- Runs only when needed
- Easy to understand and debug

**Installation:**
```bash
# 1. Copy script to system location
sudo cp pytivo_watcher_cron.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/pytivo_watcher_cron.sh

# 2. Create log directory
mkdir -p ~/logs

# 3. Test the script manually
/usr/local/bin/pytivo_watcher_cron.sh

# 4. Add to crontab
crontab -e

# Add one of these lines:
# Run every 5 minutes:
*/5 * * * * /usr/local/bin/pytivo_watcher_cron.sh

# Run every 15 minutes:
*/15 * * * * /usr/local/bin/pytivo_watcher_cron.sh

# Run every hour:
0 * * * * /usr/local/bin/pytivo_watcher_cron.sh

# Run every day at 2 AM:
0 2 * * * /usr/local/bin/pytivo_watcher_cron.sh

# 5. Verify cron entry
crontab -l

# 6. View logs
tail -f ~/logs/pytivo-watcher-cron.log
```

**Customization:**
Edit `/usr/local/bin/pytivo_watcher_cron.sh` and modify:
```bash
TIVO_IP="192.168.1.185"           # Your TiVo IP
WATCH_DIR="/mnt/cloud/pytivo-watcher"  # Directory to monitor
SEQUENCE="watcher"                 # Sequence name from tivo_navigation.txt
LOG_FILE="/home/jtashiro/logs/pytivo-watcher-cron.log"
```

---

### Option 3: Manual Run with Watch Loop
**Best for:** Testing, one-time use

```bash
# Run once
cd /usr/local/lib/python3.*/site-packages/pytivo
python3 pytivo_transfer.py 192.168.1.185 watcher

# Run in loop (simple watch)
while true; do
    python3 pytivo_transfer.py 192.168.1.185 watcher
    sleep 300  # Wait 5 minutes
done
```

---

## Configuration

### Environment Variables

**Systemd Service:**
Edit `/etc/systemd/system/pytivo-watcher.service`:
```ini
Environment="TIVO_IP=192.168.1.185"
Environment="WATCH_DIR=/mnt/cloud/pytivo-watcher"
Environment="CHECK_INTERVAL=300"      # Check every 5 minutes
Environment="MIN_FILE_AGE=60"         # Wait 60s after file modified
Environment="SEQUENCE_NAME=watcher"
```

**Cron Script:**
Edit `/usr/local/bin/pytivo_watcher_cron.sh`:
```bash
TIVO_IP="${TIVO_IP:-192.168.1.185}"
WATCH_DIR="${WATCH_DIR:-/mnt/cloud/pytivo-watcher}"
SEQUENCE="${SEQUENCE:-watcher}"
```

Or set in crontab:
```cron
TIVO_IP=192.168.1.185
WATCH_DIR=/mnt/cloud/pytivo-watcher
*/5 * * * * /usr/local/bin/pytivo_watcher_cron.sh
```

---

## Troubleshooting

### Service not starting
```bash
# Check service status
sudo systemctl status pytivo-watcher

# View full logs
sudo journalctl -u pytivo-watcher -n 100 --no-pager

# Check if files exist
ls -la /usr/local/bin/pytivo_watcher_service.py
ls -la /etc/systemd/system/pytivo-watcher.service

# Verify permissions
ls -la /var/log/pytivo-watcher.log
```

### Cron not running
```bash
# Verify cron service is running
sudo systemctl status cron

# Check crontab
crontab -l

# Check system log for cron errors
grep CRON /var/log/syslog

# Test script manually
bash -x /usr/local/bin/pytivo_watcher_cron.sh
```

### Transfer not working
```bash
# Test connection to TiVo
./check_tivo_rpc.py 192.168.1.185

# Run transfer manually with verbose output
cd /usr/local/lib/python3.*/site-packages/pytivo
python3 pytivo_transfer.py 192.168.1.185 watcher

# Check watch directory
ls -la /mnt/cloud/pytivo-watcher/

# Check pyTivo is running
ps aux | grep pytivo
```

---

## Recommendations

**For your use case (automatic monitoring and transfer):**

1. **Start with Cron** (simpler, easier to debug):
   - Install cron script
   - Set to run every 5-15 minutes
   - Monitor for a few days
   - Adjust timing as needed

2. **Upgrade to Systemd** when stable:
   - Better logging
   - Auto-restart on errors
   - Continuous monitoring
   - Professional deployment

**Typical workflow:**
1. New files arrive in `/mnt/cloud/pytivo-watcher/`
2. Cron/Service detects files (after MIN_FILE_AGE to ensure complete)
3. Runs `pytivo_transfer.py 192.168.1.185 watcher`
4. Script navigates TiVo, queues all files
5. Monitors transfers to completion
6. Deletes files from watch directory
7. Returns home on TiVo
8. Waits for next check interval

**Log monitoring:**
```bash
# Systemd
sudo journalctl -u pytivo-watcher -f

# Cron
tail -f ~/logs/pytivo-watcher-cron.log

# PyTivo logs (to see actual transfers)
tail -f /home/jtashiro/logs/pytivo.log
```
