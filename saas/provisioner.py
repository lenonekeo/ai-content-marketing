"""
Provisioner — spins up and tears down customer Docker containers.

Each customer gets:
  - A Docker container named  makone-<slug>
  - A .env file at           /opt/makone/customers/<slug>/.env
  - Data volumes at          /opt/makone/customers/<slug>/data/
                             /opt/makone/customers/<slug>/logs/
                             /opt/makone/customers/<slug>/downloads/
  - An Nginx vhost at        /etc/nginx/sites-enabled/makone-<slug>.conf
    routing <slug>.<domain>  →  127.0.0.1:<port>

Requires:
  - Docker installed and running on the VPS
  - Nginx installed on the VPS
  - This process running as root (or with sudo passwordless for docker/nginx)
"""

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

# Path to the ai-content-marketing Docker image (built once, reused)
DOCKER_IMAGE = os.environ.get("MAKONE_IMAGE", "makone-app:latest")

# Root dir for all customer data on the host
CUSTOMERS_DIR = os.environ.get("CUSTOMERS_DIR", "/opt/makone/customers")

# Domain used for subdomains (e.g. makone-bi.com → customer.makone-bi.com)
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "makone-bi.com")

# Nginx sites-enabled path
NGINX_SITES = os.environ.get("NGINX_SITES", "/etc/nginx/sites-enabled")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
    logger.info(f"RUN: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def _customer_dir(slug: str) -> str:
    return os.path.join(CUSTOMERS_DIR, slug)


def _nginx_conf_path(slug: str) -> str:
    return os.path.join(NGINX_SITES, f"makone-{slug}.conf")


def _container_name(slug: str) -> str:
    return f"makone-{slug}"


# ---------------------------------------------------------------------------
# .env file builder
# ---------------------------------------------------------------------------

def _build_env_file(customer: dict, admin_password: str, openai_api_key: str) -> str:
    """Build the .env content for a customer container."""
    slug = customer["slug"]
    port = customer["port"]
    domain = f"{slug}.{BASE_DOMAIN}"

    return f"""# Auto-generated for customer: {slug}
# Created: {time.strftime("%Y-%m-%dT%H:%M:%S")}

# OpenAI (shared platform key — swap per customer if needed)
OPENAI_API_KEY={openai_api_key}
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.8

# App auth — customer sets their own password after first login
APP_USERNAME=admin
APP_PASSWORD={admin_password}

# Business info — pre-filled from onboarding form
BUSINESS_NAME={customer.get("company", "")}
BUSINESS_WEBSITE={customer.get("website", "")}
CONTACT_EMAIL={customer.get("email", "")}

# Server
APPROVAL_PORT={port}
VPS_HOST=127.0.0.1
PUBLIC_BASE_URL=https://{domain}
APPROVAL_REQUIRED=true

# Schedule (defaults — customer changes from Setup page)
POST_HOUR=9
POST_MINUTE=0
POST_DAYS=mon,wed,fri
TIMEZONE=UTC

# Social — customer connects from Setup page (left blank intentionally)
LINKEDIN_ACCESS_TOKEN=
LINKEDIN_PERSON_URN=
LINKEDIN_ORG_URN=
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
FACEBOOK_ACCESS_TOKEN=
FACEBOOK_PAGE_ID=
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
INSTAGRAM_ACCESS_TOKEN=
INSTAGRAM_ACCOUNT_ID=
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REFRESH_TOKEN=
HEYGEN_API_KEY=
HEYGEN_AVATAR_ID=
HEYGEN_VOICE_ID=
GOOGLE_API_KEY=
GOOGLE_PROJECT_ID=

# SMTP — customer configures from Setup page
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=

# Remotion
REMOTION_ENABLED=true
REMOTION_YT_STITCH=false

APP_ENV=production
"""


# ---------------------------------------------------------------------------
# Nginx vhost
# ---------------------------------------------------------------------------

def _build_nginx_conf(slug: str, port: int) -> str:
    domain = f"{slug}.{BASE_DOMAIN}"
    return f"""# Auto-generated for {domain}
server {{
    listen 80;
    server_name {domain};

    # Redirect HTTP → HTTPS (Certbot will add the SSL block)
    return 301 https://$host$request_uri;
}}

server {{
    listen 443 ssl;
    server_name {domain};

    # SSL certs managed by Certbot
    ssl_certificate     /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 256M;

    location / {{
        proxy_pass         http://127.0.0.1:{port};
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }}
}}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def provision(customer: dict, admin_password: str, openai_api_key: str) -> bool:
    """
    Provision a new customer:
    1. Create host directories
    2. Write .env
    3. Start Docker container
    4. Write Nginx config
    5. Reload Nginx
    6. Issue SSL cert (optional — skips gracefully if certbot unavailable)

    Returns True on success.
    """
    slug = customer["slug"]
    port = customer["port"]
    cdir = _customer_dir(slug)
    cname = _container_name(slug)
    domain = f"{slug}.{BASE_DOMAIN}"

    try:
        # 1. Host directories
        for sub in ("data", "logs", "downloads", "remotion_public"):
            os.makedirs(os.path.join(cdir, sub), exist_ok=True)
        logger.info(f"[{slug}] Directories created at {cdir}")

        # 2. .env file
        env_content = _build_env_file(customer, admin_password, openai_api_key)
        env_path = os.path.join(cdir, ".env")
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
        logger.info(f"[{slug}] .env written to {env_path}")

        # 3. Docker container
        _run([
            "docker", "run", "-d",
            "--name", cname,
            "--restart", "unless-stopped",
            "-p", f"127.0.0.1:{port}:{port}",
            # Mount customer data dirs so data persists across redeploys
            "-v", f"{cdir}/data:/app/data",
            "-v", f"{cdir}/logs:/app/logs",
            "-v", f"{cdir}/downloads:/app/downloads",
            "-v", f"{cdir}/remotion_public:/app/remotion/public",
            # Mount the .env (read-only from container perspective is fine)
            "-v", f"{env_path}:/app/.env:ro",
            # Override PORT inside container
            "-e", f"APPROVAL_PORT={port}",
            DOCKER_IMAGE,
        ])
        logger.info(f"[{slug}] Container '{cname}' started on port {port}")

        # 4. Nginx config
        nginx_conf = _build_nginx_conf(slug, port)
        nginx_path = _nginx_conf_path(slug)
        with open(nginx_path, "w", encoding="utf-8") as f:
            f.write(nginx_conf)
        logger.info(f"[{slug}] Nginx config written to {nginx_path}")

        # 5. Reload Nginx
        _run(["nginx", "-t"])
        _run(["systemctl", "reload", "nginx"])
        logger.info(f"[{slug}] Nginx reloaded")

        # 6. SSL cert (non-fatal if certbot not available)
        try:
            _run([
                "certbot", "--nginx",
                "-d", domain,
                "--non-interactive",
                "--agree-tos",
                "--email", os.environ.get("CERTBOT_EMAIL", customer.get("email", "")),
                "--redirect",
            ], timeout=120)
            logger.info(f"[{slug}] SSL cert issued for {domain}")
        except Exception as e:
            logger.warning(f"[{slug}] SSL cert skipped (certbot error): {e}")

        return True

    except Exception as e:
        logger.error(f"[{slug}] Provisioning failed: {e}")
        return False


def suspend(slug: str) -> bool:
    """Stop (but don't remove) the customer container."""
    try:
        _run(["docker", "stop", _container_name(slug)])
        logger.info(f"[{slug}] Container stopped (suspended)")
        return True
    except Exception as e:
        logger.error(f"[{slug}] Suspend failed: {e}")
        return False


def resume(slug: str) -> bool:
    """Restart a suspended container."""
    try:
        _run(["docker", "start", _container_name(slug)])
        logger.info(f"[{slug}] Container restarted (resumed)")
        return True
    except Exception as e:
        logger.error(f"[{slug}] Resume failed: {e}")
        return False


def deprovision(slug: str) -> bool:
    """
    Fully remove a customer:
    - Stop + remove container
    - Remove Nginx config
    - Reload Nginx
    (Host data dirs are kept for 30-day grace period — delete manually)
    """
    try:
        cname = _container_name(slug)
        _run(["docker", "stop", cname], check=False)
        _run(["docker", "rm", cname], check=False)
        logger.info(f"[{slug}] Container removed")

        nginx_path = _nginx_conf_path(slug)
        if os.path.exists(nginx_path):
            os.remove(nginx_path)
            logger.info(f"[{slug}] Nginx config removed")

        _run(["nginx", "-t"], check=False)
        _run(["systemctl", "reload", "nginx"], check=False)
        logger.info(f"[{slug}] Nginx reloaded")
        return True
    except Exception as e:
        logger.error(f"[{slug}] Deprovision failed: {e}")
        return False


def container_status(slug: str) -> str:
    """Return Docker container status string, or 'not found'."""
    try:
        r = _run(["docker", "inspect", "--format", "{{.State.Status}}", _container_name(slug)])
        return r.stdout.strip()
    except Exception:
        return "not found"


def rebuild_image(app_dir: str = "/opt/makone/app") -> bool:
    """Rebuild the shared Docker image from source (used when pushing updates)."""
    try:
        _run(["docker", "build", "-t", DOCKER_IMAGE, app_dir], timeout=600)
        logger.info("Docker image rebuilt")
        return True
    except Exception as e:
        logger.error(f"Image rebuild failed: {e}")
        return False


def rolling_restart_all() -> dict:
    """
    After a rebuild, restart every active container one by one.
    Returns {slug: "ok" | "failed"}.
    """
    from customer_store import get_all
    results = {}
    for c in get_all():
        if c.get("status") != "active":
            continue
        slug = c["slug"]
        try:
            _run(["docker", "restart", _container_name(slug)])
            results[slug] = "ok"
            logger.info(f"[{slug}] Restarted")
            time.sleep(2)  # stagger restarts
        except Exception as e:
            results[slug] = f"failed: {e}"
            logger.error(f"[{slug}] Restart failed: {e}")
    return results
