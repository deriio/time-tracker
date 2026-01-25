#!/bin/bash
# Automated deployment script for Time Tracker Bot on VPS
# This script automates the deployment process described in Technical Deployment plan.md

set -e  # Exit on error

echo "=========================================="
echo "Time Tracker Bot - VPS Deployment Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# Check if running as botuser
if [ "$USER" != "botuser" ]; then
    print_error "This script must be run as 'botuser'"
    echo "Please run: su - botuser"
    exit 1
fi

# Navigate to home directory
cd /home/botuser

print_info "Step 1: Cloning repository..."
if [ -d "time-tracker" ]; then
    print_info "Repository already exists. Pulling latest changes..."
    cd time-tracker
    git pull
else
    git clone https://github.com/deriio/time-tracker.git
    cd time-tracker
fi
print_success "Repository ready"

print_info "Step 2: Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_success "Virtual environment created"
else
    print_info "Virtual environment already exists"
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
print_success "Dependencies installed"

print_info "Step 3: Creating photos directory..."
mkdir -p photos
chmod 755 photos
touch photos/.gitkeep
print_success "Photos directory ready"

print_info "Step 4: Checking configuration files..."
if [ ! -f ".env" ]; then
    print_error ".env file not found!"
    echo "Please create .env file with production values"
    echo "Template available at: deploy/.env.production.template"
    exit 1
fi

if [ ! -f "credentials.json" ]; then
    print_error "credentials.json not found!"
    echo "Please upload credentials.json using: scp credentials.json botuser@YOUR_VPS_IP:/home/botuser/time-tracker/"
    exit 1
fi

# Set proper permissions
chmod 600 .env credentials.json
if [ -f "token.json" ]; then
    chmod 600 token.json
fi
if [ -f "oauth_credentials.json" ]; then
    chmod 600 oauth_credentials.json
fi
print_success "Configuration files secured"

print_info "Step 5: Installing systemd services..."
sudo cp deploy/systemd/timetracker-bot.service /etc/systemd/system/
sudo cp deploy/systemd/timetracker-webhook.service /etc/systemd/system/
sudo systemctl daemon-reload
print_success "Systemd services installed"

print_info "Step 6: Enabling services..."
sudo systemctl enable timetracker-bot
sudo systemctl enable timetracker-webhook
print_success "Services enabled for auto-start"

print_info "Step 7: Starting services..."
sudo systemctl start timetracker-webhook
sleep 3
sudo systemctl start timetracker-bot
sleep 2
print_success "Services started"

print_info "Step 8: Checking service status..."
if systemctl is-active --quiet timetracker-webhook; then
    print_success "Webhook service is running"
else
    print_error "Webhook service failed to start"
    sudo journalctl -u timetracker-webhook -n 20 --no-pager
    exit 1
fi

if systemctl is-active --quiet timetracker-bot; then
    print_success "Bot service is running"
else
    print_error "Bot service failed to start"
    sudo journalctl -u timetracker-bot -n 20 --no-pager
    exit 1
fi

print_info "Step 9: Setting up monitoring scripts..."
chmod +x deploy/scripts/healthcheck.sh
chmod +x deploy/scripts/backup.sh
print_success "Monitoring scripts ready"

echo ""
echo "=========================================="
print_success "Deployment completed successfully!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Configure Nginx (see deploy/nginx/timetracker.conf)"
echo "2. Set up SSL with certbot"
echo "3. Update WEBHOOK_SERVER_URL in .env with your domain"
echo "4. Restart services: sudo systemctl restart timetracker-bot timetracker-webhook"
echo ""
echo "Useful commands:"
echo "  - View bot logs:     sudo journalctl -u timetracker-bot -f"
echo "  - View webhook logs: sudo journalctl -u timetracker-webhook -f"
echo "  - Restart bot:       sudo systemctl restart timetracker-bot"
echo "  - Restart webhook:   sudo systemctl restart timetracker-webhook"
echo "  - Health check:      ./deploy/scripts/healthcheck.sh"
echo ""
