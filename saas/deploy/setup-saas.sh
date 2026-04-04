#!/usr/bin/env bash
# =============================================================================
# MakOne SaaS — One-Command VPS Setup
# =============================================================================
# Run as root on a fresh Ubuntu 22.04 VPS:
#
#   curl -fsSL https://raw.githubusercontent.com/lenonekeo/ai-content-marketing/main/saas/deploy/setup-saas.sh | bash
#
# Or clone the repo and run:
#   cd /opt/makone && bash saas/deploy/setup-saas.sh
#
# Before running, create /opt/makone/saas/.env from saas/.env.example
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }
die()  { echo -e "${RED}[error]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && die "Run as root (sudo bash setup-saas.sh)"

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
log "Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    curl git nginx certbot python3-certbot-nginx \
    python3 python3-pip python3-venv \
    docker.io docker-compose

systemctl enable --now docker nginx

# ---------------------------------------------------------------------------
# 2. Directory structure
# ---------------------------------------------------------------------------
log "Creating directory structure..."
mkdir -p /opt/makone/{app,saas,customers}
mkdir -p /opt/makone/saas/data

# ---------------------------------------------------------------------------
# 3. Clone / pull app source
# ---------------------------------------------------------------------------
REPO="https://github.com/lenonekeo/ai-content-marketing.git"
if [ -d /opt/makone/app/.git ]; then
    log "Updating app source..."
    git -C /opt/makone/app pull --ff-only
else
    log "Cloning app source..."
    git clone "$REPO" /opt/makone/app
fi

# ---------------------------------------------------------------------------
# 4. Build Docker image
# ---------------------------------------------------------------------------
log "Building Docker image (this takes 3–8 minutes)..."
docker build -t makone-app:latest /opt/makone/app

# ---------------------------------------------------------------------------
# 5. SaaS control plane — Python venv + deps
# ---------------------------------------------------------------------------
log "Setting up SaaS control plane..."
cp -rn /opt/makone/app/saas/. /opt/makone/saas/ 2>/dev/null || true

if [ ! -d /opt/makone/saas/venv ]; then
    python3 -m venv /opt/makone/saas/venv
fi
/opt/makone/saas/venv/bin/pip install -q --upgrade pip
/opt/makone/saas/venv/bin/pip install -q -r /opt/makone/saas/requirements.txt

# Check .env exists
if [ ! -f /opt/makone/saas/.env ]; then
    warn ".env not found at /opt/makone/saas/.env"
    warn "Copying .env.example — EDIT IT before starting the service!"
    cp /opt/makone/saas/.env.example /opt/makone/saas/.env
fi

# Load env for domain detection
source /opt/makone/saas/.env 2>/dev/null || true
DOMAIN="${BASE_DOMAIN:-makone-bi.com}"

# ---------------------------------------------------------------------------
# 6. Nginx — SaaS control plane (HTTP only first, Certbot adds SSL)
# ---------------------------------------------------------------------------
log "Configuring Nginx for $DOMAIN..."

cat > /etc/nginx/sites-available/makone-saas.conf << NGINX
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location /.well-known/acme-challenge/ { root /var/www/html; }

    location / {
        proxy_pass         http://127.0.0.1:3000;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
        client_max_body_size 10M;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/makone-saas.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ---------------------------------------------------------------------------
# 7. SSL cert for root domain
# ---------------------------------------------------------------------------
CERTBOT_MAIL="${CERTBOT_EMAIL:-admin@${DOMAIN}}"
log "Requesting SSL certificate for $DOMAIN..."
certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" \
    --non-interactive --agree-tos --email "$CERTBOT_MAIL" --redirect \
    || warn "Certbot failed — ensure DNS A records for $DOMAIN point to this server"

# Wildcard cert for customer subdomains (requires DNS challenge — manual step)
warn "-------------------------------------------------------------------"
warn "Wildcard SSL for *.$DOMAIN requires DNS challenge (manual step)."
warn "Run: certbot certonly --manual --preferred-challenges dns -d '*.$DOMAIN'"
warn "Or use Cloudflare + certbot-dns-cloudflare plugin for automation."
warn "-------------------------------------------------------------------"

# ---------------------------------------------------------------------------
# 8. Systemd service for SaaS control plane
# ---------------------------------------------------------------------------
log "Creating systemd service..."

cat > /etc/systemd/system/makone-saas.service << SERVICE
[Unit]
Description=MakOne SaaS Control Plane
After=network.target docker.service
Requires=docker.service

[Service]
User=root
WorkingDirectory=/opt/makone/saas
EnvironmentFile=/opt/makone/saas/.env
ExecStart=/opt/makone/saas/venv/bin/gunicorn app:app \
    --bind 0.0.0.0:3000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile /opt/makone/saas/access.log \
    --error-logfile /opt/makone/saas/error.log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable makone-saas
systemctl restart makone-saas

# ---------------------------------------------------------------------------
# 9. Wildcard DNS note
# ---------------------------------------------------------------------------
log "-------------------------------------------------------------------"
log "Setup complete!"
log ""
log "  Landing page:  https://$DOMAIN"
log "  Admin panel:   https://$DOMAIN/admin"
log ""
log "Next steps:"
log "  1. Edit /opt/makone/saas/.env (set ADMIN_PASSWORD, Stripe keys)"
log "  2. Point DNS: A record for $DOMAIN → $(curl -s ifconfig.me)"
log "  3. Point DNS: A record for *.$DOMAIN → $(curl -s ifconfig.me)"
log "  4. Restart:   systemctl restart makone-saas"
log "  5. Check logs: journalctl -u makone-saas -f"
log "-------------------------------------------------------------------"
