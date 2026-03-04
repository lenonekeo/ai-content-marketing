"""
Draft management and HTTP admin server.

Routes:
  GET  /              Dashboard (pending drafts + recent posts)
  GET  /setup         Credentials & settings form
  POST /setup         Save settings to .env
  GET  /influence     Content influence / brand guidelines form
  POST /influence     Save influence settings
  GET  /calendar      Calendar view of all posts
  GET  /create        AI chat-based content creation page
  POST /create/chat   Chat endpoint (multi-turn AI conversation)
  POST /create/save   Save a draft from the Create page
  POST /create/image  Generate an AI image via Gemini
  GET  /media/<file>  Serve generated media from downloads/
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


def _read_all_logs() -> list[dict]:
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
    return records


def _list_all_drafts() -> list[dict]:
    """Return all drafts regardless of status, newest first."""
    if not os.path.exists(DRAFTS_DIR):
        return []
    result = []
    for fname in sorted(os.listdir(DRAFTS_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(DRAFTS_DIR, fname)) as f:
                result.append(json.load(f))
        except Exception:
            pass
    return result


def _get_future_slots(n_weeks: int = 8) -> list:
    """Return list of future scheduled datetimes (UTC) based on POST_DAYS + POST_HOUR + POST_MINUTE."""
    from datetime import datetime, timedelta
    from config import config

    day_abbr_to_weekday = {
        "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    }
    post_days = [
        day_abbr_to_weekday[d.strip().lower()]
        for d in config.post_days.split(",")
        if d.strip().lower() in day_abbr_to_weekday
    ]
    post_hour = config.post_hour
    post_minute = getattr(config, "post_minute", 0)

    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = today + timedelta(weeks=n_weeks)

    slots = []
    current = today
    while current < end:
        if current.weekday() in post_days:
            slot_dt = current.replace(hour=post_hour, minute=post_minute)
            if slot_dt > now:
                slots.append(slot_dt)
        current += timedelta(days=1)
    return slots


def _build_calendar_data() -> list[dict]:
    """Build sorted list of all post entries: posted, drafts, and future planned."""
    from datetime import datetime
    from src.themes import THEMES, INDUSTRIES

    entries = []

    # Past posts from execution log
    for r in _read_all_logs():
        try:
            dt = datetime.fromisoformat(r["timestamp"]).replace(tzinfo=None)
        except Exception:
            continue
        entries.append({
            "dt": dt,
            "status": "posted",
            "theme_name": r.get("theme", "unknown").replace("_", " ").title(),
            "industry": "",
            "preview": r.get("content_preview", ""),
            "li_ok": r.get("linkedin", {}).get("success", False),
            "fb_ok": r.get("facebook", {}).get("success", False),
            "token": None,
        })

    # All drafts (pending, approved, rejected)
    for d in _list_all_drafts():
        try:
            dt = datetime.fromisoformat(d["timestamp"]).replace(tzinfo=None)
        except Exception:
            continue
        preview = d.get("linkedin_text") or d.get("facebook_text") or d.get("instagram_caption") or ""
        status = d.get("status", "pending")
        entries.append({
            "dt": dt,
            "status": status,
            "theme_name": d.get("theme", "unknown").replace("_", " ").title(),
            "industry": d.get("industry", ""),
            "preview": preview,
            "li_ok": None,
            "fb_ok": None,
            "token": d.get("token") if status == "pending" else None,
        })

    # Future planned (skip days that already have a pending/approved draft)
    draft_dates = {e["dt"].date() for e in entries if e["status"] in ("pending", "approved")}
    for slot_dt in _get_future_slots(n_weeks=8):
        if slot_dt.date() not in draft_dates:
            day_of_year = slot_dt.timetuple().tm_yday
            theme = THEMES[day_of_year % len(THEMES)]
            industry = INDUSTRIES[day_of_year % len(INDUSTRIES)]
            entries.append({
                "dt": slot_dt,
                "status": "planned",
                "theme_name": theme["name"],
                "industry": industry,
                "preview": "",
                "li_ok": None,
                "fb_ok": None,
                "token": None,
            })

    entries.sort(key=lambda e: e["dt"])
    return entries


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
.day-cb { display:inline-flex; align-items:center; justify-content:center;
          width:52px; height:40px; border:1.5px solid #e0e0e0; border-radius:7px;
          cursor:pointer; font-weight:600; font-size:13px; color:#888;
          transition: all .15s; user-select:none; }
.day-cb:has(input:checked) { background:#2ecc71; border-color:#2ecc71; color:#fff; }
.day-cb input { display:none; }
.cal-day-group { margin-bottom:20px; }
.cal-date { font-weight:700; font-size:13px; color:#1a1a2e; padding:8px 0 6px;
            border-bottom:2px solid #f0f0f0; margin-bottom:8px; letter-spacing:.3px; }
.cal-entry { display:flex; gap:14px; padding:8px 0; border-bottom:1px solid #f8f8f8;
             align-items:flex-start; }
.cal-entry:last-child { border-bottom:none; }
.cal-time { font-size:12px; font-weight:600; color:#aaa; min-width:64px;
            padding-top:3px; white-space:nowrap; }
.cal-info { flex:1; font-size:13px; }
.cal-preview { color:#999; font-size:12px; margin-top:3px; font-style:italic; }
@keyframes spin { from { transform:rotate(0deg) } to { transform:rotate(360deg) } }
.spinner { display:inline-block; width:28px; height:28px; border:3px solid #e0e0e0;
           border-top-color:#2ecc71; border-radius:50%; animation:spin .8s linear infinite; }
@media (max-width: 620px) {
  .grid-2, .grid-3 { grid-template-columns: 1fr; }
  nav { padding: 0 16px; }
  .nav-brand { font-size: 15px; margin-right: 12px; }
  .nav-links a { padding: 6px 10px; font-size: 13px; }
}
.plt-row { display:flex; gap:10px; flex-wrap:wrap; }
.plt-chk { display:inline-flex; align-items:center; gap:8px; padding:9px 16px;
           border:1.5px solid #e0e0e0; border-radius:8px; cursor:pointer;
           font-weight:600; font-size:13px; color:#777; transition:all .15s;
           user-select:none; }
.plt-chk:has(input:checked) { border-color:#2ecc71; background:#f0fff4; color:#1e8449; }
.plt-chk input { display:none; }
.type-row { display:flex; gap:8px; }
.type-lbl { display:inline-flex; align-items:center; gap:6px; padding:7px 14px;
            border:1.5px solid #e0e0e0; border-radius:8px; cursor:pointer;
            font-size:13px; font-weight:600; color:#777; transition:all .15s;
            user-select:none; }
.type-lbl:has(input:checked) { border-color:#3498db; background:#eaf4fd; color:#2980b9; }
.type-lbl input { display:none; }
details.content-expand { margin-top:5px; }
details.content-expand summary { cursor:pointer; color:#2ecc71; font-size:12px;
  font-weight:600; list-style:none; display:inline-block; }
details.content-expand summary::-webkit-details-marker { display:none; }
.post-text-box { background:#f8f9fa; border-radius:6px; padding:12px 14px;
  font-size:13px; color:#555; line-height:1.6; white-space:pre-wrap;
  margin-top:8px; max-height:340px; overflow-y:auto; border:1px solid #eee; }
.img-preview-box img { max-width:100%; max-height:280px; border-radius:8px;
  display:none; border:1px solid #e0e0e0; margin-top:10px; }
/* Chat UI */
.chat-window { height:420px; overflow-y:auto; padding:16px 0; display:flex;
  flex-direction:column; gap:14px; }
.chat-msg { display:flex; gap:10px; align-items:flex-start; }
.chat-msg.user { flex-direction:row-reverse; }
.chat-bubble { max-width:80%; padding:11px 15px; border-radius:12px;
  font-size:14px; line-height:1.6; white-space:pre-wrap; }
.chat-msg.user .chat-bubble { background:#2ecc71; color:#fff; border-bottom-right-radius:3px; }
.chat-msg.ai .chat-bubble { background:#f0f2f5; color:#333; border-bottom-left-radius:3px; }
.chat-avatar { width:32px; height:32px; border-radius:50%; flex-shrink:0;
  display:flex; align-items:center; justify-content:center; font-size:14px;
  font-weight:700; }
.chat-msg.user .chat-avatar { background:#2ecc71; color:#fff; }
.chat-msg.ai .chat-avatar { background:#1a1a2e; color:#fff; }
.chat-input-row { display:flex; gap:10px; margin-top:12px; }
.chat-input-row textarea { flex:1; resize:none; min-height:60px; max-height:120px; }
.use-this-btn { font-size:11px; padding:4px 10px; margin-top:6px; cursor:pointer;
  background:#f0f2f5; border:1px solid #e0e0e0; border-radius:6px; color:#555;
  font-weight:600; transition:all .15s; }
.use-this-btn:hover { background:#2ecc71; color:#fff; border-color:#2ecc71; }
"""


def _head(title: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — MakOne BI</title>
<style>{_STYLES}</style>
</head><body>"""


def _nav(active: str = "") -> str:
    pages = [("/", "Dashboard"), ("/create", "Create"), ("/setup", "Setup"), ("/influence", "Content Influence"), ("/calendar", "Calendar")]
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
            drafts_html += f"""
<div class="draft-row">
  <div>
    <strong>{theme}</strong> &nbsp;<span class="badge badge-pending">Pending</span>
    <div class="draft-meta">{industry} &nbsp;·&nbsp; {ts}</div>
  </div>
  <a href="/review?token={token}" class="btn btn-primary">Review &amp; Approve</a>
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
            preview = r.get("content_preview", "")
            short = preview[:180]
            if len(preview) > 180:
                preview_html = f"""<details class="content-expand">
  <summary>{_esc(short)}… (show full post)</summary>
  <div class="post-text-box">{_esc(preview)}</div>
</details>"""
            elif preview:
                preview_html = f'<div class="log-detail">{_esc(preview)}</div>'
            else:
                preview_html = ""
            logs_html += f"""
<div class="log-row">
  <div class="log-title">{theme} &nbsp;·&nbsp; {ts}
    &nbsp;<span class="badge badge-none">{media}</span>
    &nbsp;<span class="badge {li_badge}</span> LinkedIn
    &nbsp;<span class="badge {fb_badge}</span> Facebook
  </div>
  {preview_html}
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

    current_days = set(d.strip().lower() for d in env.get("POST_DAYS", "mon,wed,fri").split(","))
    days_html = " ".join(
        f'<label class="day-cb"><input type="checkbox" name="POST_DAYS" value="{d}" '
        f'{"checked" if d in current_days else ""}>{label}</label>'
        for d, label in [
            ("mon", "Mon"), ("tue", "Tue"), ("wed", "Wed"), ("thu", "Thu"),
            ("fri", "Fri"), ("sat", "Sat"), ("sun", "Sun"),
        ]
    )
    post_hour_val = int(env.get("POST_HOUR", "9"))
    post_minute_val = int(env.get("POST_MINUTE", "0"))
    post_time_val = f"{post_hour_val:02d}:{post_minute_val:02d}"

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
      <div class="card-title">Instagram</div>
      <div class="field">
        <label>Access Token <span class="hint">leave blank to keep current — same as Facebook Page Access Token</span></label>
        <input type="password" name="INSTAGRAM_ACCESS_TOKEN" placeholder="{masked("INSTAGRAM_ACCESS_TOKEN") or "EAA..."}">
      </div>
      <div class="field">
        <label>Instagram Account ID <span class="hint">numeric ID of your Instagram Business/Creator account</span></label>
        <input type="text" name="INSTAGRAM_ACCOUNT_ID" value="{val("INSTAGRAM_ACCOUNT_ID")}" placeholder="17841400000000000">
      </div>
      <p style="font-size:12px;color:#aaa;margin-top:4px">
        Requires an Instagram Business or Creator account connected to your Facebook Page.
        The token needs <strong>instagram_basic</strong> and <strong>instagram_content_publish</strong> permissions.
        Instagram posts require an image or video — text-only posts are not supported.
      </p>
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
      <div class="card-title">Email Notifications</div>
      <div class="grid-2">
        <div class="field">
          <label>SMTP Host <span class="hint">your mail server</span></label>
          <input type="text" name="SMTP_HOST" value="{val("SMTP_HOST", "smtp.gmail.com")}"
                 placeholder="smtp.gmail.com · smtp.office365.com · mail.yourdomain.com">
        </div>
        <div class="field">
          <label>SMTP Port <span class="hint">usually 587 (TLS) or 465 (SSL)</span></label>
          <input type="number" name="SMTP_PORT" value="{val("SMTP_PORT", "587")}">
        </div>
      </div>
      <div class="grid-2">
        <div class="field">
          <label>Email Address</label>
          <input type="text" name="SMTP_USER" value="{val("SMTP_USER")}">
        </div>
        <div class="field">
          <label>Password / App Password <span class="hint">leave blank to keep current</span></label>
          <input type="password" name="SMTP_PASSWORD" placeholder="{masked("SMTP_PASSWORD") or "your email password"}">
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Posting Schedule</div>
      <div class="field">
        <label>Post Days <span class="hint">select one or more days</span></label>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
          {days_html}
        </div>
      </div>
      <div class="grid-2" style="margin-top:16px">
        <div class="field">
          <label>Post Time <span class="hint">24-hour clock</span></label>
          <input type="time" name="POST_TIME" value="{post_time_val}" style="max-width:180px">
        </div>
        <div class="field">
          <label>Timezone</label>
          <select name="TIMEZONE">
            {"".join(f'<option value="{tz}" {"selected" if env.get("TIMEZONE","UTC")==tz else ""}>{label}</option>' for tz, label in [
              ("UTC","UTC"),
              ("America/New_York","EST/EDT — New York, Toronto, Montreal"),
              ("America/Chicago","CST/CDT — Chicago, Dallas"),
              ("America/Denver","MST/MDT — Denver, Phoenix"),
              ("America/Los_Angeles","PST/PDT — Los Angeles, Vancouver"),
              ("America/Sao_Paulo","BRT — São Paulo, Brazil"),
              ("Europe/London","GMT/BST — London"),
              ("Europe/Paris","CET/CEST — Paris, Brussels"),
              ("Europe/Berlin","CET/CEST — Berlin, Amsterdam"),
              ("Asia/Dubai","GST — Dubai"),
              ("Asia/Kolkata","IST — India"),
              ("Asia/Singapore","SGT — Singapore"),
              ("Asia/Tokyo","JST — Tokyo"),
              ("Australia/Sydney","AEDT — Sydney"),
            ])}
          </select>
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


def _page_calendar() -> str:
    from datetime import datetime
    from config import config

    now = datetime.utcnow()
    all_entries = _build_calendar_data()

    future = [e for e in all_entries if e["dt"] >= now]
    past = list(reversed([e for e in all_entries if e["dt"] < now]))

    def _render_group(entry_list: list) -> str:
        if not entry_list:
            return '<p class="empty">Nothing here yet</p>'

        html = ""
        current_date_str = None

        for e in entry_list:
            dt = e["dt"]
            date_str = dt.strftime(f"%A, %B {dt.day}, %Y")
            time_str = dt.strftime("%H:%M UTC")

            if date_str != current_date_str:
                if current_date_str is not None:
                    html += "</div>"  # close previous day group
                html += f'<div class="cal-day-group"><div class="cal-date">{date_str}</div>'
                current_date_str = date_str

            status = e["status"]
            if status == "posted":
                badge = '<span class="badge badge-ok">Posted</span>'
                li = ' &nbsp;<span style="font-size:11px;color:#1e8449">LI ✓</span>' if e.get("li_ok") else ' &nbsp;<span style="font-size:11px;color:#c0392b">LI ✗</span>'
                fb = ' &nbsp;<span style="font-size:11px;color:#1e8449">FB ✓</span>' if e.get("fb_ok") else ' &nbsp;<span style="font-size:11px;color:#c0392b">FB ✗</span>'
                extra = li + fb
            elif status == "pending":
                badge = '<span class="badge badge-pending">Pending Approval</span>'
                token = e.get("token", "")
                extra = f' &nbsp;<a href="/review?token={token}" style="color:#2ecc71;font-weight:600;font-size:12px">Review →</a>'
            elif status == "approved":
                badge = '<span class="badge badge-ok">Approved</span>'
                extra = ""
            elif status == "rejected":
                badge = '<span class="badge badge-fail">Rejected</span>'
                extra = ""
            else:  # planned
                badge = '<span class="badge badge-none">Planned</span>'
                extra = ""

            industry = f' &nbsp;·&nbsp; <span style="color:#888">{_esc(e["industry"])}</span>' if e.get("industry") else ""
            preview = e.get("preview", "")
            short = preview[:180]
            if len(preview) > 180:
                preview_html = f"""<details class="content-expand">
  <summary>{_esc(short)}… (show full post)</summary>
  <div class="post-text-box">{_esc(preview)}</div>
</details>"""
            elif preview:
                preview_html = f'<div class="cal-preview">{_esc(preview)}</div>'
            else:
                preview_html = ""

            html += f"""<div class="cal-entry">
  <div class="cal-time">{time_str}</div>
  <div class="cal-info">
    <div>{badge} &nbsp;<strong>{_esc(e["theme_name"])}</strong>{industry}{extra}</div>
    {preview_html}
  </div>
</div>"""

        if current_date_str is not None:
            html += "</div>"  # close last day group
        return html

    future_html = _render_group(future)
    past_html = _render_group(past)

    return _head("Calendar") + _nav("/calendar") + f"""
<div class="container">
  <h1>Calendar</h1>
  <p class="subtitle">All scheduled, pending, and past posts — times shown in UTC.</p>

  <div class="card">
    <div class="card-title">Upcoming Posts</div>
    {future_html}
  </div>

  <div class="card">
    <div class="card-title">Past Posts</div>
    {past_html}
  </div>
</div></body></html>"""


def _page_create(alert: str = "", alert_type: str = "success") -> str:
    from config import config as _cfg
    from src.influence import load as _load_influence
    inf = _load_influence()
    tz_name = _cfg.timezone or "UTC"
    default_role = f"You are an expert content marketer and copywriter for {_cfg.business_name}. Your goal is to write engaging, professional social media content that drives business results."
    alert_html = f'<div class="alert alert-{alert_type}">{alert}</div>' if alert else ""

    # Build influence summary badge
    inf_parts = []
    if inf.get("topics"):
        inf_parts.append(f"Topics: {inf['topics'][:60]}")
    if inf.get("target_audience"):
        inf_parts.append(f"Audience: {inf['target_audience'][:50]}")
    if inf.get("brand_voice"):
        inf_parts.append(f"Tone: {inf['brand_voice'][:40]}")
    url_count = len([u for u in inf.get("inspiration_urls", "").splitlines() if u.strip()])
    if url_count:
        inf_parts.append(f"{url_count} inspiration URL{'s' if url_count > 1 else ''}")
    if inf_parts:
        inf_summary_html = (
            f'<div style="background:#1a2e1a;border:1px solid #2ecc71;border-radius:6px;padding:10px 14px;margin-top:12px;font-size:12px">'
            f'<span style="color:#2ecc71;font-weight:600">✓ Content Influence active</span>'
            f'<span style="color:#aaa;margin-left:8px">{_esc(" · ".join(inf_parts))}</span>'
            f'<a href="/influence" style="color:#2ecc71;margin-left:12px">Edit →</a>'
            f'</div>'
        )
    else:
        inf_summary_html = (
            f'<div style="background:#2e1a0a;border:1px solid #e67e22;border-radius:6px;padding:10px 14px;margin-top:12px;font-size:12px">'
            f'<span style="color:#e67e22">⚠ No Content Influence settings — the AI will use generic context.</span>'
            f'<a href="/influence" style="color:#e67e22;margin-left:10px">Set up →</a>'
            f'</div>'
        )

    # Video buttons (enabled only if credentials set)
    veo3_btn = (
        '<button class="btn btn-ghost" onclick="generateVideo(\'veo3\')" id="veo3-btn">Generate Video (VEO 3)</button>'
        if _cfg.veo3_enabled else
        '<button class="btn btn-ghost" disabled title="Configure GOOGLE_API_KEY in Setup">VEO 3 (not configured)</button>'
    )
    heygen_btn = (
        '<button class="btn btn-ghost" onclick="generateVideo(\'heygen\')" id="heygen-btn">AI Clone (HeyGen)</button>'
        if _cfg.heygen_enabled else
        '<button class="btn btn-ghost" disabled title="Configure HEYGEN_API_KEY in Setup">HeyGen (not configured)</button>'
    )

    return _head("Create Content") + _nav("/create") + f"""
<div class="container">
  {alert_html}
  <h1>Create Content</h1>
  <p class="subtitle">
    Chat with the AI to craft your post. Describe your idea, ask for revisions, and say
    <strong>"write a LinkedIn post about X"</strong> or <strong>"make it shorter"</strong>.
    When you're happy with a response, click <strong>Use this</strong> to edit and save it as a draft.
  </p>

  <div class="card">
    <div class="card-title">Settings</div>
    <div class="field">
      <label>AI Role <span class="hint">the persona and context for the AI — auto-filled from your business info</span></label>
      <textarea id="system_role" style="min-height:80px">{_esc(default_role)}</textarea>
    </div>
    <div class="grid-2" style="margin-top:16px">
      <div class="field">
        <label>Platforms</label>
        <div class="plt-row">
          <label class="plt-chk"><input type="checkbox" id="plt-linkedin" checked> LinkedIn</label>
          <label class="plt-chk"><input type="checkbox" id="plt-facebook" checked> Facebook</label>
          <label class="plt-chk"><input type="checkbox" id="plt-instagram"> Instagram</label>
        </div>
      </div>
      <div class="field">
        <label>Content Type</label>
        <div class="type-row">
          <label class="type-lbl"><input type="radio" name="ctype" value="post" checked> Organic Post</label>
          <label class="type-lbl"><input type="radio" name="ctype" value="ad"> Sponsored Ad</label>
        </div>
      </div>
    </div>
    {inf_summary_html}
  </div>

  <div class="card">
    <div class="card-title">Chat</div>
    <div class="chat-window" id="chat-window">
      <div class="chat-msg ai">
        <div class="chat-avatar">AI</div>
        <div class="chat-bubble">Hello! I&apos;m ready to help you create great social media content. Tell me what you&apos;d like to post about, and I&apos;ll write it for your selected platforms. You can ask me to refine, shorten, or change the tone at any time.</div>
      </div>
    </div>
    <div id="error-box" class="alert alert-error" style="display:none;margin-top:12px"></div>
    <div class="chat-input-row">
      <textarea id="chat-input" placeholder="Write a post about... / Make it shorter / Change the tone to..." onkeydown="handleKey(event)"></textarea>
      <button id="send-btn" class="btn btn-primary" onclick="sendMessage()" style="align-self:flex-end">Send</button>
    </div>
    <div style="display:flex;align-items:center;gap:12px;margin-top:10px">
      <span id="spinner" style="display:none"><span class="spinner"></span>
        <span style="color:#888;font-size:13px;margin-left:8px">Thinking...</span></span>
      <button class="btn btn-ghost" onclick="clearChat()" style="font-size:13px;padding:7px 14px">Clear chat</button>
    </div>
  </div>

  <div id="draft-section" style="display:none">
    <div class="card">
      <div class="card-title">Edit &amp; Save Draft</div>
      <p style="font-size:13px;color:#888;margin-bottom:16px">Edit the content below before saving. Each platform&apos;s text is independent.</p>
      <div id="li-field" class="field">
        <label>LinkedIn Post <span class="hint">editable</span></label>
        <textarea id="linkedin_text" style="min-height:200px"></textarea>
      </div>
      <div id="fb-field" class="field" style="margin-top:16px">
        <label>Facebook Post <span class="hint">editable</span></label>
        <textarea id="facebook_text" style="min-height:180px"></textarea>
      </div>
      <div id="ig-field" class="field" style="margin-top:16px;display:none">
        <label>Instagram Caption <span class="hint">editable — max ~150 words for best reach</span></label>
        <textarea id="instagram_caption" style="min-height:150px"></textarea>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Media <span class="hint">optional — attach an image or video to your post</span></div>
      <div class="grid-2">
        <div class="field">
          <label>Image URL <span class="hint">publicly accessible HTTPS link</span></label>
          <input type="text" id="image_url" placeholder="https://..." oninput="previewImage()">
          <div class="img-preview-box"><img id="img-preview" src="" alt="Preview"></div>
        </div>
        <div class="field">
          <label>Video URL <span class="hint">publicly accessible MP4 link</span></label>
          <input type="text" id="video_url" placeholder="https://..." oninput="previewVideo()">
          <div id="vid-preview-box" style="display:none;margin-top:8px">
            <video id="vid-preview" controls style="max-width:100%;border-radius:6px;max-height:200px"></video>
          </div>
        </div>
      </div>
      <div style="margin-top:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <button class="btn btn-ghost" onclick="generateAIImage()">Generate AI Image</button>
        <span id="img-spinner" style="display:none"><span class="spinner" style="width:20px;height:20px;border-width:2px"></span></span>
        <span id="img-status" style="font-size:13px;color:#888"></span>
      </div>
      <div style="margin-top:10px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        {veo3_btn}
        {heygen_btn}
        <span id="vid-spinner" style="display:none"><span class="spinner" style="width:20px;height:20px;border-width:2px"></span></span>
        <span id="vid-status" style="font-size:13px;color:#888"></span>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Schedule</div>
      <div class="field">
        <div style="display:flex;gap:20px;margin-bottom:12px;flex-wrap:wrap">
          <label style="display:inline-flex;align-items:center;gap:8px;font-weight:normal;cursor:pointer">
            <input type="radio" name="sched_type" value="now" checked onchange="toggleSchedule()">
            Save as draft (publish manually via Dashboard)
          </label>
          <label style="display:inline-flex;align-items:center;gap:8px;font-weight:normal;cursor:pointer">
            <input type="radio" name="sched_type" value="later" onchange="toggleSchedule()">
            Schedule for a specific date &amp; time
          </label>
        </div>
        <div id="sched-picker" style="display:none">
          <label>Date &amp; Time <span class="hint">{tz_name} — post will publish automatically at this time</span></label>
          <input type="datetime-local" id="scheduled_at" style="max-width:280px">
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:0">
      <div class="section-actions">
        <button id="save-btn" class="btn btn-primary" onclick="saveAsDraft()">Save as Draft</button>
        <button class="btn btn-ghost" onclick="document.getElementById('draft-section').style.display='none'">Cancel</button>
      </div>
    </div>
  </div>
</div>

<script>
let messages = [];
let selectedPlatforms = ["linkedin", "facebook"];

function getSelectedPlatforms() {{
  return ["linkedin","facebook","instagram"].filter(p => document.getElementById("plt-"+p).checked);
}}
function getContentType() {{
  return document.querySelector('input[name="ctype"]:checked').value;
}}

function handleKey(e) {{
  if (e.key === "Enter" && !e.shiftKey) {{
    e.preventDefault();
    sendMessage();
  }}
}}

async function sendMessage() {{
  const input = document.getElementById("chat-input").value.trim();
  if (!input) return;
  selectedPlatforms = getSelectedPlatforms();
  if (!selectedPlatforms.length) {{ showError("Select at least one platform."); return; }}

  appendMsg("user", input);
  document.getElementById("chat-input").value = "";
  messages.push({{role: "user", content: input}});

  setLoading(true);
  document.getElementById("error-box").style.display = "none";

  try {{
    const systemRole = document.getElementById("system_role").value.trim();
    const ctype = getContentType();
    const platformNote = selectedPlatforms.map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(", ");
    const typeNote = ctype === "ad" ? "sponsored ad copy" : "organic social media post";
    // Add platform context to user's first substantive message via system
    const contextualRole = systemRole +
      `\\n\\nYou are writing ${{typeNote}} for: ${{platformNote}}.` +
      (ctype === "ad" ? " Use persuasive, action-oriented language with a strong CTA. Keep it concise." :
       " Write naturally and professionally. Include 3-5 relevant hashtags.");

    const resp = await fetch("/create/chat", {{
      method: "POST",
      headers: {{"Content-Type": "application/x-www-form-urlencoded"}},
      body: "messages=" + encodeURIComponent(JSON.stringify(messages)) +
            "&system_role=" + encodeURIComponent(contextualRole)
    }});
    const data = await resp.json();
    if (data.error) {{
      showError(data.error);
      messages.pop();
    }} else {{
      messages.push({{role: "assistant", content: data.reply}});
      appendMsg("ai", data.reply, true);
    }}
  }} catch(e) {{
    showError("Request failed: " + e.message);
    messages.pop();
  }} finally {{
    setLoading(false);
  }}
}}

let _draftTexts = [];

function appendMsg(role, text, showUseThis=false) {{
  const win = document.getElementById("chat-window");
  const div = document.createElement("div");
  div.className = "chat-msg " + role;
  const escaped = text.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  div.innerHTML = `<div class="chat-avatar">${{role === "user" ? "You" : "AI"}}</div>
    <div><div class="chat-bubble">${{escaped}}</div></div>`;
  if (showUseThis) {{
    const idx = _draftTexts.length;
    _draftTexts.push(text);
    const btn = document.createElement("button");
    btn.className = "use-this-btn";
    btn.textContent = "Use this \u2193";
    btn.onclick = function() {{ useThis(idx); }};
    div.lastElementChild.appendChild(btn);
  }}
  win.appendChild(div);
  win.scrollTop = win.scrollHeight;
}}

function useThis(idx) {{
  const text = _draftTexts[idx] !== undefined ? _draftTexts[idx] : "";
  const platforms = getSelectedPlatforms();
  // Show draft section with platform fields
  document.getElementById("li-field").style.display = platforms.includes("linkedin") ? "" : "none";
  document.getElementById("fb-field").style.display = platforms.includes("facebook") ? "" : "none";
  document.getElementById("ig-field").style.display = platforms.includes("instagram") ? "" : "none";
  // Populate all selected fields with the AI text (user can edit per-platform)
  if (platforms.includes("linkedin")) document.getElementById("linkedin_text").value = text;
  if (platforms.includes("facebook")) document.getElementById("facebook_text").value = text;
  if (platforms.includes("instagram")) document.getElementById("instagram_caption").value = text;
  document.getElementById("draft-section").style.display = "block";
  document.getElementById("draft-section").scrollIntoView({{behavior:"smooth",block:"start"}});
}}

async function saveAsDraft() {{
  const li = document.getElementById("linkedin_text").value.trim();
  const fb = document.getElementById("facebook_text").value.trim();
  const ig = document.getElementById("instagram_caption").value.trim();
  if (!li && !fb && !ig) {{ showError("Nothing to save."); return; }}
  const platforms = getSelectedPlatforms();
  const schedType = document.querySelector('input[name="sched_type"]:checked').value;
  const scheduledAt = schedType === "later" ? document.getElementById("scheduled_at").value : "";
  const imageUrl = document.getElementById("image_url").value.trim();
  const videoUrl = document.getElementById("video_url").value.trim();
  const btn = document.getElementById("save-btn");
  btn.disabled = true; btn.textContent = "Saving...";
  try {{
    let params = "linkedin_text=" + encodeURIComponent(li) +
                 "&facebook_text=" + encodeURIComponent(fb) +
                 "&instagram_caption=" + encodeURIComponent(ig) +
                 "&scheduled_at=" + encodeURIComponent(scheduledAt) +
                 "&image_url=" + encodeURIComponent(imageUrl) +
                 "&video_url=" + encodeURIComponent(videoUrl);
    platforms.forEach(p => {{ params += "&platforms=" + encodeURIComponent(p); }});
    const resp = await fetch("/create/save", {{
      method:"POST", headers:{{"Content-Type":"application/x-www-form-urlencoded"}}, body: params
    }});
    const data = await resp.json();
    if (data.redirect) {{
      window.location.href = data.redirect;
    }} else if (data.error) {{
      showError(data.error);
      btn.disabled = false; btn.textContent = "Save as Draft";
    }}
  }} catch(e) {{
    showError("Failed: " + e.message);
    btn.disabled = false; btn.textContent = "Save as Draft";
  }}
}}

async function generateAIImage() {{
  const input = document.getElementById("chat-input").value.trim() ||
                (messages.length > 0 ? messages[messages.length-1].content : "business automation");
  const btn = event.target;
  btn.disabled = true;
  document.getElementById("img-spinner").style.display = "inline-flex";
  document.getElementById("img-status").textContent = "Generating image...";
  try {{
    const resp = await fetch("/create/image", {{
      method:"POST", headers:{{"Content-Type":"application/x-www-form-urlencoded"}},
      body: "prompt=" + encodeURIComponent(input)
    }});
    const data = await resp.json();
    if (data.url) {{
      document.getElementById("image_url").value = data.url;
      previewImage();
      document.getElementById("img-status").textContent = "Image generated!";
    }} else {{
      document.getElementById("img-status").textContent = data.error || "Generation failed";
    }}
  }} catch(e) {{
    document.getElementById("img-status").textContent = "Error: " + e.message;
  }} finally {{
    btn.disabled = false;
    document.getElementById("img-spinner").style.display = "none";
  }}
}}

function previewImage() {{
  const url = document.getElementById("image_url").value.trim();
  const img = document.getElementById("img-preview");
  img.src = url;
  img.style.display = url ? "block" : "none";
}}

function previewVideo() {{
  const url = document.getElementById("video_url").value.trim();
  const vid = document.getElementById("vid-preview");
  const box = document.getElementById("vid-preview-box");
  if (url) {{
    vid.src = url;
    box.style.display = "block";
  }} else {{
    box.style.display = "none";
  }}
}}

function toggleSchedule() {{
  const later = document.querySelector('input[name="sched_type"][value="later"]').checked;
  document.getElementById("sched-picker").style.display = later ? "block" : "none";
}}

async function generateVideo(type) {{
  const lastMsg = messages.length > 0 ? messages[messages.length-1].content : "";
  const chatInput = document.getElementById("chat-input").value.trim();
  const script = lastMsg || chatInput || "AI automation and business intelligence services";
  const spinner = document.getElementById("vid-spinner");
  const status = document.getElementById("vid-status");
  const veo3Btn = document.getElementById("veo3-btn");
  const heygenBtn = document.getElementById("heygen-btn");

  function _endJob() {{
    spinner.style.display = "none";
    if (veo3Btn) veo3Btn.disabled = false;
    if (heygenBtn) heygenBtn.disabled = false;
  }}

  spinner.style.display = "inline-flex";
  status.textContent = type === "veo3" ? "Submitting to VEO 3..." : "Submitting to HeyGen...";
  if (veo3Btn) veo3Btn.disabled = true;
  if (heygenBtn) heygenBtn.disabled = true;

  try {{
    const resp = await fetch("/create/video/" + type, {{
      method: "POST",
      headers: {{"Content-Type": "application/x-www-form-urlencoded"}},
      body: (type === "veo3" ? "prompt=" : "script=") + encodeURIComponent(script)
    }});
    const data = await resp.json();
    if (data.error) {{
      status.textContent = "Error: " + data.error;
      _endJob();
      return;
    }}
    const jobId = data.job_id;
    status.textContent = type === "veo3" ? "⏳ VEO 3 generating (~2 min)..." : "⏳ HeyGen generating avatar (2–5 min)...";
    // Poll for completion — spinner stays visible until done/error
    let pollCount = 0;
    const poll = setInterval(async () => {{
      try {{
        pollCount++;
        const sr = await fetch("/create/video/status?job_id=" + encodeURIComponent(jobId));
        const sd = await sr.json();
        if (sd.status === "done") {{
          clearInterval(poll);
          document.getElementById("video_url").value = sd.url;
          previewVideo();
          status.textContent = "✓ Video ready! URL filled below.";
          document.getElementById("draft-section").style.display = "block";
          _endJob();
        }} else if (sd.status === "error") {{
          clearInterval(poll);
          const errMsg = sd.error || "Generation failed";
          let hint = "";
          if (type === "heygen") {{
            if (errMsg.includes("401") || errMsg.toLowerCase().includes("unauthorized") || errMsg.toLowerCase().includes("api key")) {{
              hint = " → Check your HEYGEN_API_KEY in Setup.";
            }} else if (errMsg.includes("400") || errMsg.toLowerCase().includes("avatar_id") || errMsg.toLowerCase().includes("invalid")) {{
              hint = " → Check HEYGEN_AVATAR_ID in Setup (use the Avatar ID from HeyGen dashboard, not the Look ID).";
            }} else if (errMsg.toLowerCase().includes("voice")) {{
              hint = " → Check HEYGEN_VOICE_ID in Setup.";
            }} else if (errMsg.includes("403")) {{
              hint = " → Your HeyGen plan may not support this feature.";
            }} else {{
              hint = " → Go to Setup and verify HEYGEN_API_KEY, HEYGEN_AVATAR_ID, and HEYGEN_VOICE_ID.";
            }}
          }} else if (type === "veo3") {{
            if (errMsg.includes("401") || errMsg.toLowerCase().includes("api key")) {{
              hint = " → Check your GOOGLE_API_KEY in Setup.";
            }} else {{
              hint = " → Check your GOOGLE_API_KEY in Setup.";
            }}
          }}
          status.innerHTML = '<span style="color:#e74c3c">✗ Error: ' + errMsg + '</span><br><span style="color:#e67e22;font-size:12px">' + hint + '</span>';
          _endJob();
        }} else {{
          const dots = ".".repeat((pollCount % 3) + 1);
          status.textContent = (type === "veo3" ? "⏳ VEO 3 generating" : "⏳ HeyGen generating avatar") + dots;
        }}
      }} catch(e) {{ /* ignore transient poll errors */ }}
    }}, 8000);
  }} catch(e) {{
    status.textContent = "Request failed: " + e.message;
    _endJob();
  }}
}}

function clearChat() {{
  messages = [];
  _draftTexts = [];
  const win = document.getElementById("chat-window");
  win.innerHTML = `<div class="chat-msg ai">
    <div class="chat-avatar">AI</div>
    <div class="chat-bubble">Chat cleared. What would you like to create?</div>
  </div>`;
  document.getElementById("error-box").style.display = "none";
  document.getElementById("draft-section").style.display = "none";
}}

function setLoading(on) {{
  document.getElementById("send-btn").disabled = on;
  document.getElementById("spinner").style.display = on ? "inline-flex" : "none";
}}

function showError(msg) {{
  const box = document.getElementById("error-box");
  box.textContent = msg;
  box.style.display = "block";
}}
</script>
</body></html>"""


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

_publish_callback = None  # set by start_approval_server

# Background video generation jobs: job_id -> {"status": "pending"|"done"|"error", "url": "", "error": ""}
_video_jobs: dict = {}


def _start_video_job(job_id: str, video_type: str, text: str):
    """Run video generation in a background thread."""
    import threading
    import datetime as _dtmod

    def _run():
        try:
            # Reload .env so latest Setup credentials are used
            from dotenv import load_dotenv as _ldenv
            import os as _os
            _ldenv(override=True)
            ts = _dtmod.datetime.now().strftime("%Y%m%d_%H%M%S")
            if video_type == "veo3":
                from src import veo3_client
                from config import config as _cfg
                fname = f"veo3_{ts}.mp4"
                veo3_client.make_video(text, fname)
                url = _cfg.get_public_url(f"/media/{fname}")
            else:  # heygen
                import os as _os2
                from src import heygen_client
                # Use fresh values from env
                heygen_client.config.heygen_api_key = _os.getenv("HEYGEN_API_KEY", "")
                heygen_client.config.heygen_avatar_id = _os.getenv("HEYGEN_AVATAR_ID", "")
                heygen_client.config.heygen_voice_id = _os.getenv("HEYGEN_VOICE_ID", "")
                video_url = heygen_client.wait_for_video(heygen_client.create_video(text))
                url = video_url  # HeyGen returns a public CDN URL directly
            _video_jobs[job_id] = {"status": "done", "url": url}
            logger.info(f"Video job {job_id} ({video_type}) completed: {url}")
        except Exception as e:
            _video_jobs[job_id] = {"status": "error", "error": str(e)}
            logger.error(f"Video job {job_id} ({video_type}) failed: {e}")

    _video_jobs[job_id] = {"status": "pending"}
    threading.Thread(target=_run, daemon=True).start()

_SENSITIVE_KEYS = {
    "OPENAI_API_KEY", "HEYGEN_API_KEY", "GOOGLE_API_KEY",
    "LINKEDIN_ACCESS_TOKEN", "FACEBOOK_ACCESS_TOKEN",
    "INSTAGRAM_ACCESS_TOKEN", "SMTP_PASSWORD",
}

_SETUP_KEYS = {
    "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_TEMPERATURE",
    "HEYGEN_API_KEY", "HEYGEN_AVATAR_ID", "HEYGEN_VOICE_ID",
    "GOOGLE_API_KEY", "GOOGLE_PROJECT_ID",
    "LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN", "LINKEDIN_ORG_URN",
    "FACEBOOK_ACCESS_TOKEN", "FACEBOOK_PAGE_ID",
    "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_ACCOUNT_ID",
    "BUSINESS_NAME", "BUSINESS_WEBSITE", "CONTACT_EMAIL",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
    "POST_DAYS", "POST_HOUR", "POST_MINUTE", "TIMEZONE",
    "APPROVAL_REQUIRED", "VPS_HOST", "APPROVAL_PORT",
}


class _Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            p = urlparse(self.path)
            qs = parse_qs(p.query)
            token = qs.get("token", [None])[0]

            if p.path in ("/", ""):
                self._send(200, _page_dashboard())
            elif p.path == "/setup":
                self._send(200, _page_setup())
            elif p.path == "/influence":
                self._send(200, _page_influence())
            elif p.path == "/calendar":
                self._send(200, _page_calendar())
            elif p.path == "/create":
                self._send(200, _page_create())
            elif p.path == "/create/video/status":
                job_id = qs.get("job_id", [None])[0]
                job = _video_jobs.get(job_id, {"status": "error", "error": "Unknown job"})
                self._send_json(job)
            elif p.path.startswith("/media/"):
                self._serve_media(p.path[7:])
            elif p.path == "/review":
                self._review(token)
            elif p.path == "/reject":
                self._reject(token)
            else:
                self._send(404, self._simple_page("Not found", "Page not found.", "#e74c3c"))
        except Exception as exc:
            logger.exception(f"Unhandled error in GET {self.path}")
            try:
                self._send(500, self._simple_page(
                    "Server Error",
                    f"Error: {_esc(str(exc))}",
                    "#e74c3c",
                ))
            except Exception:
                pass

    def do_POST(self):
        try:
            p = urlparse(self.path)
            qs = parse_qs(p.query)
            token = qs.get("token", [None])[0]
            n = int(self.headers.get("Content-Length", 0))
            body = parse_qs(self.rfile.read(n).decode("utf-8", errors="replace"))

            if p.path == "/setup":
                self._save_setup(body)
            elif p.path == "/influence":
                self._save_influence(body)
            elif p.path == "/create/chat":
                self._chat_create(body)
            elif p.path == "/create/save":
                self._save_content_draft(body)
            elif p.path == "/create/image":
                self._generate_ai_image(body)
            elif p.path in ("/create/video/veo3", "/create/video/heygen"):
                self._start_video_generation(body, p.path)
            elif p.path == "/publish":
                li = body.get("linkedin_text", [""])[0]
                fb = body.get("facebook_text", [""])[0]
                self._publish(token, li, fb)
            else:
                self._send(404, self._simple_page("Not found", "Page not found.", "#e74c3c"))
        except Exception as exc:
            logger.exception(f"Unhandled error in POST {self.path}")
            try:
                self._send(500, self._simple_page(
                    "Server Error",
                    f"Error: {_esc(str(exc))}",
                    "#e74c3c",
                ))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Admin handlers
    # ------------------------------------------------------------------

    def _save_setup(self, body: dict):
        env = _read_env()
        updates = {}

        # POST_DAYS: multiple checkboxes return a list
        post_days_list = body.get("POST_DAYS", [])
        updates["POST_DAYS"] = ",".join(post_days_list) if post_days_list else env.get("POST_DAYS", "mon,wed,fri")

        # POST_TIME → split into POST_HOUR + POST_MINUTE
        skip_keys = {"POST_DAYS", "POST_HOUR", "POST_MINUTE"}
        post_time = body.get("POST_TIME", [""])[0].strip()
        if post_time and ":" in post_time:
            try:
                h, m = post_time.split(":", 1)
                updates["POST_HOUR"] = str(int(h))
                updates["POST_MINUTE"] = str(int(m))
            except ValueError:
                pass

        for key in _SETUP_KEYS:
            if key in skip_keys:
                continue
            form_val = body.get(key, [""])[0].strip()
            if form_val:
                updates[key] = form_val
            elif key in _SENSITIVE_KEYS:
                pass  # keep existing
            else:
                updates[key] = form_val

        _write_env(updates)
        logger.info(f"Settings updated: {[k for k in updates if k not in _SENSITIVE_KEYS]}")

        # Live-reschedule if any schedule setting changed — no restart needed
        schedule_keys = {"POST_DAYS", "POST_HOUR", "POST_MINUTE", "TIMEZONE"}
        if schedule_keys & set(updates):
            try:
                from scheduler import reschedule_job
                days = updates.get("POST_DAYS", "mon,wed,fri")
                hour = int(updates.get("POST_HOUR", "9"))
                minute = int(updates.get("POST_MINUTE", "0"))
                tz = updates.get("TIMEZONE", "UTC")
                reschedule_job(days, hour, minute, tz)
                alert_msg = "Settings saved. Schedule updated live — no restart needed."
            except Exception as e:
                logger.error(f"Live reschedule failed: {e}")
                alert_msg = "Settings saved. Restart the service to apply the new schedule."
        else:
            alert_msg = "Settings saved successfully. Restart the service for changes to take effect."

        self._send(200, _page_setup(alert=alert_msg, alert_type="success"))

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

    def _chat_create(self, body: dict):
        """Handle multi-turn AI chat for content creation."""
        import json as _json
        messages_raw = body.get("messages", ["[]"])[0]
        system_role = body.get("system_role", [""])[0].strip()
        try:
            messages = _json.loads(messages_raw)
        except Exception:
            messages = []
        if not messages:
            self._send_json({"error": "No messages provided."})
            return
        try:
            from openai import OpenAI
            from config import config
            from src.influence import get_prompt_context

            # Build system prompt: role + influence context
            system_content = system_role or f"You are an expert content marketer for {config.business_name}."
            ctx = get_prompt_context()
            if ctx:
                system_content += ctx

            full_messages = [{"role": "system", "content": system_content}] + messages

            client = OpenAI(api_key=config.openai_api_key)
            resp = client.chat.completions.create(
                model=config.openai_model,
                messages=full_messages,
                temperature=config.openai_temperature,
                max_tokens=800,
            )
            reply = resp.choices[0].message.content.strip()
            self._send_json({"reply": reply})
        except Exception as e:
            logger.exception("Error in chat create")
            self._send_json({"error": str(e)})

    def _save_content_draft(self, body: dict):
        li = body.get("linkedin_text", [""])[0].strip()
        fb = body.get("facebook_text", [""])[0].strip()
        ig = body.get("instagram_caption", [""])[0].strip()
        platforms = body.get("platforms", [])
        scheduled_at = body.get("scheduled_at", [""])[0].strip()
        image_url = body.get("image_url", [""])[0].strip()
        video_url = body.get("video_url", [""])[0].strip()
        if not li and not fb and not ig:
            self._send_json({"error": "No content to save."})
            return
        draft_data = {
            "theme": "custom",
            "industry": "Custom",
            "linkedin_text": li,
            "facebook_text": fb,
            "instagram_caption": ig,
            "platforms": platforms,
            "content_preview": (li or fb or ig)[:300],
        }
        if scheduled_at:
            # Convert from user's configured timezone to UTC for comparison
            try:
                from zoneinfo import ZoneInfo
                import datetime as _dtmod
                from config import config as _cfg
                tz_name = _cfg.timezone or "UTC"
                naive_dt = _dtmod.datetime.fromisoformat(scheduled_at)
                aware_dt = naive_dt.replace(tzinfo=ZoneInfo(tz_name))
                utc_dt = aware_dt.astimezone(_dtmod.timezone.utc)
                scheduled_at = utc_dt.strftime("%Y-%m-%dT%H:%M:%S")
            except Exception as _e:
                logger.warning(f"Timezone conversion for scheduled_at failed: {_e}")
            draft_data["scheduled_at"] = scheduled_at
        if image_url:
            draft_data["image_url"] = image_url
        if video_url:
            draft_data["video_url"] = video_url
        draft = save_draft(draft_data)
        # Only send approval email for manual drafts (not auto-scheduled)
        if not scheduled_at:
            try:
                from src.notifier import send_approval_email
                from config import config
                review_url = config.get_public_url(f"/review?token={draft['token']}")
                send_approval_email(draft, review_url)
            except Exception as e:
                logger.warning(f"Could not send approval email: {e}")
        self._send_json({"redirect": "/"})

    def _send_json(self, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_media(self, filename: str):
        """Serve a file from the downloads/ directory."""
        # Basic safety: strip path traversal
        filename = os.path.basename(filename)
        filepath = os.path.join("downloads", filename)
        if not os.path.exists(filepath) or not os.path.isfile(filepath):
            self._send(404, self._simple_page("Not found", "File not found.", "#e74c3c"))
            return
        ext = os.path.splitext(filename)[1].lower()
        ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".mp4": "video/mp4", ".gif": "image/gif"}.get(ext, "application/octet-stream")
        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _generate_ai_image(self, body: dict):
        """Generate an AI image via Gemini Imagen and return a URL to serve it."""
        prompt = body.get("prompt", [""])[0].strip() or "professional business automation"
        try:
            from src import imagen_client
            from config import config
            if not config.imagen_enabled:
                self._send_json({"error": "Google API key not configured. Add GOOGLE_API_KEY in Setup."})
                return
            import datetime as _dt
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            img_prompt = imagen_client.build_image_prompt("custom", prompt, "Business")
            image_path = imagen_client.generate_image(img_prompt, filename=f"create_{ts}.png")
            fname = os.path.basename(image_path)
            url = config.get_public_url(f"/media/{fname}")
            self._send_json({"url": url})
        except Exception as e:
            logger.exception("AI image generation failed")
            self._send_json({"error": str(e)})

    def _start_video_generation(self, body: dict, path: str):
        """Start a background video generation job and return a job_id for polling."""
        import secrets as _sec
        video_type = "veo3" if path.endswith("veo3") else "heygen"
        text = body.get("prompt" if video_type == "veo3" else "script", [""])[0].strip()
        if not text:
            text = "AI automation and business intelligence services"
        job_id = _sec.token_urlsafe(12)
        _start_video_job(job_id, video_type, text)
        self._send_json({"job_id": job_id})

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

    def _scheduled_publisher():
        import time as _time
        while True:
            _time.sleep(60)
            try:
                now = datetime.utcnow()
                for d in _list_pending_drafts():
                    sat = d.get("scheduled_at", "").strip()
                    if not sat:
                        continue
                    try:
                        sdt = datetime.fromisoformat(sat).replace(tzinfo=None)
                        if sdt <= now:
                            d["status"] = "approved"
                            _update_draft(d)
                            if _publish_callback:
                                threading.Thread(target=_publish_callback, args=(d,), daemon=True).start()
                            logger.info(f"Auto-published scheduled draft: {d['draft_id']}")
                    except Exception as e:
                        logger.warning(f"Could not process scheduled draft {d.get('draft_id')}: {e}")
            except Exception as e:
                logger.warning(f"Scheduled publisher error: {e}")

    sp = threading.Thread(target=_scheduled_publisher, daemon=True)
    sp.start()
    logger.info("Scheduled post publisher started (checks every 60s)")
    return server
