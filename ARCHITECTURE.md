# 🏗️ Architecture Overview: VPS Deployment

## Production Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         INTERNET                                 │
│                    (HTTPS - Port 443)                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Let's Encrypt  │
                    │   SSL/TLS Cert  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │      NGINX      │
                    │  Reverse Proxy  │
                    │  + SSL Term.    │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐         ┌────▼────┐       ┌─────▼─────┐
    │  /api   │         │ /photos │       │  /health  │
    │ Proxy   │         │ Static  │       │  Monitor  │
    └────┬────┘         └────┬────┘       └───────────┘
         │                   │
         │              ┌────▼────────────────────┐
         │              │  Photos Directory       │
         │              │  /home/botuser/...      │
         │              │  • Auto-cleanup (60s)   │
         │              │  • TTL: 5 minutes       │
         │              └─────────────────────────┘
         │
    ┌────▼──────────────────────────────────────┐
    │         FastAPI Webhook Server            │
    │         (127.0.0.1:8000)                  │
    │  ┌────────────────────────────────────┐   │
    │  │  Endpoints:                        │   │
    │  │  • GET  /api/config                │   │
    │  │  • POST /api/upload                │   │
    │  │  • POST /api/checkin               │   │
    │  │  • POST /api/claim                 │   │
    │  │  • DELETE /api/photos/{filename}   │   │
    │  └────────────────────────────────────┘   │
    │                                            │
    │  Background Tasks:                         │
    │  • cleanup_old_photos() - Every 60s        │
    └────────────┬───────────────────────────────┘
                 │
    ┌────────────▼───────────────────────────────┐
    │         Telegram Bot (main.py)             │
    │  • Handles user commands                   │
    │  • Processes WebApp data                   │
    │  • Sends photos to groups                  │
    │  • Immediate photo cleanup after send      │
    └────────────┬───────────────────────────────┘
                 │
    ┌────────────▼───────────────────────────────┐
    │      Google Sheets Manager                 │
    │  • User management                         │
    │  • Attendance logging                      │
    │  • Monthly sheet creation                  │
    └────────────┬───────────────────────────────┘
                 │
         ┌───────┴────────┐
         │                │
    ┌────▼────┐     ┌─────▼──────┐
    │ Google  │     │   Google   │
    │ Sheets  │     │   Drive    │
    └─────────┘     └────────────┘
```

## Systemd Services

```
┌─────────────────────────────────────────────────┐
│              Systemd Manager                    │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │  timetracker-webhook.service              │  │
│  │  • ExecStart: uvicorn webhook_server:app │  │
│  │  • Workers: 2                             │  │
│  │  • Port: 8000 (localhost only)            │  │
│  │  • Auto-restart: always                   │  │
│  │  • Logs: journald                         │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │  timetracker-bot.service                  │  │
│  │  • ExecStart: python main.py              │  │
│  │  • Auto-restart: always                   │  │
│  │  • Logs: journald                         │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Photo Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                    Photo Lifecycle                          │
└─────────────────────────────────────────────────────────────┘

1. Upload (WebApp → /api/upload)
   ┌──────────────────────┐
   │ Photo captured       │
   │ Base64 encoded       │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ Saved to /photos/    │
   │ UUID.jpg             │
   │ Timestamp: T0        │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ Return public URL    │
   └──────────────────────┘

2. Use (Bot sends to Telegram)
   ┌──────────────────────┐
   │ Bot fetches photo    │
   │ from public URL      │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ Send to Telegram     │
   │ group/user           │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ ✅ Success?          │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ DELETE /api/photos/  │
   │ {filename}           │
   │ Timestamp: T0 + 2s   │
   └──────────────────────┘

3. Cleanup (Background Task)
   ┌──────────────────────┐
   │ Every 60 seconds     │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ Scan /photos/*.jpg   │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ Check mtime          │
   │ If > 5 min old       │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ Delete file          │
   │ Log deletion         │
   └──────────────────────┘

Timeline:
T0 ────────────────────────────────────────────────► T0 + 5min
│         │                                          │
Upload    Immediate Delete                    Background Delete
          (if successful)                      (if missed)
```

## Request Flow: Check-in/out

```
┌──────────────────────────────────────────────────────────────┐
│                  Check-in/out Flow                           │
└──────────────────────────────────────────────────────────────┘

1. User opens WebApp
   [Telegram] → [WebApp (GitHub Pages)]
                      │
                      ▼
   GET /api/config (fetch users, roles)
                      │
                      ▼
   [Display UI based on role]

2. User takes photo
   [Camera] → [Base64 encode]
                      │
                      ▼
   POST /api/upload
                      │
                      ▼
   [Save to /photos/UUID.jpg]
                      │
                      ▼
   Return: {url: "https://domain.com/photos/UUID.jpg"}

3. User submits check-in
   POST /api/checkin
   {
     photo: "base64...",
     action: "check_in",
     user_id: "123456",
     ...
   }
                      │
                      ▼
   [Verify Telegram initData]
                      │
                      ▼
   [Log to Google Sheets]
                      │
                      ▼
   [Send photo to Telegram group via Bot API]
                      │
                      ▼
   [DELETE /api/photos/UUID.jpg]
                      │
                      ▼
   Return: {ok: true}

4. WebApp receives response
   [Show success message]
   [Close WebApp]
```

## Security Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    Security Layers                          │
└─────────────────────────────────────────────────────────────┘

Layer 1: Network
├─ Firewall (UFW)
│  ├─ Allow: SSH (22)
│  ├─ Allow: HTTP (80)
│  ├─ Allow: HTTPS (443)
│  └─ Deny: All other
└─ SSL/TLS (Let's Encrypt)
   └─ HTTPS only

Layer 2: Nginx
├─ Security Headers
│  ├─ X-Frame-Options: SAMEORIGIN
│  ├─ X-Content-Type-Options: nosniff
│  └─ X-XSS-Protection: 1; mode=block
├─ Client body size limit: 10M
└─ No directory listing

Layer 3: Application
├─ Telegram initData validation (HMAC-SHA256)
├─ User authentication via cache
├─ Role-based access control
└─ Environment variables for secrets

Layer 4: System
├─ Dedicated user (botuser)
├─ File permissions (600 for .env, credentials)
├─ Systemd security (NoNewPrivileges, PrivateTmp)
└─ Automatic backups
```

## Monitoring & Maintenance

```
┌─────────────────────────────────────────────────────────────┐
│              Monitoring & Maintenance                       │
└─────────────────────────────────────────────────────────────┘

Real-time Monitoring:
├─ journalctl -u timetracker-bot -f
├─ journalctl -u timetracker-webhook -f
└─ curl https://domain.com/health

Scheduled Tasks (cron):
├─ Health Check (every 15 min)
│  └─ ./deploy/scripts/healthcheck.sh
└─ Backup (daily at 3:00 AM)
   └─ ./deploy/scripts/backup.sh

Metrics to Watch:
├─ Service status (systemctl status)
├─ Photo count in /photos/
├─ Disk usage
├─ Memory usage
└─ Error logs
```

## Deployment Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                  Deployment Workflow                        │
└─────────────────────────────────────────────────────────────┘

Local Machine                    VPS
─────────────                    ───

1. Commit changes
   git push origin main
                                 2. Pull changes
                                    git pull

                                 3. Update dependencies
                                    pip install -r requirements.txt

                                 4. Restart services
                                    systemctl restart timetracker-*

                                 5. Verify
                                    systemctl status timetracker-*
                                    curl /health

Zero-downtime deployment:
• Systemd auto-restarts on failure
• Nginx continues serving during restart
• Health check confirms success
```

## File Structure on VPS

```
/home/botuser/
├── time-tracker/              # Main repository
│   ├── venv/                  # Python virtual environment
│   ├── photos/                # Ephemeral photo storage
│   │   ├── .gitkeep          # Git placeholder
│   │   └── *.jpg             # Auto-deleted (TTL: 5min)
│   ├── deploy/                # Deployment files
│   │   ├── .env.production.template
│   │   ├── nginx/
│   │   ├── systemd/
│   │   ├── scripts/
│   │   └── README.md
│   ├── main.py               # Telegram bot
│   ├── webhook_server.py     # FastAPI server
│   ├── sheets_manager.py     # Google Sheets integration
│   ├── .env                  # Environment variables (600)
│   ├── credentials.json      # Google credentials (600)
│   ├── token.json            # OAuth token (600)
│   └── requirements.txt
├── backups/                   # Automatic backups
│   └── time-tracker-*.tar.gz # Last 7 backups
└── logs/                      # Optional log directory
    └── health.log            # Health check logs

/etc/nginx/
└── sites-available/
    └── timetracker           # Nginx config

/etc/systemd/system/
├── timetracker-bot.service
└── timetracker-webhook.service

/var/log/nginx/
├── timetracker_access.log
└── timetracker_error.log
```
