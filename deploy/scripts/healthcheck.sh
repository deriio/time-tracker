#!/bin/bash
# Health check script for Time Tracker Bot

echo "=== Time Tracker Health Check ==="
echo "Time: $(date)"
echo ""

# Check services
echo "Bot Status:"
systemctl is-active timetracker-bot
echo ""

echo "Webhook Status:"
systemctl is-active timetracker-webhook
echo ""

# Check HTTP endpoint
echo "HTTP Health:"
curl -s https://YOUR_DOMAIN.com/health
echo ""

# Check photo count
echo "Photos in storage:"
ls -1 /home/botuser/time-tracker/photos/*.jpg 2>/dev/null | wc -l

# Check disk space
echo ""
echo "Disk Usage:"
df -h /home/botuser/time-tracker

# Check memory usage
echo ""
echo "Memory Usage:"
free -h

# Check last 10 log entries for errors
echo ""
echo "Recent Errors (Bot):"
journalctl -u timetracker-bot -n 10 --no-pager | grep -i error || echo "No errors found"

echo ""
echo "Recent Errors (Webhook):"
journalctl -u timetracker-webhook -n 10 --no-pager | grep -i error || echo "No errors found"
