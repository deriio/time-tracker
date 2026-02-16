🎯 Technical Deployment Plan: Time Tracker Bot → VPS Migration
📋 Executive Summary
Objective: Migrate bot from local development (Cloudflare Tunnel) to production VPS environment.

Key Requirements:

Nginx reverse proxy with SSL termination
Systemd service management
Photo storage with 5-minute TTL (Time To Live)
Zero manual intervention for cleanup
Production-grade logging and monitoring
Timeline: 2-3 hours (initial deployment)

🏗️ Architecture Overview
┌─────────────────────────────────────────────────────┐
│                   Internet (443/80)                 │
└────────────────────┬────────────────────────────────┘
                     │
              ┌──────▼──────┐
              │    Nginx    │ ← SSL Termination
              │   (Proxy)   │ ← Static /photos
              └──────┬──────┘
                     │
        ┌────────────┴────────────┐
        │                         │
   ┌────▼────┐            ┌──────▼──────┐
   │  Bot    │            │   Webhook   │
   │ (main)  │            │  (FastAPI)  │
   │  :N/A   │            │   :8000     │
   └────┬────┘            └──────┬──────┘
        │                        │
        └────────┬───────────────┘
                 │
          ┌──────▼──────┐
          │   Google    │
          │   Sheets    │
          └─────────────┘
┌─────────────────────────────────────┐
│  /photos (ephemeral, 5min TTL)      │
│  • Created by webhook_server.py     │
│  • Consumed by Telegram API         │
│  • Deleted after send OR 5min max   │
└─────────────────────────────────────┘
📐 Phase 1: Pre-Deployment Preparation
1.1 VPS Requirements Check
bash
# Minimum specs
CPU: 1 vCore
RAM: 1 GB
Disk: 10 GB SSD
OS: Ubuntu 22.04 LTS (recommended)
Network: Public IPv4 + Domain pointed to IP
Validation:

bash
# Check OS version
lsb_release -a
# Check available resources
free -h
df -h
nproc
1.2 Repository Preparation
bash
# Ensure .gitignore is correct (local machine)
cat .gitignore | grep -E '\.env|token\.json|.*\.json|photos/'
# Create deployment branch (optional)
git checkout -b production
git push origin production
1.3 Environment Variables Template
Create deploy/.env.production.template:

ini
# Bot Configuration
BOT_TOKEN=REPLACE_WITH_PRODUCTION_TOKEN
ADMIN_IDS=REPLACE_WITH_ADMIN_IDS
# Google API
GOOGLE_JSON_PATH=/home/botuser/time-tracker/credentials.json
DRIVE_FOLDER_ID=REPLACE_WITH_FOLDER_ID
TEMPLATE_FILE_ID=REPLACE_WITH_TEMPLATE_ID
# Telegram Groups
WORKSHOP_GROUP_ID=REPLACE_WITH_WORKSHOP_GROUP
OFFICE_GROUP_ID=REPLACE_WITH_OFFICE_GROUP
WORKSHOP_FOLDER_ID=REPLACE_WITH_WORKSHOP_FOLDER
OFFICE_FOLDER_ID=REPLACE_WITH_OFFICE_FOLDER
# Server URLs (WILL BE UPDATED IN PHASE 3)
WEBAPP_URL=https://deriio.github.io/time-tracker/
WEBHOOK_SERVER_URL=https://YOUR_DOMAIN_HERE
📐 Phase 2: VPS Initial Setup
2.1 Security Hardening
bash
# SSH as root
ssh root@YOUR_VPS_IP
# Update system
apt update && apt upgrade -y
# Install fail2ban
apt install -y fail2ban ufw
# Configure firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
# Verify
ufw status
2.2 User & Directory Structure
bash
# Create dedicated user
useradd -m -s /bin/bash botuser
usermod -aG sudo botuser  # Only if needed for maintenance
# Set password
passwd botuser
# Switch to botuser
su - botuser
cd ~
# Expected structure:
# /home/botuser/
# ├── time-tracker/          # Main repo
# │   ├── venv/
# │   ├── photos/            # Ephemeral storage
# │   ├── main.py
# │   ├── webhook_server.py
# │   ├── sheets_manager.py
# │   ├── .env
# │   └── credentials.json
# └── logs/                  # Separate log directory
2.3 Python Environment
bash
# Install Python 3.10+
sudo apt install -y python3.10 python3.10-venv python3-pip
# Verify
python3 --version  # Should be 3.10+
2.4 Install System Dependencies
bash
sudo apt install -y \
    nginx \
    certbot \
    python3-certbot-nginx \
    git \
    htop \
    curl \
    build-essential
📐 Phase 3: Application Deployment
3.1 Clone Repository
bash
# As botuser
cd /home/botuser
git clone https://github.com/deriio/time-tracker.git
# OR use your actual repo URL
cd time-tracker
# Verify structure
ls -la
3.2 Virtual Environment
bash
python3 -m venv venv
source venv/bin/activate
# Upgrade pip
pip install --upgrade pip
# Install dependencies
pip install -r requirements.txt
# Verify critical packages
pip list | grep -E "aiogram|fastapi|gspread|uvicorn"
3.3 Configuration Files
bash
# Copy credentials (SECURE METHOD - use SCP from local machine)
# From LOCAL machine:
scp credentials.json botuser@YOUR_VPS_IP:/home/botuser/time-tracker/
scp token.json botuser@YOUR_VPS_IP:/home/botuser/time-tracker/
scp oauth_credentials.json botuser@YOUR_VPS_IP:/home/botuser/time-tracker/
# Create .env
nano .env
# Paste production values
# Set permissions
chmod 600 .env credentials.json token.json
chown botuser:botuser .env credentials.json token.json
3.4 Photo Storage Directory
bash
mkdir -p /home/botuser/time-tracker/photos
chmod 755 /home/botuser/time-tracker/photos
# Create cleanup marker file (for tracking)
touch /home/botuser/time-tracker/photos/.gitkeep
📐 Phase 4: Enhanced Photo Cleanup Logic
4.1 Modify 
webhook_server.py
Add background cleanup task:

python
# At the top of webhook_server.py, after imports
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
# Photo cleanup configuration
PHOTO_TTL_MINUTES = 5
CLEANUP_INTERVAL_SECONDS = 60  # Run every 60 seconds
async def cleanup_old_photos():
    """Background task to delete photos older than TTL."""
    while True:
        try:
            now = datetime.now()
            cutoff = now - timedelta(minutes=PHOTO_TTL_MINUTES)
            
            deleted_count = 0
            for photo_path in PHOTOS_DIR.glob("*.jpg"):
                # Get file modification time
                mtime = datetime.fromtimestamp(photo_path.stat().st_mtime)
                
                if mtime < cutoff:
                    photo_path.unlink()
                    deleted_count += 1
                    logger.debug(f"Auto-deleted expired photo: {photo_path.name}")
            
            if deleted_count > 0:
                logger.info(f"Cleanup cycle: Removed {deleted_count} expired photo(s)")
                
        except Exception as e:
            logger.error(f"Photo cleanup error: {e}")
        
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
# Add startup event
@app.on_event("startup")
async def startup_event():
    """Start background tasks on server startup."""
    asyncio.create_task(cleanup_old_photos())
    logger.info(f"Photo cleanup task started (TTL: {PHOTO_TTL_MINUTES} min)")
Alternative: Immediate deletion after successful send

Modify the /api/delete endpoint to be called automatically:

python
# In main.py, after successful photo send:
async def process_web_check(message: Message, data: dict, user_id: int):
    # ... existing code ...
    
    try:
        await message.bot.send_photo(...)
        
        # ✅ IMMEDIATE CLEANUP
        if photo_filename and WEBHOOK_SERVER_URL:
            async with httpx.AsyncClient() as client:
                try:
                    await client.delete(
                        f"{WEBHOOK_SERVER_URL.rstrip('/')}/api/photos/{photo_filename}",
                        timeout=5.0
                    )
                    logger.info(f"Photo cleaned up: {photo_filename}")
                except Exception as e:
                    logger.warning(f"Failed to delete photo {photo_filename}: {e}")
    except Exception as e_photo:
        logger.error(f"Report delivery failed: {e_photo}")
4.2 Update Requirements
bash
# Add to requirements.txt if not present
echo "apscheduler==3.10.4" >> requirements.txt  # Optional: for advanced scheduling
📐 Phase 5: Nginx Configuration
5.1 Create Nginx Config
bash
sudo nano /etc/nginx/sites-available/timetracker
Content:

nginx
# Upstream for FastAPI backend
upstream webhook_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}
server {
    server_name YOUR_DOMAIN.com;  # REPLACE
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Client body size (for photo uploads)
    client_max_body_size 10M;
    
    # API endpoints
    location /api {
        proxy_pass http://webhook_backend;
        proxy_http_version 1.1;
        
        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Telegram-Init-Data $http_x_telegram_init_data;
        proxy_set_header Bypass-Tunnel-Reminder $http_bypass_tunnel_reminder;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Connection reuse
        proxy_set_header Connection "";
    }
    
    # Photo static files (ephemeral)
    location /photos {
        alias /home/botuser/time-tracker/photos;
        
        # Cache control (very short since photos are temporary)
        expires 5m;
        add_header Cache-Control "public, max-age=300";
        
        # Security: prevent directory listing
        autoindex off;
        
        # CORS for Telegram WebApp
        add_header Access-Control-Allow-Origin "*";
    }
    
    # Health check endpoint
    location /health {
        access_log off;
        return 200 "OK\n";
        add_header Content-Type text/plain;
    }
    
    # Root (optional - can serve static landing page)
    location / {
        return 301 https://deriio.github.io/time-tracker/;
    }
    
    # Logging
    access_log /var/log/nginx/timetracker_access.log;
    error_log /var/log/nginx/timetracker_error.log;
    
    listen 80;
}
5.2 Enable Site
bash
# Test config
sudo nginx -t
# Create symlink
sudo ln -s /etc/nginx/sites-available/timetracker /etc/nginx/sites-enabled/
# Remove default site (optional)
sudo rm /etc/nginx/sites-enabled/default
# Reload
sudo systemctl reload nginx
5.3 SSL Certificate
bash
# Request certificate
sudo certbot --nginx -d YOUR_DOMAIN.com
# Verify auto-renewal
sudo certbot renew --dry-run
# Check certificate
curl https://YOUR_DOMAIN.com/health
📐 Phase 6: Systemd Services
6.1 Bot Service
bash
sudo nano /etc/systemd/system/timetracker-bot.service
Content:

ini
[Unit]
Description=Time Tracker Telegram Bot
After=network.target
Wants=network-online.target
[Service]
Type=simple
User=botuser
Group=botuser
WorkingDirectory=/home/botuser/time-tracker
# Environment
Environment="PATH=/home/botuser/time-tracker/venv/bin:/usr/bin"
EnvironmentFile=/home/botuser/time-tracker/.env
# Execution
ExecStart=/home/botuser/time-tracker/venv/bin/python main.py
# Restart policy
Restart=always
RestartSec=10
StartLimitInterval=200
StartLimitBurst=5
# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=timetracker-bot
# Security
NoNewPrivileges=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
6.2 Webhook Service
bash
sudo nano /etc/systemd/system/timetracker-webhook.service
Content:

ini
[Unit]
Description=Time Tracker Webhook Server (FastAPI)
After=network.target
Wants=network-online.target
[Service]
Type=simple
User=botuser
Group=botuser
WorkingDirectory=/home/botuser/time-tracker
# Environment
Environment="PATH=/home/botuser/time-tracker/venv/bin:/usr/bin"
EnvironmentFile=/home/botuser/time-tracker/.env
# Execution (Production settings)
ExecStart=/home/botuser/time-tracker/venv/bin/uvicorn webhook_server:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 2 \
    --log-level info \
    --no-access-log
# Restart policy
Restart=always
RestartSec=10
StartLimitInterval=200
StartLimitBurst=5
# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=timetracker-webhook
# Security
NoNewPrivileges=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
6.3 Enable & Start Services
bash
# Reload systemd
sudo systemctl daemon-reload
# Enable services (start on boot)
sudo systemctl enable timetracker-bot
sudo systemctl enable timetracker-webhook
# Start services
sudo systemctl start timetracker-webhook
sleep 5
sudo systemctl start timetracker-bot
# Verify status
sudo systemctl status timetracker-webhook
sudo systemctl status timetracker-bot
# Check if listening
sudo netstat -tlnp | grep 8000
📐 Phase 7: Update Frontend (GitHub Pages)
7.1 Update WEBAPP_URL References
bash
# Update .env on VPS
nano /home/botuser/time-tracker/.env
# Change:
WEBHOOK_SERVER_URL=https://YOUR_DOMAIN.com
7.2 Restart Services
bash
sudo systemctl restart timetracker-bot timetracker-webhook
7.3 Test WebApp Flow
bash
# From Telegram:
1. /start
2. Click "Сделать отчет"
3. Take photo
4. Submit
# Monitor logs:
sudo journalctl -u timetracker-webhook -f
📐 Phase 8: Monitoring & Maintenance
8.1 Log Management
bash
# View real-time logs
sudo journalctl -u timetracker-bot -f
sudo journalctl -u timetracker-webhook -f
# View last 100 lines
sudo journalctl -u timetracker-bot -n 100
# Search for errors
sudo journalctl -u timetracker-webhook | grep ERROR
# Log rotation (automatic with systemd)
sudo journalctl --vacuum-time=7d  # Keep 7 days
8.2 Health Monitoring Script
bash
# Create monitoring script
nano /home/botuser/healthcheck.sh
Content:

bash
#!/bin/bash
# Health check script
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
bash
chmod +x /home/botuser/healthcheck.sh
# Run manually
./healthcheck.sh
# Add to crontab (optional)
crontab -e
# Add: */15 * * * * /home/botuser/healthcheck.sh >> /home/botuser/logs/health.log 2>&1
8.3 Backup Strategy
bash
# Create backup script
nano /home/botuser/backup.sh
Content:

bash
#!/bin/bash
BACKUP_DIR="/home/botuser/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
# Backup sensitive files
tar -czf $BACKUP_DIR/time-tracker-$DATE.tar.gz \
    /home/botuser/time-tracker/.env \
    /home/botuser/time-tracker/credentials.json \
    /home/botuser/time-tracker/token.json
# Keep only last 7 backups
ls -t $BACKUP_DIR/*.tar.gz | tail -n +8 | xargs rm -f
bash
chmod +x backup.sh
# Schedule daily backup
crontab -e
# Add: 0 3 * * * /home/botuser/backup.sh
📐 Phase 9: Testing & Validation
9.1 Smoke Tests
bash
# Test checklist:
✓ Bot responds to /start
✓ /setup_checkin generates terminal button
✓ WebApp loads correctly
✓ Photo upload works
✓ Check-in sends message to correct group
✓ Photo appears in /photos (temporarily)
✓ Photo auto-deletes after 5 minutes
✓ Logs written to Google Sheets
9.2 Performance Testing
bash
# Monitor resource usage during peak
htop
# Check response times
curl -o /dev/null -s -w "%{time_total}\n" https://YOUR_DOMAIN.com/api/config
📐 Phase 10: Rollback Plan
10.1 Emergency Rollback
bash
# Stop services
sudo systemctl stop timetracker-bot timetracker-webhook
# Revert to Cloudflare Tunnel (local)
# Update .env on local machine:
WEBHOOK_SERVER_URL=https://your-cloudflare-url.trycloudflare.com
# Restart local setup
python main.py
python webhook_server.py
10.2 Common Issues & Fixes
Issue	Diagnosis	Fix
Bot not responding	systemctl status timetracker-bot	Check logs, verify BOT_TOKEN
502 Bad Gateway	curl localhost:8000/health	Restart webhook service
Photos not loading	Check /photos permissions	chmod 755 photos/
SSL errors	certbot certificates	Renew certificate
🎯 Success Criteria
 Both services running (systemctl status)
 HTTPS accessible (curl https://domain.com/health)
 Bot responds in Telegram
 WebApp loads without errors
 Photo upload + check-in workflow completes
 Photos auto-delete after 5 minutes
 Google Sheets logging works
 No errors in logs for 1 hour
📊 Final Checklist
bash
# Run this final verification:
sudo systemctl status timetracker-bot timetracker-webhook
sudo journalctl -u timetracker-webhook --since "10 minutes ago" | grep ERROR
ls -lh /home/botuser/time-tracker/photos/
curl -I https://YOUR_DOMAIN.com/health
Estimated Total Time: 2-3 hours
Downtime: 0 minutes (if Cloudflare kept running during setup)

Готов начинать реализацию? Скажи, и я подготовлю файлы для автоматизации (например, deployment script).