"""
Draft management and HTTP admin server.

Routes:
  GET  /              Dashboard (pending drafts + recent posts)
  GET  /setup         Credentials & settings form
  POST /setup         Save settings to .env
  GET  /influence     Content influence / brand guidelines form
  POST /influence     Save influence settings
  GET  /review?token  Review/edit draft before publishing
  GET  /reject?token  Reject a draft
  POST /publish?token Publish an approved (possibly edited) draft
"""

import json
import logging
import os
import secrets
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

DRAFTS_DIR = "drafts"
ENV_FILE = ".env"


# ---------------------------------------------------------------------------
# Draft helpers
# ---------------------------------------------------------------------------

def save_draft(data: dict) -> dict:
    """Save draft to disk. Adds draft_id, token, status, timestamp. Returns updated draft."""
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    draft_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    data["draft_id"] = draft_id
    data["token"] = secrets.token_urlsafe(20)
    data["status"] = "pending"
    data["timestamp"] = datetime.now().isoformat()
    path = os.path.join(DRAFTS_DIR, f"{draft_id}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Draft saved: {draft_id}")
    return data


def _find_by_token(token: str) -> dict | None:
    if not token or not os.path.exists(DRAFTS_DIR):
        return None
    for fname in os.listdir(DRAFTS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(DRAFTS_DIR, fname)
        try:
            with open(path) as f:
                d = json.load(f)
            if d.get("token") == token and d.get("status") == "pending":
                return d
        except Exception:
            pass
    return None


def _update_draft(draft: dict):
    path = os.path.join(DRAFTS_DIR, f"{draft['draft_id']}.json")
    with open(path, "w") as f:
        json.dump(draft, f, indent=2)


def _list_pending_drafts() -> list[dict]:
    if not os.path.exists(DRAFTS_DIR):
        return []
    result = []
    for fname in sorted(os.listdir(DRAFTS_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(DRAFTS_DIR, fname)) as f:
                d = json.load(f)
            if d.get("status") == "pending":
                result.append(d)
        except Exception:
            pass
    return result


# ---------------------------------------------------------------------------
# .env read/write helpers
# ---------------------------------------------------------------------------

def _read_env() -> dict:
    result = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.rstrip("\n")
                if "=" in line and not line.strip().startswith("#"):
                    key, _, val = line.partition("=")
                    result[key.strip()] = val.strip()
    return result


def _write_env(updates: dict):
    """Update specific keys in .env preserving comments and ordering."""
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            lines = f.readlines()

    updated = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated.add(key)
            else:
                new_lines.append(line if line.endswith("\n") else line + "\n")
        else:
            new_lines.append(line if line.endswith("\n") else line + "\n")

    for key, val in updates.items():
        if key not in updated:
            new_lines.append(f"{key}={val}\n")

    with open(ENV_FILE, "w") as f:
        f.writelines(new_lines)


# ---------------------------------------------------------------------------
# Recent execution log helper
# ---------------------------------------------------------------------------

def _read_recent_logs(n: int = 5) -> list[dict]:
    logs_file = "logs/posts.jsonl"
    if not os.path.exists(logs_file):
        return []
    records = []
    try:
        with open(logs_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except Exception:
        pass
    return records[-n:][::-1]


# ---------------------------------------------------------------------------
# Shared HTML components
# ---------------------------------------------------------------------------

_STYLES = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
       background: #f0f2f5; min-height: 100vh; }
nav { background: #1a1a2e; padding: 0 28px; display: flex; align-items: center;
      height: 58px; position: sticky; top: 0; z-index: 100; gap: 8px; }
.nav-brand { color: #fff; font-weight: 700; font-size: 17px; margin-right: 24px;
             white-space: nowrap; }
.nav-brand span { color: #2ecc71; }
.nav-links { display: flex; gap: 4px; }
.nav-links a { color: rgba(255,255,255,.65); text-decoration: none; padding: 7px 14px;
               border-radius: 6px; font-size: 14px; font-weight: 500; transition: all .15s; }
.nav-links a:hover, .nav-links a.active { color: #fff; background: rgba(255,255,255,.12); }
.container { max-width: 940px; margin: 0 auto; padding: 32px 20px 60px; }
h1 { font-size: 22px; color: #1a1a2e; margin-bottom: 6px; }
.subtitle { color: #888; font-size: 14px; margin-bottom: 28px; }
.card { background: #fff; border-radius: 12px; padding: 26px 28px;
        box-shadow: 0 1px 6px rgba(0,0,0,.07); margin-bottom: 20px; }
.card-title { font-size: 14px; font-weight: 700; color: #1a1a2e; text-transform: uppercase;
              letter-spacing: .6px; margin-bottom: 18px; padding-bottom: 12px;
              border-bottom: 1px solid #f0f0f0; }
.field { margin-bottom: 16px; }
label { display: block; font-weight: 600; font-size: 13px; color: #555; margin-bottom: 6px; }
.hint { font-weight: 400; color: #bbb; font-size: 12px; margin-left: 4px; }
input[type=text], input[type=password], input[type=number], select, textarea {
  width: 100%; padding: 10px 13px; border: 1px solid #e0e0e0; border-radius: 7px;
  font-size: 14px; color: #222; background: #fff; transition: border-color .2s; }
input:focus, select:focus, textarea:focus {
  outline: none; border-color: #2ecc71; box-shadow: 0 0 0 3px rgba(46,204,113,.12); }
textarea { resize: vertical; min-height: 110px; line-height: 1.6; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.btn { padding: 11px 26px; font-size: 14px; font-weight: 600; cursor: pointer;
       border: none; border-radius: 7px; transition: opacity .2s; display: inline-block;
       text-decoration: none; }
.btn:hover { opacity: .85; }
.btn-primary { background: #2ecc71; color: #fff; }
.btn-danger { background: #e74c3c; color: #fff; }
.btn-ghost { background: #f0f2f5; color: #555; }
.alert { padding: 12px 16px; border-radius: 8px; font-size: 14px; margin-bottom: 20px; }
.alert-success { background: #d5f5e3; color: #1e8449; border: 1px solid #a9dfbf; }
.alert-error { background: #fde8e8; color: #c0392b; border: 1px solid #f5b7b1; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 20px;
         font-size: 12px; font-weight: 600; }
.badge-pending { background: #fef9e7; color: #b7950b; }
.badge-ok { background: #d5f5e3; color: #1e8449; }
.badge-fail { background: #fde8e8; color: #c0392b; }
.badge-none { background: #f0f0f0; color: #888; }
.draft-row { display: flex; align-items: center; justify-content: space-between;
             padding: 14px 0; border-bottom: 1px solid #f5f5f5; gap: 12px; }
.draft-row:last-child { border-bottom: none; }
.draft-meta { font-size: 13px; color: #888; margin-top: 3px; }
.log-row { padding: 12px 0; border-bottom: 1px solid #f5f5f5; font-size: 13px; }
.log-row:last-child { border-bottom: none; }
.log-title { font-weight: 600; color: #333; margin-bottom: 4px; }
.log-detail { color: #888; }
.empty { color: #bbb; font-size: 14px; padding: 20px 0; text-align: center; }
.section-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 20px; }
@media (max-width: 620px) {
  .grid-2, .grid-3 { grid-template-columns: 1fr; }
  nav { padding: 0 16px; }
  .nav-brand { font-size: 15px; margin-right: 12px; }
  .nav-links a { padding: 6px 10px; font-size: 13px; }
}
"""


def _head(title: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — MakOne BI</title>
<style>{_STYLES}</style>
</head><body>"""


def _nav(active: str = "") -> str:
    pages = [("/", "Dashboard"), ("/setup", "Setup"), ("/influence", "Content Influence")]
    links = "".join(
        f'<a href="{href}" class="{"active" if active == href else ""}">{name}</a>'
        for href, name in pages
    )
    return f"""<nav>
  <div class="nav-brand">MakOne <span>BI</span></div>
  <div class="nav-links">{links}</div>
</nav>"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------

def _page_dashboard(alert: str = "") -> str:
    pending = _list_pending_drafts()
    recent = _read_recent_logs(5)

    drafts_html = ""
    if pending:
        for d in pending:
            ts = d.get("timestamp", "")[:19].replace("T", " ")
            theme = d.get("theme", "?").replace("_", " ").title()
            industry = d.get("industry", "?")
            token = d.get("token", "")
            from config import config
            host = config.vps_host
            port = config.approval_port
            url = f"http://{host}:{port}/review?token={token}"
            drafts_html += f"""
<div class="draft-row">
  <div>
    <strong>{theme}</strong> &nbsp;<span class="badge badge-pending">Pending</span>
    <div class="draft-meta">{industry} &nbsp;·&nbsp; {ts}</div>
  </div>
  <a href="{url}" class="btn btn-primary">Review &amp; Approve</a>
</div>"""
    else:
        drafts_html = '<p class="empty">No pending drafts</p>'

    logs_html = ""
    if recent:
        for r in recent:
            ts = r.get("timestamp", "")[:19].replace("T", " ")
            theme = r.get("theme", "?").replace("_", " ").title()
            li = r.get("linkedin", {})
            fb = r.get("facebook", {})
            li_badge = 'badge-ok">OK' if li.get("success") else 'badge-fail">FAIL'
            fb_badge = 'badge-ok">OK' if fb.get("success") else 'badge-fail">FAIL'
            media = r.get("media_used", r.get("video_type", "?"))
            logs_html += f"""
<div class="log-row">
  <div class="log-title">{theme} &nbsp;·&nbsp; {ts}
    &nbsp;<span class="badge badge-none">{media}</span>
    &nbsp;<span class="badge {li_badge}</span> LinkedIn
    &nbsp;<span class="badge {fb_badge}</span> Facebook
  </div>
  <div class="log-detail">{_esc(r.get("content_preview", "")[:100])}...</div>
</div>"""
    else:
        logs_html = '<p class="empty">No posts yet</p>'

    alert_html = f'<div class="alert alert-success">{alert}</div>' if alert else ""

    return _head("Dashboard") + _nav("/") + f"""
<div class="container">
  {alert_html}
  <h1>Dashboard</h1>
  <p class="subtitle">AI Content Marketing — MakOne Business Intelligence</p>

  <div class="card">
    <div class="card-title">Pending Approval</div>
    {drafts_html}
  </div>

  <div class="card">
    <div class="card-title">Recent Posts</div>
    {logs_html}
  </div>
</div></body></html>"""


def _page_setup(alert: str = "", alert_type: str = "success") -> str:
    env = _read_env()

    def val(key, default=""):
        return _esc(env.get(key, default))

    def masked(key):
        return "••••••••" if env.get(key) else ""

    alert_html = f'<div class="alert alert-{alert_type}">{alert}</div>' if alert else ""

    return _head("Setup") + _nav("/setup") + f"""
<div class="container">
  {alert_html}
  <h1>Setup</h1>
  <p class="subtitle">Manage credentials, API keys, and app settings.
    Leave sensitive fields blank to keep existing values.</p>

  <form method="POST" action="/setup">

    <div class="card">
      <div class="card-title">OpenAI</div>
      <div class="field">
        <label>API Key <span class="hint">leave blank to keep current</span></label>
        <input type="password" name="OPENAI_API_KEY" placeholder="{masked("OPENAI_API_KEY") or "sk-proj-..."}">
      </div>
      <div class="grid-2">
        <div class="field">
          <label>Model</label>
          <input type="text" name="OPENAI_MODEL" value="{val("OPENAI_MODEL", "gpt-4o-mini")}">
        </div>
        <div class="field">
          <label>Temperature <span class="hint">0.0 – 1.0</span></label>
          <input type="text" name="OPENAI_TEMPERATURE" value="{val("OPENAI_TEMPERATURE", "0.8")}">
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">HeyGen — Avatar Videos</div>
      <div class="field">
        <label>API Key <span class="hint">leave blank to keep current</span></label>
        <input type="password" name="HEYGEN_API_KEY" placeholder="{masked("HEYGEN_API_KEY") or "sk_V2_..."}">
      </div>
      <div class="grid-2">
        <div class="field">
          <label>Avatar ID</label>
          <input type="text" name="HEYGEN_AVATAR_ID" value="{val("HEYGEN_AVATAR_ID")}">
        </div>
        <div class="field">
          <label>Voice ID</label>
          <input type="text" name="HEYGEN_VOICE_ID" value="{val("HEYGEN_VOICE_ID")}">
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Google — Gemini Images &amp; VEO 3 Videos</div>
      <div class="field">
        <label>API Key <span class="hint">leave blank to keep current</span></label>
        <input type="password" name="GOOGLE_API_KEY" placeholder="{masked("GOOGLE_API_KEY") or "AIza..."}">
      </div>
      <div class="field">
        <label>GCP Project ID <span class="hint">optional, for Vertex AI</span></label>
        <input type="text" name="GOOGLE_PROJECT_ID" value="{val("GOOGLE_PROJECT_ID")}">
      </div>
    </div>

    <div class="card">
      <div class="card-title">LinkedIn</div>
      <div class="field">
        <label>Access Token <span class="hint">leave blank to keep current</span></label>
        <input type="password" name="LINKEDIN_ACCESS_TOKEN" placeholder="{masked("LINKEDIN_ACCESS_TOKEN") or "AQV..."}">
      </div>
      <div class="grid-2">
        <div class="field">
          <label>Person URN</label>
          <input type="text" name="LINKEDIN_PERSON_URN" value="{val("LINKEDIN_PERSON_URN")}">
        </div>
        <div class="field">
          <label>Org URN <span class="hint">optional, for company page</span></label>
          <input type="text" name="LINKEDIN_ORG_URN" value="{val("LINKEDIN_ORG_URN")}">
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Facebook</div>
      <div class="field">
        <label>Page Access Token <span class="hint">leave blank to keep current</span></label>
        <input type="password" name="FACEBOOK_ACCESS_TOKEN" placeholder="{masked("FACEBOOK_ACCESS_TOKEN") or "EAA..."}">
      </div>
      <div class="field">
        <label>Page ID</label>
        <input type="text" name="FACEBOOK_PAGE_ID" value="{val("FACEBOOK_PAGE_ID")}">
      </div>
    </div>

    <div class="card">
      <div class="card-title">Business Info</div>
      <div class="grid-2">
        <div class="field">
          <label>Business Name</label>
          <input type="text" name="BUSINESS_NAME" value="{val("BUSINESS_NAME", "MakOne Business Intelligence")}">
        </div>
        <div class="field">
          <label>Contact Email</label>
          <input type="text" name="CONTACT_EMAIL" value="{val("CONTACT_EMAIL")}">
        </div>
      </div>
      <div class="field">
        <label>Website</label>
        <input type="text" name="BUSINESS_WEBSITE" value="{val("BUSINESS_WEBSITE", "https://makone-bi.com")}">
      </div>
    </div>

    <div class="card">
      <div class="card-title">Email Notifications (Gmail SMTP)</div>
      <div class="grid-2">
        <div class="field">
          <label>Gmail Address</label>
          <input type="text" name="SMTP_USER" value="{val("SMTP_USER")}">
        </div>
        <div class="field">
          <label>App Password <span class="hint">leave blank to keep current</span></label>
          <input type="password" name="SMTP_PASSWORD" placeholder="{masked("SMTP_PASSWORD") or "xxxx xxxx xxxx xxxx"}">
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Posting Schedule</div>
      <div class="grid-2">
        <div class="field">
          <label>Post Days</label>
          <input type="text" name="POST_DAYS" value="{val("POST_DAYS", "mon,wed,fri")}"
                 placeholder="mon,wed,fri">
        </div>
        <div class="field">
          <label>Post Hour (UTC, 0–23)</label>
          <input type="number" name="POST_HOUR" value="{val("POST_HOUR", "9")}" min="0" max="23">
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Approval Workflow</div>
      <div class="grid-3">
        <div class="field">
          <label>Approval Required</label>
          <select name="APPROVAL_REQUIRED">
            <option value="true" {"selected" if env.get("APPROVAL_REQUIRED","true").lower() in ("true","1","yes") else ""}>Yes — require approval</option>
            <option value="false" {"selected" if env.get("APPROVAL_REQUIRED","true").lower() in ("false","0","no") else ""}>No — post automatically</option>
          </select>
        </div>
        <div class="field">
          <label>VPS Host / IP</label>
          <input type="text" name="VPS_HOST" value="{val("VPS_HOST", "localhost")}">
        </div>
        <div class="field">
          <label>Approval Port</label>
          <input type="number" name="APPROVAL_PORT" value="{val("APPROVAL_PORT", "8080")}">
        </div>
      </div>
    </div>

    <div class="section-actions">
      <button type="submit" class="btn btn-primary">Save Settings</button>
      <a href="/" class="btn btn-ghost">Cancel</a>
    </div>
  </form>
</div></body></html>"""


def _page_influence(alert: str = "") -> str:
    from src.influence import load as load_influence

    d = load_influence()

    def val(key):
        return _esc(d.get(key, ""))

    alert_html = f'<div class="alert alert-success">{alert}</div>' if alert else ""

    return _head("Content Influence") + _nav("/influence") + f"""
<div class="container">
  {alert_html}
  <h1>Content Influence</h1>
  <p class="subtitle">Tell the AI what to write about, who to write for, and how to sound.
    These settings are applied to every generated post.</p>

  <form method="POST" action="/influence">

    <div class="card">
      <div class="card-title">Topics &amp; Keywords</div>
      <div class="field">
        <label>Focus Topics <span class="hint">comma-separated</span></label>
        <input type="text" name="topics" value="{val("topics")}"
               placeholder="AI automation, workflow optimization, business efficiency, ROI...">
      </div>
      <div class="field">
        <label>Avoid <span class="hint">topics or phrases to never include</span></label>
        <input type="text" name="avoid" value="{val("avoid")}"
               placeholder="competitors, technical jargon, pricing details...">
      </div>
    </div>

    <div class="card">
      <div class="card-title">Audience &amp; Voice</div>
      <div class="field">
        <label>Target Audience</label>
        <input type="text" name="target_audience" value="{val("target_audience")}"
               placeholder="Business owners and operations managers at SMEs (10–200 employees) looking to scale...">
      </div>
      <div class="field">
        <label>Brand Voice &amp; Tone</label>
        <textarea name="brand_voice" placeholder="Expert but approachable. Confident without being arrogant. Practical and results-focused. Speak as a trusted advisor, not a salesperson...">{val("brand_voice")}</textarea>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Style Guidance</div>
      <div class="field">
        <label>Additional Style Notes <span class="hint">specific formatting or writing rules</span></label>
        <textarea name="style_notes" placeholder="Always open with a bold statement or surprising statistic. Use short paragraphs. End sentences with impact. Never use passive voice...">{val("style_notes")}</textarea>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Example Posts</div>
      <div class="field">
        <label>Paste example LinkedIn/Facebook posts you like
          <span class="hint">the AI will match this style</span></label>
        <textarea name="example_posts" style="min-height:200px"
                  placeholder="Paste 1–3 example posts here (separated by a blank line).&#10;&#10;The AI will study these to match your preferred style, length, and energy...">{val("example_posts")}</textarea>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Inspiration Sources</div>
      <div class="field">
        <label>Social media &amp; website URLs <span class="hint">one per line — content is fetched and cached for 24h</span></label>
        <textarea name="inspiration_urls" style="min-height:160px"
                  placeholder="https://www.facebook.com/yourbrandpage&#10;https://www.linkedin.com/company/yourbrand&#10;https://www.youtube.com/@yourchannel&#10;https://yourblog.com/articles&#10;&#10;The AI will read these pages and draw content ideas from them. Max 5 URLs used per generation.">{val("inspiration_urls")}</textarea>
      </div>
      <p style="font-size:12px;color:#aaa;margin-top:-8px">
        Supported: any public webpage, Facebook page, LinkedIn company page, YouTube channel,
        Instagram profile (public), blog, news site, competitor site, etc.
        Paywalled or login-required pages will be skipped automatically.
      </p>
    </div>

    <div class="section-actions">
      <button type="submit" class="btn btn-primary">Save Influence Settings</button>
      <a href="/" class="btn btn-ghost">Cancel</a>
    </div>
  </form>
</div></body></html>"""


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

_publish_callback = None  # set by start_approval_server

_SENSITIVE_KEYS = {
    "OPENAI_API_KEY", "HEYGEN_API_KEY", "GOOGLE_API_KEY",
    "LINKEDIN_ACCESS_TOKEN", "FACEBOOK_ACCESS_TOKEN", "SMTP_PASSWORD",
}

_SETUP_KEYS = {
    "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_TEMPERATURE",
    "HEYGEN_API_KEY", "HEYGEN_AVATAR_ID", "HEYGEN_VOICE_ID",
    "GOOGLE_API_KEY", "GOOGLE_PROJECT_ID",
    "LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN", "LINKEDIN_ORG_URN",
    "FACEBOOK_ACCESS_TOKEN", "FACEBOOK_PAGE_ID",
    "BUSINESS_NAME", "BUSINESS_WEBSITE", "CONTACT_EMAIL",
    "SMTP_USER", "SMTP_PASSWORD",
    "POST_DAYS", "POST_HOUR",
    "APPROVAL_REQUIRED", "VPS_HOST", "APPROVAL_PORT",
}


class _Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        p = urlparse(self.path)
        qs = parse_qs(p.query)
        token = qs.get("token", [None])[0]

        if p.path in ("/", ""):
            self._send(200, _page_dashboard())
        elif p.path == "/setup":
            self._send(200, _page_setup())
        elif p.path == "/influence":
            self._send(200, _page_influence())
        elif p.path == "/review":
            self._review(token)
        elif p.path == "/reject":
            self._reject(token)
        else:
            self._send(404, self._simple_page("Not found", "Page not found.", "#e74c3c"))

    def do_POST(self):
        p = urlparse(self.path)
        qs = parse_qs(p.query)
        token = qs.get("token", [None])[0]
        n = int(self.headers.get("Content-Length", 0))
        body = parse_qs(self.rfile.read(n).decode("utf-8", errors="replace"))

        if p.path == "/setup":
            self._save_setup(body)
        elif p.path == "/influence":
            self._save_influence(body)
        elif p.path == "/publish":
            li = body.get("linkedin_text", [""])[0]
            fb = body.get("facebook_text", [""])[0]
            self._publish(token, li, fb)
        else:
            self._send(404, self._simple_page("Not found", "Page not found.", "#e74c3c"))

    # ------------------------------------------------------------------
    # Admin handlers
    # ------------------------------------------------------------------

    def _save_setup(self, body: dict):
        env = _read_env()
        updates = {}
        for key in _SETUP_KEYS:
            form_val = body.get(key, [""])[0].strip()
            if form_val:
                # Non-empty submission — update
                updates[key] = form_val
            elif key in _SENSITIVE_KEYS:
                # Blank sensitive field = keep existing (don't touch)
                pass
            else:
                # Non-sensitive blank = update to blank (allow clearing)
                updates[key] = form_val

        _write_env(updates)
        logger.info(f"Settings updated: {[k for k in updates if k not in _SENSITIVE_KEYS]}")
        self._send(200, _page_setup(alert="Settings saved successfully. Restart the service for changes to take effect.", alert_type="success"))

    def _save_influence(self, body: dict):
        from src.influence import save as save_influence
        data = {
            "topics": body.get("topics", [""])[0],
            "target_audience": body.get("target_audience", [""])[0],
            "brand_voice": body.get("brand_voice", [""])[0],
            "style_notes": body.get("style_notes", [""])[0],
            "example_posts": body.get("example_posts", [""])[0],
            "avoid": body.get("avoid", [""])[0],
            "inspiration_urls": body.get("inspiration_urls", [""])[0],
        }
        save_influence(data)
        logger.info("Influence settings saved")
        self._send(200, _page_influence(alert="Content influence settings saved. Next generated post will use these guidelines."))

    # ------------------------------------------------------------------
    # Draft review handlers
    # ------------------------------------------------------------------

    def _review(self, token):
        d = _find_by_token(token)
        if not d:
            self._send(404, self._simple_page("Draft not found", "This draft was not found or has already been processed.", "#e74c3c"))
            return

        li = _esc(d.get("linkedin_text", ""))
        fb = _esc(d.get("facebook_text", ""))
        ts = d.get("timestamp", "")[:19].replace("T", " ")

        html = _head(f"Review — {d.get('theme','').replace('_',' ').title()}") + _nav() + f"""
<div class="container" style="max-width:760px">
  <h1>Review Draft Post</h1>
  <p class="subtitle">
    <span class="badge badge-none">{d.get("theme","?").replace("_"," ").title()}</span>
    &nbsp;{d.get("industry","?")} &nbsp;·&nbsp; {ts}
  </p>

  <div class="card">
    <form method="POST" action="/publish?token={token}">
      <div class="field">
        <label>LinkedIn Post <span class="hint">editable — changes will be published as-is</span></label>
        <textarea name="linkedin_text" style="min-height:220px">{li}</textarea>
      </div>
      <div class="field" style="margin-top:20px">
        <label>Facebook Post <span class="hint">editable</span></label>
        <textarea name="facebook_text" style="min-height:220px">{fb}</textarea>
      </div>
      <div class="section-actions">
        <button type="submit" class="btn btn-primary">Publish Now</button>
        <a href="/" class="btn btn-ghost">Back to Dashboard</a>
      </div>
    </form>
  </div>

  <div class="card" style="margin-top:0">
    <form method="GET" action="/reject">
      <input type="hidden" name="token" value="{token}">
      <button type="submit" class="btn btn-danger">Reject &amp; Discard</button>
    </form>
  </div>
</div></body></html>"""
        self._send(200, html)

    def _publish(self, token, li_text, fb_text):
        d = _find_by_token(token)
        if not d:
            self._send(404, self._simple_page("Already processed", "This draft has already been processed.", "#e74c3c"))
            return
        d["status"] = "approved"
        d["linkedin_text"] = li_text
        d["facebook_text"] = fb_text
        _update_draft(d)
        if _publish_callback:
            threading.Thread(target=_publish_callback, args=(d,), daemon=True).start()
        self._send(200, self._simple_page("✅ Publishing now...", "Your post is being published to LinkedIn and Facebook. Check your feeds in a few minutes.", "#2ecc71"))

    def _reject(self, token):
        d = _find_by_token(token)
        if not d:
            self._send(404, self._simple_page("Not found", "Draft not found.", "#e74c3c"))
            return
        d["status"] = "rejected"
        _update_draft(d)
        self._send(200, self._simple_page("❌ Post rejected", "The draft has been discarded. No post was published.", "#e74c3c"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _simple_page(self, title, message, color):
        return _head(title) + _nav() + f"""
<div style="text-align:center;padding:80px 20px">
<div style="background:#fff;border-radius:12px;max-width:500px;margin:0 auto;
            padding:48px 32px;box-shadow:0 2px 12px rgba(0,0,0,.08)">
  <h2 style="color:{color};margin-bottom:16px">{title}</h2>
  <p style="color:#666;font-size:15px;margin-bottom:24px">{message}</p>
  <a href="/" class="btn btn-ghost">Back to Dashboard</a>
</div></div></body></html>"""

    def _send(self, code, html):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        logger.debug(f"AdminServer: {fmt % args}")


# ---------------------------------------------------------------------------
# Server start
# ---------------------------------------------------------------------------

def start_approval_server(publish_callback, port: int = 8080):
    """Start the HTTP admin + approval server in a background daemon thread."""
    global _publish_callback
    _publish_callback = publish_callback
    server = HTTPServer(("0.0.0.0", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info(f"Admin server started on port {port}")
    return server
