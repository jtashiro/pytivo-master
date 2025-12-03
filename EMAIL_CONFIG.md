# Email Notification Configuration

The pytivo_transfer.py script can send HTML email notifications after transfers complete or fail.

## Environment Variables

Set these environment variables to enable email notifications:

### Required
- `TO_EMAIL` - Recipient email address (e.g., `user@example.com`)

### Optional
- `SMTP_SERVER` - SMTP server hostname (default: `localhost`)
- `SMTP_PORT` - SMTP server port (default: `25`)
- `SMTP_USER` - SMTP username (for authentication)
- `SMTP_PASS` - SMTP password (for authentication)
- `FROM_EMAIL` - Sender email address (default: `pytivo@localhost`)

## Examples

### Using Gmail
```bash
export SMTP_SERVER=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=your.email@gmail.com
export SMTP_PASS=your-app-password
export FROM_EMAIL=your.email@gmail.com
export TO_EMAIL=recipient@example.com
```

### Using Local Mail Server
```bash
export TO_EMAIL=admin@example.com
export FROM_EMAIL=pytivo@example.com
# SMTP_SERVER defaults to localhost:25
```

### In Cron
```cron
# Set environment variables in crontab
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your.email@gmail.com
SMTP_PASS=your-app-password
FROM_EMAIL=your.email@gmail.com
TO_EMAIL=recipient@example.com

# Run transfer
*/5 * * * * /usr/local/bin/pytivo_watcher_cron.sh
```

### In Shell Script
```bash
export SMTP_SERVER=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=your.email@gmail.com
export SMTP_PASS=your-app-password
export FROM_EMAIL=your.email@gmail.com
export TO_EMAIL=recipient@example.com

./pytivo_transfer.py 192.168.1.185 watcher
```

## Email Content

### Success Email
- Subject: `✓ PyTivo Transfer Complete - X file(s)`
- Contains:
  - TiVo IP address
  - Transfer date/time
  - Total duration
  - Table of all files with status

### Failure Email
- Subject: `✗ PyTivo Transfer Failed`
- Contains:
  - TiVo IP address
  - Date/time
  - Error message
  - List of files that were queued (if any)

## Security Notes

For Gmail, you need to:
1. Enable 2-factor authentication
2. Generate an "App Password" at https://myaccount.google.com/apppasswords
3. Use the app password (not your regular password)

For production use, consider:
- Using a dedicated email account
- Storing credentials in a secure location
- Using environment files (not in cron directly)
- Setting up a local mail relay instead of using external SMTP
