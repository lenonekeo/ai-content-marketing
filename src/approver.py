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
/* ── CSS Variables — light mode (default) ── */
:root {
  --bg:        #f0f2f5;
  --surface:   #ffffff;
  --surface2:  #f8f9fa;
  --border:    #e0e0e0;
  --border2:   #f0f0f0;
  --nav-bg:    #1a1a2e;
  --text:      #1a1a2e;
  --text2:     #555;
  --text3:     #888;
  --text4:     #bbb;
  --accent:    #2ecc71;
  --accent2:   #27ae60;
  --blue:      #3498db;
  --shadow:    rgba(0,0,0,.07);
  --chat-ai:   #f0f2f5;
  --chat-ai-text: #333;
  --input-bg:  #ffffff;
  --btn-ghost-bg: #f0f2f5;
  --btn-ghost-color: #555;
}
/* ── Dark mode ── */
[data-theme="dark"] {
  --bg:        #0d0d1a;
  --surface:   #1a1a2e;
  --surface2:  #141425;
  --border:    rgba(255,255,255,.1);
  --border2:   rgba(255,255,255,.05);
  --nav-bg:    #090912;
  --text:      #f1f5f9;
  --text2:     #94a3b8;
  --text3:     #64748b;
  --text4:     #475569;
  --accent:    #2ecc71;
  --accent2:   #27ae60;
  --blue:      #60a5fa;
  --shadow:    rgba(0,0,0,.4);
  --chat-ai:   #1e1e35;
  --chat-ai-text: #e2e8f0;
  --input-bg:  #141425;
  --btn-ghost-bg: rgba(255,255,255,.07);
  --btn-ghost-color: #94a3b8;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
       background: var(--bg); min-height: 100vh; color: var(--text);
       transition: background .25s, color .25s; }
nav { background: var(--nav-bg); padding: 0 28px; display: flex; align-items: center;
      height: 58px; position: sticky; top: 0; z-index: 100; gap: 8px; }
.nav-brand { color: #fff; font-weight: 700; font-size: 17px; margin-right: 24px;
             white-space: nowrap; }
.nav-brand span { color: var(--accent); }
.nav-links { display: flex; gap: 4px; }
.nav-links a { color: rgba(255,255,255,.65); text-decoration: none; padding: 7px 14px;
               border-radius: 6px; font-size: 14px; font-weight: 500; transition: all .15s; }
.nav-links a:hover, .nav-links a.active { color: #fff; background: rgba(255,255,255,.12); }
/* Theme toggle button */
#theme-toggle { margin-left: auto; background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.15);
  color: #fff; border-radius: 8px; padding: 6px 12px; font-size: 13px; cursor: pointer;
  display: flex; align-items: center; gap: 6px; transition: background .2s; white-space: nowrap; }
#theme-toggle:hover { background: rgba(255,255,255,.18); }
.nav-signout { color: rgba(255,255,255,.45); font-size: 13px; text-decoration: none;
               padding: 6px 10px; border-radius: 6px; transition: all .15s; white-space: nowrap; }
.nav-signout:hover { color: rgba(255,255,255,.8); background: rgba(255,255,255,.08); }
.container { max-width: 940px; margin: 0 auto; padding: 32px 20px 60px; }
h1 { font-size: 22px; color: var(--text); margin-bottom: 6px; }
.subtitle { color: var(--text3); font-size: 14px; margin-bottom: 28px; }
.card { background: var(--surface); border-radius: 12px; padding: 26px 28px;
        box-shadow: 0 1px 6px var(--shadow); margin-bottom: 20px;
        border: 1px solid var(--border2); transition: background .25s, border-color .25s; }
.card-title { font-size: 14px; font-weight: 700; color: var(--text); text-transform: uppercase;
              letter-spacing: .6px; margin-bottom: 18px; padding-bottom: 12px;
              border-bottom: 1px solid var(--border2); }
.field { margin-bottom: 16px; }
label { display: block; font-weight: 600; font-size: 13px; color: var(--text2); margin-bottom: 6px; }
.hint { font-weight: 400; color: var(--text4); font-size: 12px; margin-left: 4px; }
input[type=text], input[type=password], input[type=number], select, textarea {
  width: 100%; padding: 10px 13px; border: 1px solid var(--border); border-radius: 7px;
  font-size: 14px; color: var(--text); background: var(--input-bg);
  transition: border-color .2s, background .25s; }
input:focus, select:focus, textarea:focus {
  outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(46,204,113,.12); }
textarea { resize: vertical; min-height: 110px; line-height: 1.6; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.btn { padding: 11px 26px; font-size: 14px; font-weight: 600; cursor: pointer;
       border: none; border-radius: 7px; transition: opacity .2s; display: inline-block;
       text-decoration: none; }
.btn:hover { opacity: .85; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-danger { background: #e74c3c; color: #fff; }
.btn-ghost { background: var(--btn-ghost-bg); color: var(--btn-ghost-color); }
.alert { padding: 12px 16px; border-radius: 8px; font-size: 14px; margin-bottom: 20px; }
.alert-success { background: #d5f5e3; color: #1e8449; border: 1px solid #a9dfbf; }
.alert-error { background: #fde8e8; color: #c0392b; border: 1px solid #f5b7b1; }
[data-theme="dark"] .alert-success { background: rgba(46,204,113,.12); color: #4ade80; border-color: rgba(46,204,113,.25); }
[data-theme="dark"] .alert-error { background: rgba(231,76,60,.12); color: #f87171; border-color: rgba(231,76,60,.25); }
.badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
.badge-pending { background: #fef9e7; color: #b7950b; }
.badge-ok { background: #d5f5e3; color: #1e8449; }
.badge-fail { background: #fde8e8; color: #c0392b; }
.badge-none { background: var(--surface2); color: var(--text3); }
[data-theme="dark"] .badge-pending { background: rgba(234,179,8,.12); color: #fbbf24; }
[data-theme="dark"] .badge-ok { background: rgba(46,204,113,.12); color: #4ade80; }
[data-theme="dark"] .badge-fail { background: rgba(231,76,60,.12); color: #f87171; }
.draft-row { display: flex; align-items: center; justify-content: space-between;
             padding: 14px 0; border-bottom: 1px solid var(--border2); gap: 12px; }
.draft-row:last-child { border-bottom: none; }
.draft-meta { font-size: 13px; color: var(--text3); margin-top: 3px; }
.log-row { padding: 12px 0; border-bottom: 1px solid var(--border2); font-size: 13px; }
.log-row:last-child { border-bottom: none; }
.log-title { font-weight: 600; color: var(--text); margin-bottom: 4px; }
.log-detail { color: var(--text3); }
.empty { color: var(--text4); font-size: 14px; padding: 20px 0; text-align: center; }
.section-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 20px; }
.day-cb { display:inline-flex; align-items:center; justify-content:center;
          width:52px; height:40px; border:1.5px solid var(--border); border-radius:7px;
          cursor:pointer; font-weight:600; font-size:13px; color:var(--text3);
          transition: all .15s; user-select:none; }
.day-cb:has(input:checked) { background:var(--accent); border-color:var(--accent); color:#fff; }
.day-cb input { display:none; }
.cal-day-group { margin-bottom:20px; }
.cal-date { font-weight:700; font-size:13px; color:var(--text); padding:8px 0 6px;
            border-bottom:2px solid var(--border2); margin-bottom:8px; letter-spacing:.3px; }
.cal-entry { display:flex; gap:14px; padding:8px 0; border-bottom:1px solid var(--border2);
             align-items:flex-start; }
.cal-entry:last-child { border-bottom:none; }
.cal-time { font-size:12px; font-weight:600; color:var(--text4); min-width:64px;
            padding-top:3px; white-space:nowrap; }
.cal-info { flex:1; font-size:13px; }
.cal-preview { color:var(--text3); font-size:12px; margin-top:3px; font-style:italic; }
@keyframes spin { from { transform:rotate(0deg) } to { transform:rotate(360deg) } }
.spinner { display:inline-block; width:28px; height:28px; border:3px solid var(--border);
           border-top-color:var(--accent); border-radius:50%; animation:spin .8s linear infinite; }
@media (max-width: 620px) {
  .grid-2, .grid-3 { grid-template-columns: 1fr; }
  nav { padding: 0 16px; }
  .nav-brand { font-size: 15px; margin-right: 12px; }
  .nav-links a { padding: 6px 10px; font-size: 13px; }
}
.plt-row { display:flex; gap:10px; flex-wrap:wrap; }
.plt-chk { display:inline-flex; align-items:center; gap:8px; padding:9px 16px;
           border:1.5px solid var(--border); border-radius:8px; cursor:pointer;
           font-weight:600; font-size:13px; color:var(--text3); transition:all .15s;
           user-select:none; }
.plt-chk:has(input:checked) { border-color:var(--accent); background:rgba(46,204,113,.08); color:var(--accent2); }
.plt-chk input { display:none; }
.type-row { display:flex; gap:8px; }
.type-lbl { display:inline-flex; align-items:center; gap:6px; padding:7px 14px;
            border:1.5px solid var(--border); border-radius:8px; cursor:pointer;
            font-size:13px; font-weight:600; color:var(--text3); transition:all .15s;
            user-select:none; }
.type-lbl:has(input:checked) { border-color:var(--blue); background:rgba(52,152,219,.08); color:var(--blue); }
.type-lbl input { display:none; }
details.content-expand { margin-top:5px; }
details.content-expand summary { cursor:pointer; color:var(--accent); font-size:12px;
  font-weight:600; list-style:none; display:inline-block; }
details.content-expand summary::-webkit-details-marker { display:none; }
.post-text-box { background:var(--surface2); border-radius:6px; padding:12px 14px;
  font-size:13px; color:var(--text2); line-height:1.6; white-space:pre-wrap;
  margin-top:8px; max-height:340px; overflow-y:auto; border:1px solid var(--border); }
.img-preview-box img { max-width:100%; max-height:280px; border-radius:8px;
  display:none; border:1px solid var(--border); margin-top:10px; }
.chat-window { height:420px; overflow-y:auto; padding:16px 0; display:flex;
  flex-direction:column; gap:14px; }
.chat-msg { display:flex; gap:10px; align-items:flex-start; }
.chat-msg.user { flex-direction:row-reverse; }
.chat-bubble { max-width:80%; padding:11px 15px; border-radius:12px;
  font-size:14px; line-height:1.6; white-space:pre-wrap; }
.chat-msg.user .chat-bubble { background:var(--accent); color:#fff; border-bottom-right-radius:3px; }
.chat-msg.ai .chat-bubble { background:var(--chat-ai); color:var(--chat-ai-text); border-bottom-left-radius:3px; }
.chat-avatar { width:32px; height:32px; border-radius:50%; flex-shrink:0;
  display:flex; align-items:center; justify-content:center; font-size:14px; font-weight:700; }
.chat-msg.user .chat-avatar { background:var(--accent); color:#fff; }
.chat-msg.ai .chat-avatar { background:var(--nav-bg); color:#fff; }
.chat-input-row { display:flex; gap:10px; margin-top:12px; }
.chat-input-row textarea { flex:1; resize:none; min-height:60px; max-height:120px; }
.use-this-btn { font-size:11px; padding:4px 10px; margin-top:6px; cursor:pointer;
  background:var(--btn-ghost-bg); border:1px solid var(--border); border-radius:6px;
  color:var(--text2); font-weight:600; transition:all .15s; }
.use-this-btn:hover { background:var(--accent); color:#fff; border-color:var(--accent); }
"""


def _head(title: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — MakOne BI</title>
<style>{_STYLES}</style>
<script>
// Apply saved theme before page renders (prevents flash)
(function(){{
  var t = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', t);
}})();
</script>
</head><body>"""


def _nav(active: str = "") -> str:
    pages = [("/", "Dashboard"), ("/create", "Create"), ("/render", "🎬 Render"), ("/setup", "Setup"), ("/influence", "Content Influence"), ("/calendar", "Calendar")]
    links = "".join(
        '<a href="{}" class="{}">{}</a>'.format(href, "active" if active == href else "", name)
        for href, name in pages
    )
    return f"""<nav>
  <div class="nav-brand">MakOne <span>BI</span></div>
  <div class="nav-links">{links}</div>
  <button id="theme-toggle" onclick="toggleTheme()" title="Toggle dark/light mode">
    <span id="theme-icon">🌙</span> <span id="theme-label">Dark</span>
  </button>
  <a href="/logout" class="nav-signout">Sign out</a>
</nav>
<script>
(function(){{
  var t = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', t);
  var icon = document.getElementById('theme-icon');
  var label = document.getElementById('theme-label');
  if (icon) icon.textContent = t === 'dark' ? '☀️' : '🌙';
  if (label) label.textContent = t === 'dark' ? 'Light' : 'Dark';
}})();
function toggleTheme() {{
  var current = document.documentElement.getAttribute('data-theme') || 'light';
  var next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  document.getElementById('theme-icon').textContent = next === 'dark' ? '☀️' : '🌙';
  document.getElementById('theme-label').textContent = next === 'dark' ? 'Light' : 'Dark';
}}
</script>"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


# ---------------------------------------------------------------------------
# Remotion render jobs
# ---------------------------------------------------------------------------

_render_jobs: dict = {}  # job_id -> {status, output, error}

REMOTION_COMPOSITIONS = [
    {"id": "PostCard",       "label": "Post Card",        "desc": "Animated social media post card (1080×1080, 8s)",  "props_hint": '{"text":"Your post text here","businessName":"MakOne BI","website":"makone-bi.com"}'},
    {"id": "Intro",          "label": "YouTube Intro",    "desc": "Branded intro clip (1920×1080, 3s)",               "props_hint": '{"businessName":"MakOne BI","tagline":"AI Automation Experts"}'},
    {"id": "Outro",          "label": "YouTube Outro",    "desc": "CTA outro clip (1920×1080, 6s)",                   "props_hint": '{"businessName":"MakOne BI","website":"makone-bi.com","ctaText":"Book a free discovery call"}'},
    {"id": "ProductLaunch",  "label": "Product Launch",   "desc": "Full product launch video (1920×1080, 25s)",       "props_hint": '{}'},
    {"id": "AvatarShowcase", "label": "Avatar Showcase",  "desc": "HeyGen avatar + app screenshots (1920×1080, 14s)", "props_hint": '{}'},
]


def _start_render_job(job_id: str, composition: str, props: str):
    import threading, subprocess, os, datetime as _dt
    remotion_dir = os.path.join(os.path.dirname(__file__), '..', 'remotion')
    remotion_dir = os.path.abspath(remotion_dir)
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(remotion_dir, "out", f"{composition}_{ts}.mp4")
    os.makedirs(os.path.join(remotion_dir, "out"), exist_ok=True)

    def _run():
        try:
            cmd = ["npx", "remotion", "render", "src/index.jsx", composition, out_file, "--gl=swiftshader"]
            if props and props.strip() not in ('{}', ''):
                cmd.append(f"--props={props}")
            result = subprocess.run(cmd, cwd=remotion_dir, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                _render_jobs[job_id] = {"status": "error", "error": result.stderr[-800:]}
            else:
                fname = os.path.basename(out_file)
                # Copy to downloads/ so /media/ can serve it
                import shutil
                from config import config as _cfg
                dl_path = os.path.join(os.path.dirname(__file__), '..', _cfg.downloads_dir, fname)
                shutil.copy2(out_file, dl_path)
                _render_jobs[job_id] = {"status": "done", "url": _cfg.get_public_url(f"/media/{fname}"), "filename": fname}
        except Exception as e:
            _render_jobs[job_id] = {"status": "error", "error": str(e)}

    _render_jobs[job_id] = {"status": "pending"}
    threading.Thread(target=_run, daemon=True).start()


def _page_render() -> str:
    comp_cards = ""
    for c in REMOTION_COMPOSITIONS:
        comp_cards += f"""
    <div class="card" style="margin-bottom:16px">
      <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
        <div style="flex:1;min-width:200px">
          <div style="font-weight:700;font-size:16px;color:#1e293b">{c['label']}</div>
          <div style="font-size:13px;color:#64748b;margin-top:4px">{c['desc']}</div>
        </div>
        <div style="flex:2;min-width:260px">
          <input type="text" id="props-{c['id']}" value='{c['props_hint']}' placeholder='Props JSON'
            style="width:100%;font-family:monospace;font-size:12px;padding:8px 10px;border:1px solid #e2e8f0;border-radius:8px;box-sizing:border-box">
        </div>
        <button class="btn btn-ghost" onclick="startRender('{c['id']}')" id="btn-{c['id']}" style="white-space:nowrap">
          ▶ Render
        </button>
      </div>
      <div id="status-{c['id']}" style="margin-top:10px;font-size:13px;color:#64748b;display:none"></div>
    </div>"""

    return _head("Render Video") + _nav("/render") + f"""
<div class="container">
  <h1>🎬 Render Remotion Video</h1>
  <p class="subtitle">Generate MP4 videos from your Remotion compositions — renders on the server, download when done.</p>
  {comp_cards}
</div>
<script>
async function startRender(id) {{
  const props = document.getElementById('props-' + id).value.trim();
  const btn = document.getElementById('btn-' + id);
  const status = document.getElementById('status-' + id);
  btn.disabled = true;
  status.style.display = 'block';
  status.textContent = '⏳ Rendering... (this may take a few minutes)';
  try {{
    const resp = await fetch('/render/start', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
      body: 'composition=' + encodeURIComponent(id) + '&props=' + encodeURIComponent(props)
    }});
    const data = await resp.json();
    if (data.error) {{ status.textContent = '❌ ' + data.error; btn.disabled = false; return; }}
    const jobId = data.job_id;
    let polls = 0;
    const poll = setInterval(async () => {{
      polls++;
      const sr = await fetch('/render/status?job_id=' + encodeURIComponent(jobId));
      const sd = await sr.json();
      if (sd.status === 'done') {{
        clearInterval(poll);
        btn.disabled = false;
        status.innerHTML = '✅ Done! <a href="' + sd.url + '" download style="color:#4f8ef7;font-weight:700">⬇ Download ' + sd.filename + '</a>';
      }} else if (sd.status === 'error') {{
        clearInterval(poll);
        btn.disabled = false;
        status.textContent = '❌ Error: ' + sd.error;
      }} else {{
        status.textContent = '⏳ Rendering... (' + (polls * 5) + 's elapsed)';
      }}
      if (polls > 120) {{ clearInterval(poll); btn.disabled = false; status.textContent = '⚠️ Timed out — check server logs'; }}
    }}, 5000);
  }} catch(e) {{
    status.textContent = '❌ ' + e.message;
    btn.disabled = false;
  }}
}}
</script>
"""


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
            img_url = d.get("image_url", "")
            vid_url = d.get("video_url", "")
            thumb_html = ""
            if img_url:
                thumb_html += f'<img src="{_esc(img_url)}" style="height:48px;width:72px;object-fit:cover;border-radius:4px;border:1px solid #e0e0e0;margin-right:6px">'
            if vid_url:
                thumb_html += '<span style="display:inline-flex;align-items:center;justify-content:center;height:48px;width:72px;background:#f0f0f0;border-radius:4px;border:1px solid #e0e0e0;font-size:20px;margin-right:6px">🎬</span>'
            drafts_html += f"""
<div class="draft-row">
  <div style="display:flex;align-items:center;gap:10px">
    {thumb_html}
    <div>
      <strong>{theme}</strong> &nbsp;<span class="badge badge-pending">Pending</span>
      <div class="draft-meta">{industry} &nbsp;·&nbsp; {ts}</div>
    </div>
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


def _build_user_management_html(current_username: str) -> str:
    """Build the admin-only user management card HTML."""
    from src import user_store as _us
    current_user = _us.get_by_username(current_username)
    if not current_user or current_user.get("role") != "admin":
        return ""

    users = _us.get_all()
    rows = ""
    for u in users:
        uname = _esc(u["username"])
        email = _esc(u.get("email", ""))
        role = _esc(u.get("role", "user"))
        status = u.get("status", "active")
        created = _esc(u.get("created_at", "")[:10])
        is_self = u["username"] == current_username

        status_badge = (
            '<span style="color:#16a34a;font-weight:600">Active</span>' if status == "active"
            else '<span style="color:#b45309;font-weight:600">Pending</span>'
        )
        role_badge = (
            '<span style="color:#7c3aed;font-weight:600">Admin</span>' if role == "admin"
            else '<span style="color:#64748b">User</span>'
        )

        approve_btn = ""
        if status == "pending":
            approve_btn = f'<form method="POST" action="/setup/users/approve" style="display:inline"><input type="hidden" name="username" value="{uname}"><button class="btn btn-ghost" style="font-size:12px;padding:4px 10px" type="submit">Approve</button></form> '

        delete_btn = ""
        if not is_self:
            delete_btn = f'<form method="POST" action="/setup/users/delete" style="display:inline" onsubmit="return confirm(\'Delete user {uname}?\')"><input type="hidden" name="username" value="{uname}"><button class="btn btn-danger" style="font-size:12px;padding:4px 10px" type="submit">Delete</button></form>'

        rows += f"""
        <tr>
          <td><strong>{uname}</strong>{"&nbsp;👤" if is_self else ""}</td>
          <td style="color:#64748b">{email}</td>
          <td>{role_badge}</td>
          <td>{status_badge}</td>
          <td style="color:#94a3b8">{created}</td>
          <td>{approve_btn}{delete_btn}</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:#94a3b8">No users yet</td></tr>'

    pending_count = sum(1 for u in users if u.get("status") == "pending")
    pending_note = f' <span style="background:#fef9e7;color:#b45309;border-radius:12px;padding:2px 8px;font-size:12px">{pending_count} pending</span>' if pending_count else ""

    return f"""
  <div class="card" style="margin-top:24px">
    <div class="card-title">👥 User Management{pending_note}</div>
    <p style="font-size:14px;color:#64748b;margin-bottom:16px">
      Approve or remove users who have signed up. Pending accounts cannot log in until approved.
    </p>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:14px">
        <thead>
          <tr style="border-bottom:2px solid var(--border)">
            <th style="text-align:left;padding:8px 12px">Username</th>
            <th style="text-align:left;padding:8px 12px">Email</th>
            <th style="text-align:left;padding:8px 12px">Role</th>
            <th style="text-align:left;padding:8px 12px">Status</th>
            <th style="text-align:left;padding:8px 12px">Created</th>
            <th style="text-align:left;padding:8px 12px">Actions</th>
          </tr>
        </thead>
        <tbody>{rows}
        </tbody>
      </table>
    </div>
  </div>"""


def _page_setup(alert: str = "", alert_type: str = "success", current_username: str = "") -> str:
    env = _read_env()

    def val(key, default=""):
        return _esc(env.get(key, default))

    def masked(key):
        return "••••••••" if env.get(key) else ""

    alert_html = f'<div class="alert alert-{alert_type}">{alert}</div>' if alert else ""
    user_mgmt_html = _build_user_management_html(current_username)

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
          <label>Avatar ID <span class="hint">use the ID from "List My Avatars" below</span></label>
          <input type="text" id="heygen_avatar_id_input" name="HEYGEN_AVATAR_ID" value="{val("HEYGEN_AVATAR_ID")}">
        </div>
        <div class="field">
          <label>Voice ID</label>
          <input type="text" name="HEYGEN_VOICE_ID" value="{val("HEYGEN_VOICE_ID")}">
        </div>
      </div>
      <div style="margin-top:12px">
        <button type="button" class="btn btn-ghost" onclick="listHeygenAvatars()" style="font-size:13px">
          🔍 List My Avatars
        </button>
        <span id="heygen-list-status" style="font-size:13px;color:#888;margin-left:10px"></span>
      </div>
      <div id="heygen-avatars-result" style="display:none;margin-top:12px;background:#f8f9fa;border-radius:8px;padding:14px;border:1px solid #e0e0e0;font-size:13px"></div>
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
      <div class="grid-2" style="margin-top:12px">
        <div class="field">
          <label>Client ID <span class="hint">from LinkedIn Developer App</span></label>
          <input type="text" name="LINKEDIN_CLIENT_ID" value="{val("LINKEDIN_CLIENT_ID")}">
        </div>
        <div class="field">
          <label>Client Secret <span class="hint">leave blank to keep current</span></label>
          <input type="password" name="LINKEDIN_CLIENT_SECRET" placeholder="{masked("LINKEDIN_CLIENT_SECRET") or "..."}">
        </div>
      </div>
      <div style="margin-top:12px">
        <a href="/setup/linkedin/connect" class="btn btn-ghost" style="font-size:13px">Connect LinkedIn</a>
        <span style="font-size:12px;color:#aaa;margin-left:10px">Requires HTTPS â€” start your Cloudflare tunnel and set PUBLIC_BASE_URL first.</span>
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
      <div class="grid-2" style="margin-top:12px">
        <div class="field">
          <label>App ID <span class="hint">from Facebook Developer App</span></label>
          <input type="text" name="FACEBOOK_APP_ID" value="{val("FACEBOOK_APP_ID")}">
        </div>
        <div class="field">
          <label>App Secret <span class="hint">leave blank to keep current</span></label>
          <input type="password" name="FACEBOOK_APP_SECRET" placeholder="{masked("FACEBOOK_APP_SECRET") or "..."}">
        </div>
      </div>
      <div style="margin-top:12px">
        <a href="/setup/facebook/connect" class="btn btn-ghost" style="font-size:13px">Connect Facebook & Instagram</a>
        <span style="font-size:12px;color:#aaa;margin-left:10px">Saves permanent Page token + Instagram ID automatically. Requires HTTPS.</span>
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
      <div class="card-title">YouTube</div>
      <div class="grid-2">
        <div class="field">
          <label>Client ID</label>
          <input type="text" name="YOUTUBE_CLIENT_ID" value="{val("YOUTUBE_CLIENT_ID")}">
        </div>
        <div class="field">
          <label>Client Secret <span class="hint">leave blank to keep current</span></label>
          <input type="password" name="YOUTUBE_CLIENT_SECRET" placeholder="{masked("YOUTUBE_CLIENT_SECRET") or "GOCSPX-..."}">
        </div>
      </div>
      <div class="grid-2">
        <div class="field">
          <label>Refresh Token <span class="hint">leave blank to keep current</span></label>
          <input type="password" name="YOUTUBE_REFRESH_TOKEN" placeholder="{masked("YOUTUBE_REFRESH_TOKEN") or "1//0A..."}">
        </div>
        <div class="field">
          <label>Privacy</label>
          <select name="YOUTUBE_PRIVACY">
            <option value="public" {"selected" if env.get("YOUTUBE_PRIVACY","public")=="public" else ""}>Public</option>
            <option value="unlisted" {"selected" if env.get("YOUTUBE_PRIVACY","public")=="unlisted" else ""}>Unlisted</option>
            <option value="private" {"selected" if env.get("YOUTUBE_PRIVACY","public")=="private" else ""}>Private</option>
          </select>
        </div>
      </div>
      <div style="margin-top:12px">
        <a href="/setup/youtube/connect" class="btn btn-ghost" style="font-size:13px">Connect YouTube</a>
        <span style="font-size:12px;color:#aaa;margin-left:10px">Or manually paste the Refresh Token above.</span>
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

  <!-- Login & Access — separate form with password confirmation -->
  <form method="POST" action="/account" id="account-form">
    <div class="card" style="margin-top:24px">
      <div class="card-title">🔐 Login &amp; Access</div>
      <p style="font-size:14px;color:#64748b;margin-bottom:20px">
        Change the username and password used to access this app.
        You must enter your current password to save changes.
      </p>
      <div class="grid-2">
        <div class="field">
          <label>Username</label>
          <input type="text" name="username" value="{val("APP_USERNAME", "admin")}" autocomplete="username">
        </div>
        <div class="field">
          <label>Current Password <span class="hint">required to save</span></label>
          <input type="password" name="current_password" placeholder="Enter current password" autocomplete="current-password">
        </div>
      </div>
      <div class="grid-2">
        <div class="field">
          <label>New Password <span class="hint">leave blank to keep current</span></label>
          <input type="password" name="new_password" id="new_password" placeholder="New password" autocomplete="new-password"
            oninput="checkPasswords()">
        </div>
        <div class="field">
          <label>Confirm New Password</label>
          <input type="password" name="confirm_password" id="confirm_password" placeholder="Repeat new password" autocomplete="new-password"
            oninput="checkPasswords()">
          <span id="pw-match" style="font-size:12px;margin-top:4px;display:block"></span>
        </div>
      </div>
      <div class="section-actions" style="margin-top:8px">
        <button type="submit" class="btn btn-primary" id="account-btn">Update Login</button>
      </div>
    </div>
  </form>

  {user_mgmt_html}

<script>
function checkPasswords() {{
  const np = document.getElementById("new_password").value;
  const cp = document.getElementById("confirm_password").value;
  const msg = document.getElementById("pw-match");
  const btn = document.getElementById("account-btn");
  if (!np && !cp) {{ msg.textContent = ""; return; }}
  if (np === cp) {{
    msg.textContent = "✓ Passwords match";
    msg.style.color = "#16a34a";
    btn.disabled = false;
  }} else {{
    msg.textContent = "✗ Passwords do not match";
    msg.style.color = "#dc2626";
    btn.disabled = true;
  }}
}}

function _avCard(id, name, imgUrl) {{
  const img = imgUrl
    ? `<img src="${{imgUrl}}" style="width:80px;height:80px;object-fit:cover;border-radius:8px;margin-bottom:6px;display:block">`
    : `<div style="width:80px;height:80px;background:#e0e0e0;border-radius:8px;margin-bottom:6px;display:flex;align-items:center;justify-content:center;font-size:28px">👤</div>`;
  return `<div onclick="document.getElementById('heygen_avatar_id_input').value='${{id}}';document.querySelectorAll('.av-card').forEach(c=>{{c.style.border='1px solid #e0e0e0';c.style.background=''}});this.style.border='2px solid #2ecc71';this.style.background='#f0fff4'"
    class="av-card" title="${{id}}" style="cursor:pointer;padding:10px;border:1px solid #e0e0e0;border-radius:8px;width:110px;text-align:center;font-size:12px;transition:all .15s;flex-shrink:0">
    ${{img}}
    <div style="font-weight:600;color:#333;font-size:11px;line-height:1.3;margin-bottom:3px;word-break:break-word">${{name}}</div>
    <div style="color:#2980b9;font-family:monospace;font-size:9px;word-break:break-all">${{id.slice(0,14)}}...</div>
  </div>`;
}}

async function listHeygenAvatars() {{
  const statusEl = document.getElementById("heygen-list-status");
  const resultEl = document.getElementById("heygen-avatars-result");
  statusEl.textContent = "Fetching your AI clones and looks...";
  resultEl.style.display = "none";
  try {{
    const resp = await fetch("/setup/heygen/avatars");
    const data = await resp.json();
    if (data.error) {{
      statusEl.textContent = "Error: " + data.error;
      return;
    }}
    const groups = data.groups || [];
    if (!groups.length) {{
      statusEl.textContent = "No avatar groups found. Check your HeyGen account.";
      return;
    }}
    let totalLooks = groups.reduce((n, g) => n + (g.looks || []).length, 0);
    statusEl.textContent = totalLooks + " avatar(s) found. Click one to use it:";
    let html = "";
    let lastSection = "";
    for (const g of groups) {{
      if (g.section !== lastSection) {{
        lastSection = g.section;
        const icon = g.section === "My AI Clones" ? "🧬" : "🎭";
        html += `<div style="font-size:13px;font-weight:700;color:#555;margin:12px 0 6px;border-bottom:2px solid #e0e0e0;padding-bottom:4px">${{icon}} ${{g.section}}</div>`;
      }}
      html += `<div style="margin-bottom:18px">`;
      if (g.group_name !== "Stock Avatars") {{
        html += `<div style="font-weight:600;font-size:12px;color:#1a1a2e;margin-bottom:8px">👤 ${{g.group_name}} <span style="font-weight:400;color:#aaa;font-size:11px">(${{g.looks.length}} look(s))</span></div>`;
      }}
      html += `<div style="display:flex;flex-wrap:wrap;gap:10px">`;
      if (!g.looks.length) {{
        html += `<p style="color:#aaa;font-size:12px">No looks found.</p>`;
      }}
      for (const lk of g.looks) {{
        const lkId = lk.id || "";
        const lkName = lk.name || "(unnamed)";
        const lkImg = lk.image_url || "";
        html += _avCard(lkId, lkName, lkImg);
      }}
      html += `</div></div>`;
    }}
    html += `<p style="margin-top:8px;color:#888;font-size:12px">Click a look card to fill in the Avatar ID field above, then Save Settings.</p>`;
    resultEl.innerHTML = html;
    resultEl.style.display = "block";
  }} catch(e) {{
    statusEl.textContent = "Request failed: " + e.message;
  }}
}}
</script>
</body></html>"""


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
    remotion_btn = (
        '''<div class="remotion-dropdown" style="position:relative;display:inline-block">
          <button class="btn btn-ghost" onclick="toggleRemotionMenu(event)" id="remotion-btn" style="display:flex;align-items:center;gap:6px">
            &#127916; Remotion <span style="font-size:10px">&#9660;</span>
          </button>
          <div id="remotion-menu" style="display:none;position:absolute;top:110%;left:0;background:#fff;border:1px solid #e2e8f0;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.12);z-index:999;min-width:220px;overflow:hidden">
            <div style="padding:8px 12px;font-size:11px;font-weight:700;color:#94a3b8;letter-spacing:1px;border-bottom:1px solid #f1f5f9">PICK COMPOSITION</div>
            <div onclick="generateVideo(\'remotion\',\'PostCard\')"       style="padding:10px 16px;cursor:pointer;font-size:13px;font-weight:600" onmouseover="this.style.background=\'#f8fafc\'" onmouseout="this.style.background=\'\'">&#127916; Post Card <span style="font-size:11px;color:#94a3b8;font-weight:400">— animated post (1080×1080)</span></div>
            <div onclick="generateVideo(\'remotion\',\'Intro\')"           style="padding:10px 16px;cursor:pointer;font-size:13px;font-weight:600" onmouseover="this.style.background=\'#f8fafc\'" onmouseout="this.style.background=\'\'">&#9654; YouTube Intro <span style="font-size:11px;color:#94a3b8;font-weight:400">— branded 3s clip</span></div>
            <div onclick="generateVideo(\'remotion\',\'Outro\')"           style="padding:10px 16px;cursor:pointer;font-size:13px;font-weight:600" onmouseover="this.style.background=\'#f8fafc\'" onmouseout="this.style.background=\'\'">&#127937; YouTube Outro <span style="font-size:11px;color:#94a3b8;font-weight:400">— CTA 6s clip</span></div>
            <div onclick="generateVideo(\'remotion\',\'ProductLaunch\')"   style="padding:10px 16px;cursor:pointer;font-size:13px;font-weight:600" onmouseover="this.style.background=\'#f8fafc\'" onmouseout="this.style.background=\'\'">&#128640; Product Launch <span style="font-size:11px;color:#94a3b8;font-weight:400">— full 25s video</span></div>
            <div onclick="generateVideo(\'remotion\',\'AvatarShowcase\')"  style="padding:10px 16px;cursor:pointer;font-size:13px;font-weight:600;border-top:1px solid #f1f5f9" onmouseover="this.style.background=\'#f8fafc\'" onmouseout="this.style.background=\'\'">&#129302; Avatar Showcase <span style="font-size:11px;color:#94a3b8;font-weight:400">— avatar + app (14s)</span></div>
          </div>
        </div>'''
        if _cfg.remotion_enabled else
        '<button class="btn btn-ghost" disabled title="Set REMOTION_ENABLED=true to enable">Remotion (not enabled)</button>'
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
          <label class="plt-chk"><input type="checkbox" id="plt-youtube"> YouTube</label>
          <label class="plt-chk"><input type="checkbox" id="plt-heygen"> HeyGen Video</label>
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
      <div id="media-previews" style="display:none;margin-top:20px;border-top:1px solid #eee;padding-top:16px">
        <div style="font-weight:600;font-size:14px;margin-bottom:12px;color:#333">Generated Media</div>
        <div style="display:flex;gap:16px;flex-wrap:wrap">
          <div id="prev-image-wrap" style="display:none;flex:1;min-width:200px">
            <div style="font-size:12px;font-weight:600;color:#888;margin-bottom:6px">AI IMAGE</div>
            <img id="prev-image" src="" style="max-width:100%;border-radius:8px;border:1px solid #e0e0e0">
          </div>
          <div id="prev-video-wrap" style="display:none;flex:1;min-width:200px">
            <div id="prev-video-label" style="font-size:12px;font-weight:600;color:#888;margin-bottom:6px">VIDEO</div>
            <video id="prev-video" controls style="max-width:100%;border-radius:8px;max-height:220px"></video>
          </div>
        </div>
      </div>
      <div id="media-previews" style="display:none;margin-top:20px;border-top:1px solid #eee;padding-top:16px">
        <div style="font-weight:600;font-size:14px;margin-bottom:12px;color:#333">Generated Media</div>
        <div style="display:flex;gap:16px;flex-wrap:wrap">
          <div id="prev-image-wrap" style="display:none;flex:1;min-width:220px">
            <div style="font-size:12px;font-weight:600;color:#888;margin-bottom:6px">AI IMAGE</div>
            <img id="prev-image" src="" style="max-width:100%;border-radius:8px;border:1px solid #e0e0e0">
          </div>
          <div id="prev-veo3-wrap" style="display:none;flex:1;min-width:220px">
            <div style="font-size:12px;font-weight:600;color:#888;margin-bottom:6px">VEO3 VIDEO</div>
            <video id="prev-veo3" controls style="max-width:100%;border-radius:8px;max-height:220px"></video>
          </div>
          <div id="prev-heygen-wrap" style="display:none;flex:1;min-width:220px">
            <div style="font-size:12px;font-weight:600;color:#888;margin-bottom:6px">AI CLONE (HEYGEN)</div>
            <video id="prev-heygen" controls style="max-width:100%;border-radius:8px;max-height:220px"></video>
          </div>
          <div id="prev-remotion-wrap" style="display:none;flex:1;min-width:220px">
            <div style="font-size:12px;font-weight:600;color:#888;margin-bottom:6px" id="prev-remotion-label">🎬 REMOTION</div>
            <video id="prev-remotion" controls style="max-width:100%;border-radius:8px;max-height:220px"></video>
          </div>
        </div>
      </div>
      <div style="margin-top:10px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        {veo3_btn}
        {heygen_btn}
        {remotion_btn}
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
  return ["linkedin","facebook","instagram","youtube","heygen"].filter(p => document.getElementById("plt-"+p).checked);
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

function showDraftSection(fallbackText) {{
  // Use the last AI-generated draft text (formatted social post); fall back to the passed text
  const text = _draftTexts.length > 0 ? _draftTexts[_draftTexts.length - 1] : fallbackText;
  const platforms = getSelectedPlatforms();
  document.getElementById("li-field").style.display = platforms.includes("linkedin") ? "" : "none";
  document.getElementById("fb-field").style.display = platforms.includes("facebook") ? "" : "none";
  document.getElementById("ig-field").style.display = platforms.includes("instagram") ? "" : "none";
  if (platforms.includes("linkedin")) document.getElementById("linkedin_text").value = text;
  if (platforms.includes("facebook")) document.getElementById("facebook_text").value = text;
  if (platforms.includes("instagram")) document.getElementById("instagram_caption").value = text;
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
      document.getElementById("prev-image").src = data.url;
      document.getElementById("prev-image-wrap").style.display = "block";
      document.getElementById("media-previews").style.display = "block";
      document.getElementById("prev-image").src = data.url;
      document.getElementById("prev-image-wrap").style.display = "block";
      document.getElementById("media-previews").style.display = "block";
      document.getElementById("prev-image").src = data.url;
      document.getElementById("prev-image-wrap").style.display = "block";
      document.getElementById("media-previews").style.display = "block";
      document.getElementById("prev-image").src = data.url;
      document.getElementById("prev-image-wrap").style.display = "block";
      document.getElementById("media-previews").style.display = "block";
      document.getElementById("prev-image").src = data.url;
      document.getElementById("prev-image-wrap").style.display = "block";
      document.getElementById("media-previews").style.display = "block";
      document.getElementById("prev-image").src = data.url;
      document.getElementById("prev-image-wrap").style.display = "block";
      document.getElementById("media-previews").style.display = "block";
      document.getElementById("prev-image").src = data.url;
      document.getElementById("prev-image-wrap").style.display = "block";
      document.getElementById("media-previews").style.display = "block";
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

function toggleRemotionMenu(event) {{
  event.stopPropagation();
  const menu = document.getElementById("remotion-menu");
  menu.style.display = menu.style.display === "none" ? "block" : "none";
  document.addEventListener("click", function _close() {{
    menu.style.display = "none";
    document.removeEventListener("click", _close);
  }}, {{once: true}});
}}

async function generateVideo(type, composition) {{
  // Close remotion dropdown if open
  const rmenu = document.getElementById("remotion-menu");
  if (rmenu) rmenu.style.display = "none";

  const lastMsg = messages.length > 0 ? messages[messages.length-1].content : "";
  const chatInput = document.getElementById("chat-input").value.trim();
  const script = lastMsg || chatInput || "AI automation and business intelligence services";
  const spinner = document.getElementById("vid-spinner");
  const status = document.getElementById("vid-status");
  const veo3Btn = document.getElementById("veo3-btn");
  const heygenBtn = document.getElementById("heygen-btn");
  const remotionBtn = document.getElementById("remotion-btn");

  function _endJob() {{
    spinner.style.display = "none";
    if (veo3Btn) veo3Btn.disabled = false;
    if (heygenBtn) heygenBtn.disabled = false;
    if (remotionBtn) remotionBtn.disabled = false;
  }}

  spinner.style.display = "inline-flex";
  if (type === "veo3") {{
    status.textContent = "Submitting to VEO 3...";
  }} else if (type === "remotion" && composition === "AvatarShowcase") {{
    status.textContent = "🤖 Starting Avatar Showcase pipeline (HeyGen + screenshots + render — keep this page open)...";
  }} else if (type === "remotion") {{
    status.textContent = "🎬 Rendering " + (composition || "PostCard") + "...";
  }} else {{
    status.textContent = "Submitting to HeyGen...";
  }}
  if (veo3Btn) veo3Btn.disabled = true;
  if (heygenBtn) heygenBtn.disabled = true;
  if (remotionBtn) remotionBtn.disabled = true;

  // Extract the last URL mentioned anywhere in the chat conversation
  function _lastChatUrl() {{
    const urlRe = /https?:\/\/[^\s"'<>)]+/g;
    for (let i = messages.length - 1; i >= 0; i--) {{
      const found = (messages[i].content || "").match(urlRe);
      if (found && found.length > 0) return found[found.length - 1];
    }}
    return "";
  }}

  try {{
    let bodyStr;
    if (type === "veo3") {{
      bodyStr = "prompt=" + encodeURIComponent(script);
    }} else if (type === "remotion") {{
      const screenshotUrl = composition === "AvatarShowcase" ? _lastChatUrl() : "";
      bodyStr = "script=" + encodeURIComponent(script) +
                "&composition=" + encodeURIComponent(composition || "PostCard") +
                (screenshotUrl ? "&screenshot_url=" + encodeURIComponent(screenshotUrl) : "");
    }} else {{
      bodyStr = "script=" + encodeURIComponent(script);
    }}
    const resp = await fetch("/create/video/" + type, {{
      method: "POST",
      headers: {{"Content-Type": "application/x-www-form-urlencoded"}},
      body: bodyStr
    }});
    const data = await resp.json();
    if (data.error) {{
      status.textContent = "Error: " + data.error;
      _endJob();
      return;
    }}
    const jobId = data.job_id;
    if (type === "veo3") {{
      status.textContent = "⏳ VEO 3 generating (~2 min)...";
    }} else if (type === "remotion") {{
      status.textContent = "⏳ Rendering " + (composition || "PostCard") + " (1–3 min)...";
    }} else {{
      status.textContent = "⏳ HeyGen generating avatar (5–20 min — keep this page open)...";
    }}
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
          document.getElementById("media-previews").style.display = "block";
          if (type === "veo3") {{
            document.getElementById("prev-veo3").src = sd.url;
            document.getElementById("prev-veo3-wrap").style.display = "block";
          }} else if (type === "remotion") {{
            const compLabel = composition || "PostCard";
            document.getElementById("prev-remotion-label").textContent = "🎬 REMOTION — " + compLabel.toUpperCase();
            document.getElementById("prev-remotion").src = sd.url;
            document.getElementById("prev-remotion-wrap").style.display = "block";
            showDraftSection(script);
          }} else {{
            document.getElementById("prev-heygen").src = sd.url;
            document.getElementById("prev-heygen-wrap").style.display = "block";
            showDraftSection(script);
          }}
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
            hint = " → Check your GOOGLE_API_KEY in Setup.";
          }} else if (type === "remotion") {{
            hint = " → Check server logs for render error details.";
          }}
          status.innerHTML = '<span style="color:#e74c3c">✗ Error: ' + errMsg + '</span><br><span style="color:#e67e22;font-size:12px">' + hint + '</span>';
          _endJob();
        }} else {{
          const dots = ".".repeat((pollCount % 3) + 1);
          if (sd.message) {{
            status.textContent = "⏳ " + sd.message;
          }} else if (type === "veo3") {{
            status.textContent = "⏳ VEO 3 generating" + dots;
          }} else if (type === "remotion") {{
            status.textContent = "⏳ Rendering " + (composition || "PostCard") + dots;
          }} else {{
            status.textContent = "⏳ HeyGen generating avatar" + dots;
          }}
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

# ---------------------------------------------------------------------------
# Auth / Session management
# ---------------------------------------------------------------------------
import time as _time
import hmac as _hmac
import hashlib as _hashlib

_sessions: dict = {}       # session_token -> {expiry, username}
_reset_tokens: dict = {}   # reset_token -> {username, expiry}
_SESSION_TTL = 86400       # 24 hours
_RESET_TTL   = 3600        # 1 hour


def _session_create(username: str = "") -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = {"expiry": _time.time() + _SESSION_TTL, "username": username}
    return token


def _session_get_username(token: str | None) -> str:
    """Return the username associated with a valid session, or ''."""
    if not token:
        return ""
    entry = _sessions.get(token)
    if not entry or _time.time() > entry.get("expiry", 0):
        return ""
    return entry.get("username", "")


def _session_valid(token: str | None) -> bool:
    if not token:
        return False
    entry = _sessions.get(token)
    if not entry:
        return False
    exp = entry.get("expiry", 0) if isinstance(entry, dict) else entry
    if _time.time() > exp:
        _sessions.pop(token, None)
        return False
    return True


def _session_delete(token: str):
    _sessions.pop(token, None)


def _get_session_cookie(handler) -> str | None:
    raw = handler.headers.get("Cookie", "")
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k.strip() == "session":
            return v.strip()
    return None


def _password_valid(password: str) -> bool:
    """Legacy check against APP_PASSWORD env var (used by _save_account only)."""
    from config import config as _cfg
    stored = _cfg.app_password
    if not stored:
        return False
    return _hmac.compare_digest(
        _hashlib.sha256(password.encode()).hexdigest(),
        _hashlib.sha256(stored.encode()).hexdigest(),
    )


def _reset_token_create(username: str) -> str:
    token = secrets.token_urlsafe(32)
    _reset_tokens[token] = {"username": username, "expiry": _time.time() + _RESET_TTL}
    return token


def _reset_token_consume(token: str) -> str | None:
    """Return username if token is valid, then delete it."""
    entry = _reset_tokens.get(token)
    if not entry:
        return None
    if _time.time() > entry["expiry"]:
        _reset_tokens.pop(token, None)
        return None
    _reset_tokens.pop(token, None)
    return entry["username"]


def _send_reset_email(email: str, username: str, reset_url: str):
    """Send password reset email via SMTP. Silently skips if SMTP not configured."""
    from config import config as _cfg
    if not _cfg.smtp_enabled:
        return
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(
        f"Hi {username},\n\nClick the link below to reset your MakOne BI password:\n\n"
        f"{reset_url}\n\nThis link expires in 1 hour.\n\nIf you didn't request this, ignore this email.",
        "plain",
    )
    msg["Subject"] = "MakOne BI — Password Reset"
    msg["From"]    = _cfg.smtp_user
    msg["To"]      = email
    try:
        with smtplib.SMTP(_cfg.smtp_host, _cfg.smtp_port) as s:
            s.starttls()
            s.login(_cfg.smtp_user, _cfg.smtp_password)
            s.send_message(msg)
        logger.info(f"Password reset email sent to {email}")
    except Exception as e:
        logger.error(f"Failed to send reset email: {e}")


def _page_login(error: str = "", tab: str = "signin", success: str = "") -> str:
    err_html = f'<div style="background:rgba(220,38,38,0.12);color:#fca5a5;border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:14px;border:1px solid rgba(220,38,38,0.3)">{_esc(error)}</div>' if error else ""
    ok_html  = f'<div style="background:rgba(46,204,113,0.12);color:#4ade80;border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:14px;border:1px solid rgba(46,204,113,0.3)">{_esc(success)}</div>' if success else ""
    from config import config as _cfg
    smtp_note = "" if _cfg.smtp_enabled else '<p style="font-size:11px;color:#475569;margin-top:8px">⚠ No email configured — your admin will share the reset link with you.</p>'
    si = "active" if tab == "signin" else ""
    su = "active" if tab == "signup" else ""
    fo = "active" if tab == "forgot" else ""
    _login_css = """*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Arial,sans-serif;background:#07071a;color:#fff;min-height:100vh;overflow-x:hidden}
.glow{position:absolute;border-radius:50%;pointer-events:none;filter:blur(80px)}
.hero{min-height:100vh;display:flex;flex-direction:row;align-items:stretch}
.left{flex:1;display:flex;flex-direction:column;justify-content:center;padding:80px 60px;position:relative;overflow:hidden}
.right{width:460px;flex-shrink:0;display:flex;align-items:center;justify-content:center;padding:40px;background:rgba(255,255,255,0.03);border-left:1px solid rgba(255,255,255,0.06)}
.badge{display:inline-flex;align-items:center;gap:8px;background:rgba(79,142,247,0.12);border:1px solid rgba(79,142,247,0.3);border-radius:99px;padding:6px 16px;font-size:13px;color:#93c5fd;font-weight:600;margin-bottom:32px}
.badge-dot{width:8px;height:8px;border-radius:50%;background:#4f8ef7;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
h1{font-size:56px;font-weight:900;line-height:1.1;margin-bottom:24px;letter-spacing:-1px}
.grad{background:linear-gradient(90deg,#4f8ef7,#a855f7,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{font-size:18px;color:#94a3b8;line-height:1.7;margin-bottom:40px;max-width:520px}
.features{display:flex;flex-direction:column;gap:18px;margin-bottom:40px}
.feature{display:flex;align-items:flex-start;gap:16px}
.feature-icon{width:42px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:19px;flex-shrink:0}
.feature-text h3{font-size:14px;font-weight:700;color:#f1f5f9;margin-bottom:2px}
.feature-text p{font-size:13px;color:#64748b;line-height:1.5}
.stats{display:flex;gap:36px}
.stat-val{font-size:30px;font-weight:900;background:linear-gradient(90deg,#4f8ef7,#a855f7);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stat-label{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:2px}
.auth-card{width:100%;max-width:380px}
.tab-bar{display:flex;gap:4px;background:rgba(255,255,255,0.05);border-radius:10px;padding:4px;margin-bottom:24px}
.tab-btn{flex:1;padding:8px 4px;border:none;background:transparent;color:#64748b;font-size:13px;font-weight:600;cursor:pointer;border-radius:7px;transition:all .2s}
.tab-btn.active{background:rgba(79,142,247,0.2);color:#93c5fd}
.tab-pane{display:none}.tab-pane.active{display:block}
.auth-title{font-size:20px;font-weight:800;color:#f1f5f9;margin-bottom:4px}
.auth-sub{font-size:13px;color:#64748b;margin-bottom:20px}
.field-label{display:block;font-size:11px;font-weight:700;color:#94a3b8;letter-spacing:.5px;text-transform:uppercase;margin-bottom:7px}
.login-input{width:100%;padding:11px 14px;background:rgba(255,255,255,0.05);border:1.5px solid rgba(255,255,255,0.1);border-radius:9px;font-size:14px;color:#fff;outline:none;transition:border-color .2s;margin-bottom:14px}
.login-input:focus{border-color:#4f8ef7;background:rgba(79,142,247,0.08)}
.login-input::placeholder{color:#475569}
.login-btn{width:100%;padding:13px;background:linear-gradient(135deg,#4f8ef7,#a855f7);color:#fff;border:none;border-radius:9px;font-size:15px;font-weight:700;cursor:pointer;margin-top:4px;transition:opacity .2s}
.login-btn:hover{opacity:.9}
.divider{height:1px;background:rgba(255,255,255,0.06);margin:22px 0}
.footer-note{font-size:11px;color:#334155;text-align:center}
@media(max-width:960px){
  .hero{flex-direction:column}
  .left{padding:56px 28px 36px}
  h1{font-size:36px}
  .right{width:100%;border-left:none;border-top:1px solid rgba(255,255,255,0.06);padding:36px 28px}
  .stats{gap:20px}
}"""
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MakOne BI — AI Content Marketing</title>
<style>{_login_css}</style>
</head><body>
<div class="hero">

  <!-- LEFT — Marketing -->
  <div class="left">
    <div class="glow" style="width:500px;height:500px;top:-100px;left:-100px;background:rgba(79,142,247,0.12)"></div>
    <div class="glow" style="width:400px;height:400px;bottom:0;right:0;background:rgba(168,85,247,0.1)"></div>

    <div class="badge"><span class="badge-dot"></span>AI-Powered Platform</div>
    <h1>Content that<br>works while<br>you <span class="grad">sleep.</span></h1>
    <p class="subtitle">MakOne BI writes, schedules, and publishes your social media content automatically — with AI videos, smart approval flows, and multi-platform posting.</p>

    <div class="features">
      <div class="feature">
        <div class="feature-icon" style="background:rgba(79,142,247,0.15)">✍️</div>
        <div class="feature-text"><h3>AI Content Creation</h3><p>GPT-4 writes LinkedIn, Facebook & Instagram posts tailored to your brand voice.</p></div>
      </div>
      <div class="feature">
        <div class="feature-icon" style="background:rgba(168,85,247,0.15)">🎬</div>
        <div class="feature-text"><h3>Automated Video Generation</h3><p>HeyGen AI avatars, VEO 3 cinematic clips & Remotion branded videos — no editing needed.</p></div>
      </div>
      <div class="feature">
        <div class="feature-icon" style="background:rgba(6,182,212,0.15)">📅</div>
        <div class="feature-text"><h3>Smart Scheduling & Approval</h3><p>Review drafts, approve, then publish automatically across all your platforms.</p></div>
      </div>
    </div>

    <div class="stats">
      <div><div class="stat-val">5+</div><div class="stat-label">Platforms</div></div>
      <div><div class="stat-val">24/7</div><div class="stat-label">Automated</div></div>
      <div><div class="stat-val">AI</div><div class="stat-label">Powered</div></div>
    </div>
  </div>

  <!-- RIGHT — Auth tabs -->
  <div class="right">
    <div class="auth-card">
      <div style="font-size:30px;margin-bottom:14px">🤖</div>

      <div class="tab-bar">
        <button class="tab-btn {si}" onclick="showTab('signin')">Sign In</button>
        <button class="tab-btn {su}" onclick="showTab('signup')">Sign Up</button>
        <button class="tab-btn {fo}" onclick="showTab('forgot')">Reset Password</button>
      </div>

      {err_html}{ok_html}

      <!-- SIGN IN -->
      <div id="tab-signin" class="tab-pane {si}">
        <div class="auth-title">Welcome back</div>
        <div class="auth-sub">Sign in to your MakOne BI dashboard</div>
        <form method="POST" action="/login">
          <label class="field-label">Username</label>
          <input class="login-input" name="username" type="text" autocomplete="username" placeholder="Enter username" required>
          <label class="field-label">Password</label>
          <input class="login-input" name="password" type="password" autocomplete="current-password" placeholder="Enter password" required>
          <button class="login-btn" type="submit">Sign In →</button>
        </form>
      </div>

      <!-- SIGN UP -->
      <div id="tab-signup" class="tab-pane {su}">
        <div class="auth-title">Create an account</div>
        <div class="auth-sub">Request access to MakOne BI</div>
        <form method="POST" action="/signup">
          <label class="field-label">Username</label>
          <input class="login-input" name="username" type="text" autocomplete="username" placeholder="Choose a username" required>
          <label class="field-label">Email</label>
          <input class="login-input" name="email" type="email" autocomplete="email" placeholder="your@email.com" required>
          <label class="field-label">Password</label>
          <input class="login-input" name="password" type="password" autocomplete="new-password" placeholder="Create a password" required>
          <label class="field-label">Confirm Password</label>
          <input class="login-input" name="confirm" type="password" autocomplete="new-password" placeholder="Repeat password" required>
          <button class="login-btn" type="submit">Create Account →</button>
        </form>
      </div>

      <!-- FORGOT PASSWORD -->
      <div id="tab-forgot" class="tab-pane {fo}">
        <div class="auth-title">Reset your password</div>
        <div class="auth-sub">Enter your email to receive a reset link</div>
        <form method="POST" action="/forgot-password">
          <label class="field-label">Email address</label>
          <input class="login-input" name="email" type="email" autocomplete="email" placeholder="your@email.com" required>
          <button class="login-btn" type="submit">Send Reset Link →</button>
        </form>
        {smtp_note}
      </div>

      <div class="divider"></div>
      <div class="footer-note">app.makone-bi.com &nbsp;·&nbsp; MakOne BI © 2026</div>
    </div>
  </div>

</div>
<script>
function showTab(t) {{
  ['signin','signup','forgot'].forEach(function(id) {{
    document.getElementById('tab-'+id).classList.toggle('active', id===t);
  }});
  document.querySelectorAll('.tab-btn').forEach(function(b,i) {{
    b.classList.toggle('active', ['signin','signup','forgot'][i]===t);
  }});
}}
</script>
</body></html>"""


def _page_reset_password(token: str, error: str = "") -> str:
    err_html = f'<div style="background:rgba(220,38,38,0.12);color:#fca5a5;border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:14px">{_esc(error)}</div>' if error else ""
    return """<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reset Password — MakOne BI</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Arial,sans-serif;background:#07071a;color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:40px;width:100%;max-width:400px}
.field-label{display:block;font-size:11px;font-weight:700;color:#94a3b8;letter-spacing:.5px;text-transform:uppercase;margin-bottom:7px}
input{width:100%;padding:11px 14px;background:rgba(255,255,255,0.05);border:1.5px solid rgba(255,255,255,0.1);border-radius:9px;font-size:14px;color:#fff;outline:none;margin-bottom:14px}
input:focus{border-color:#4f8ef7}
input::placeholder{color:#475569}
button{width:100%;padding:13px;background:linear-gradient(135deg,#4f8ef7,#a855f7);color:#fff;border:none;border-radius:9px;font-size:15px;font-weight:700;cursor:pointer}
</style></head><body>
<div class="card">
  <div style="font-size:28px;margin-bottom:16px">🔑</div>
  <div style="font-size:20px;font-weight:800;margin-bottom:4px">Set new password</div>
  <div style="font-size:13px;color:#64748b;margin-bottom:20px">Choose a strong password for your account.</div>
""" + err_html + f"""
  <form method="POST" action="/reset-password">
    <input type="hidden" name="token" value="{_esc(token)}">
    <label class="field-label">New Password</label>
    <input type="password" name="password" placeholder="New password" required>
    <label class="field-label">Confirm Password</label>
    <input type="password" name="confirm" placeholder="Repeat password" required>
    <button type="submit">Set Password →</button>
  </form>
</div>
</body></html>"""


def _start_video_job(job_id: str, video_type: str, text: str, composition: str = "PostCard", screenshot_url: str = ""):
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
                from src.content_generator import post_to_veo3_prompt, post_to_spoken_script
                from config import config as _cfg
                fname = f"veo3_{ts}.mp4"
                veo3_prompt = post_to_veo3_prompt(text)
                veo3_caption = post_to_spoken_script(text)
                logger.info(f"VEO3 prompt: {veo3_prompt}")
                veo3_client.make_video(veo3_prompt, fname, caption_text=veo3_caption)
                url = _cfg.get_public_url(f"/media/{fname}")
            elif video_type == "remotion":
                from src import remotion_client, heygen_client
                from src.content_generator import post_to_spoken_script
                from config import config as _cfg
                comp = composition or "PostCard"
                fname = f"remotion_{comp}_{ts}.mp4"
                logger.info(f"Remotion render: composition={comp}, text preview={text[:80]}")

                from src.content_generator import extract_remotion_props

                if comp == "AvatarShowcase":
                    # Step 1 — Generate HeyGen avatar video with the chat script
                    _video_jobs[job_id]["message"] = "Step 1/3: Generating HeyGen avatar video (5–20 min)..."
                    heygen_client.config.heygen_api_key = _os.getenv("HEYGEN_API_KEY", "")
                    heygen_client.config.heygen_avatar_id = _os.getenv("HEYGEN_AVATAR_ID", "")
                    heygen_client.config.heygen_voice_id = _os.getenv("HEYGEN_VOICE_ID", "")
                    spoken_script = post_to_spoken_script(text)
                    logger.info(f"AvatarShowcase HeyGen script ({len(spoken_script)} chars): {spoken_script[:120]}...")
                    heygen_url = heygen_client.wait_for_video(heygen_client.create_video(spoken_script))

                    # Step 2 — Download avatar video + capture fresh screenshots
                    _video_jobs[job_id]["message"] = "Step 2/3: Downloading avatar video & capturing screenshots..."
                    remotion_client.download_heygen_to_public(heygen_url)
                    snap_url = screenshot_url or _cfg.get_public_url() or "http://localhost:8080"
                    logger.info(f"AvatarShowcase: capturing screenshots from {snap_url}")
                    remotion_client.capture_screenshots(snap_url)

                    # Step 3 — Get video duration, then render AvatarShowcase
                    _video_jobs[job_id]["message"] = "Step 3/3: Rendering AvatarShowcase with Remotion (1–2 min)..."
                    import os as _ospath
                    heygen_pub = _ospath.path.join(
                        _ospath.path.dirname(__file__), '..', 'remotion', 'public', 'heygen_latest.mp4'
                    )
                    vid_secs = remotion_client.get_video_duration(_ospath.path.abspath(heygen_pub))
                    remotion_client.render_composition(comp, fname, props={"videoDurationSecs": vid_secs})

                elif comp == "PostCard":
                    _video_jobs[job_id]["message"] = "Extracting post content for Post Card..."
                    props = extract_remotion_props(text, "PostCard")
                    props.setdefault("businessName", _cfg.business_name)
                    props.setdefault("website", _cfg.business_website)
                    props.setdefault("text", text[:200])
                    _video_jobs[job_id]["message"] = "Rendering Post Card..."
                    remotion_client.render_composition(comp, fname, props=props)

                elif comp == "Intro":
                    _video_jobs[job_id]["message"] = "Extracting tagline for Intro..."
                    props = extract_remotion_props(text, "Intro")
                    props.setdefault("businessName", _cfg.business_name)
                    props.setdefault("tagline", "AI Automation Experts")
                    _video_jobs[job_id]["message"] = "Rendering YouTube Intro..."
                    remotion_client.render_composition(comp, fname, props=props)

                elif comp == "Outro":
                    _video_jobs[job_id]["message"] = "Extracting CTA for Outro..."
                    props = extract_remotion_props(text, "Outro")
                    props.setdefault("businessName", _cfg.business_name)
                    props.setdefault("website", _cfg.business_website)
                    props.setdefault("ctaText", "Book a free discovery call")
                    _video_jobs[job_id]["message"] = "Rendering YouTube Outro..."
                    remotion_client.render_composition(comp, fname, props=props)

                elif comp == "ProductLaunch":
                    _video_jobs[job_id]["message"] = "AI is crafting your product launch script..."
                    props = extract_remotion_props(text, "ProductLaunch")
                    _video_jobs[job_id]["message"] = "Rendering Product Launch video (25s)..."
                    remotion_client.render_composition(comp, fname, props=props, timeout=900)

                else:
                    remotion_client.render_composition(comp, fname, props={})
                url = _cfg.get_public_url(f"/media/{fname}")
            else:  # heygen
                from src import heygen_client
                from src.content_generator import post_to_spoken_script
                # Use fresh values from env
                heygen_client.config.heygen_api_key = _os.getenv("HEYGEN_API_KEY", "")
                heygen_client.config.heygen_avatar_id = _os.getenv("HEYGEN_AVATAR_ID", "")
                heygen_client.config.heygen_voice_id = _os.getenv("HEYGEN_VOICE_ID", "")
                # Convert the post text to a natural spoken script (removes hashtags, bullets, URLs)
                spoken_script = post_to_spoken_script(text)
                logger.info(f"Spoken script for HeyGen ({len(spoken_script)} chars): {spoken_script[:120]}...")
                video_url = heygen_client.wait_for_video(heygen_client.create_video(spoken_script))
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
    "APP_PASSWORD",
}

_SETUP_KEYS = {
    "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_TEMPERATURE",
    "HEYGEN_API_KEY", "HEYGEN_AVATAR_ID", "HEYGEN_VOICE_ID",
    "GOOGLE_API_KEY", "GOOGLE_PROJECT_ID",
    "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN", "LINKEDIN_ORG_URN",
    "FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET", "FACEBOOK_ACCESS_TOKEN", "FACEBOOK_PAGE_ID",
    "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_ACCOUNT_ID",
    "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN", "YOUTUBE_PRIVACY",
    "BUSINESS_NAME", "BUSINESS_WEBSITE", "CONTACT_EMAIL",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
    "POST_DAYS", "POST_HOUR", "POST_MINUTE", "TIMEZONE",
    "APPROVAL_REQUIRED", "VPS_HOST", "APPROVAL_PORT",
}


class _Handler(BaseHTTPRequestHandler):

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _is_authenticated(self) -> bool:
        return _session_valid(_get_session_cookie(self))

    def _require_auth(self) -> bool:
        """Return True if authenticated. Otherwise redirect to /login and return False."""
        if self._is_authenticated():
            return True
        self.send_response(302)
        self.send_header("Location", "/login")
        self.end_headers()
        return False

    def _set_session_cookie(self, token: str):
        self.send_header("Set-Cookie", f"session={token}; HttpOnly; SameSite=Lax; Max-Age={_SESSION_TTL}; Path=/")

    def _clear_session_cookie(self):
        self.send_header("Set-Cookie", "session=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/")

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def do_GET(self):
        try:
            p = urlparse(self.path)
            qs = parse_qs(p.query)
            token = qs.get("token", [None])[0]

            # Public routes — no auth required
            if p.path == "/login":
                self._send(200, _page_login())
                return
            if p.path == "/reset-password":
                token = qs.get("token", [""])[0]
                if not token or token not in _reset_tokens:
                    self._send(200, _page_login(error="Reset link is invalid or has expired.", tab="forgot"))
                else:
                    self._send(200, _page_reset_password(token))
                return
            if p.path == "/logout":
                _session_delete(_get_session_cookie(self))
                self.send_response(302)
                self._clear_session_cookie()
                self.send_header("Location", "/login")
                self.end_headers()
                return
            # /review, /reject, /media/ stay public (used in emails)
            if p.path in ("/review", "/reject") or p.path.startswith("/media/"):
                pass  # fall through to route handling below
            elif not self._require_auth():
                return

            if p.path in ("/", ""):
                self._send(200, _page_dashboard())
            elif p.path == "/setup":
                _cu = _session_get_username(_get_session_cookie(self))
                self._send(200, _page_setup(current_username=_cu))
            elif p.path == "/influence":
                self._send(200, _page_influence())
            elif p.path == "/calendar":
                self._send(200, _page_calendar())
            elif p.path == "/render":
                self._send(200, _page_render())
            elif p.path == "/render/status":
                job_id = qs.get("job_id", [None])[0]
                self._send_json(_render_jobs.get(job_id, {"status": "error", "error": "Unknown job"}))
            elif p.path == "/create":
                self._send(200, _page_create())
            elif p.path == "/create/video/status":
                job_id = qs.get("job_id", [None])[0]
                job = _video_jobs.get(job_id, {"status": "error", "error": "Unknown job"})
                self._send_json(job)
            elif p.path == "/setup/heygen/avatars":
                self._list_heygen_avatars()
            elif p.path == "/setup/heygen/debug":
                self._heygen_raw_debug()
            elif p.path == "/setup/youtube/connect":
                self._youtube_connect()
            elif p.path == "/setup/youtube/callback":
                self._youtube_callback(qs)
            elif p.path == "/setup/facebook/connect":
                self._facebook_connect()
            elif p.path == "/setup/facebook/callback":
                self._facebook_callback(qs)
            elif p.path == "/setup/linkedin/connect":
                self._linkedin_connect()
            elif p.path == "/setup/linkedin/callback":
                self._linkedin_callback(qs)
            elif p.path == "/setup/heygen/test":
                self._heygen_test()
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

            # Public POST routes — no auth required
            if p.path == "/login":
                from src import user_store as _us
                username = body.get("username", [""])[0].strip()
                password = body.get("password", [""])[0]
                user = _us.authenticate(username, password)
                if user:
                    session_token = _session_create(username=username)
                    self.send_response(302)
                    self._set_session_cookie(session_token)
                    self.send_header("Location", "/")
                    self.end_headers()
                else:
                    # Check if user exists but is pending
                    u = _us.get_by_username(username)
                    if u and u.get("status") == "pending":
                        self._send(200, _page_login("Your account is pending approval by an admin."))
                    else:
                        self._send(200, _page_login("Invalid username or password."))
                return

            if p.path == "/signup":
                from src import user_store as _us
                username = body.get("username", [""])[0].strip()
                email    = body.get("email",    [""])[0].strip()
                password = body.get("password", [""])[0]
                confirm  = body.get("confirm",  [""])[0]
                if not username or not email or not password:
                    self._send(200, _page_login("All fields are required.", tab="signup"))
                    return
                if password != confirm:
                    self._send(200, _page_login("Passwords do not match.", tab="signup"))
                    return
                if len(password) < 6:
                    self._send(200, _page_login("Password must be at least 6 characters.", tab="signup"))
                    return
                try:
                    # First user becomes admin and is auto-approved
                    is_first = _us.is_first_user()
                    role   = "admin"  if is_first else "user"
                    status = "active" if is_first else "pending"
                    _us.create_user(username, email, password, role=role, status=status)
                    if is_first:
                        session_token = _session_create(username=username)
                        self.send_response(302)
                        self._set_session_cookie(session_token)
                        self.send_header("Location", "/")
                        self.end_headers()
                    else:
                        self._send(200, _page_login(
                            success="Account created! An admin will review and approve your access.",
                            tab="signin",
                        ))
                except ValueError as e:
                    self._send(200, _page_login(str(e), tab="signup"))
                return

            if p.path == "/forgot-password":
                from src import user_store as _us
                from config import config as _cfg
                email = body.get("email", [""])[0].strip()
                user  = _us.get_by_email(email)
                if user:
                    token = _reset_token_create(user["username"])
                    reset_url = _cfg.get_public_url(f"/reset-password?token={token}")
                    _send_reset_email(email, user["username"], reset_url)
                    if not _cfg.smtp_enabled:
                        # No email — show link directly (admin use)
                        self._send(200, _page_login(
                            success=f"Reset link (no email configured — share manually): {reset_url}",
                            tab="forgot",
                        ))
                        return
                # Always show success to avoid email enumeration
                self._send(200, _page_login(
                    success="If that email is registered, a reset link has been sent.",
                    tab="forgot",
                ))
                return

            if p.path == "/reset-password":
                from src import user_store as _us
                token    = body.get("token",    [""])[0]
                password = body.get("password", [""])[0]
                confirm  = body.get("confirm",  [""])[0]
                if password != confirm:
                    self._send(200, _page_reset_password(token, "Passwords do not match."))
                    return
                if len(password) < 6:
                    self._send(200, _page_reset_password(token, "Password must be at least 6 characters."))
                    return
                username = _reset_token_consume(token)
                if not username:
                    self._send(200, _page_login("Reset link is invalid or has expired.", tab="forgot"))
                    return
                _us.update_password(username, password)
                self._send(200, _page_login(success="Password updated successfully. Please sign in.", tab="signin"))
                return

            # All other POST routes require auth
            if not self._require_auth():
                return

            if p.path == "/setup":
                _cu = _session_get_username(_get_session_cookie(self))
                self._save_setup(body, current_username=_cu)
            elif p.path == "/setup/users/approve":
                self._admin_approve_user(body)
            elif p.path == "/setup/users/delete":
                self._admin_delete_user(body)
            elif p.path == "/account":
                self._save_account(body)
            elif p.path == "/influence":
                self._save_influence(body)
            elif p.path == "/create/chat":
                self._chat_create(body)
            elif p.path == "/create/save":
                self._save_content_draft(body)
            elif p.path == "/create/image":
                self._generate_ai_image(body)
            elif p.path in ("/create/video/veo3", "/create/video/heygen", "/create/video/remotion"):
                self._start_video_generation(body, p.path)
            elif p.path == "/render/start":
                import secrets as _sec
                composition = body.get("composition", [""])[0].strip()
                props = body.get("props", ["{}"])[0].strip()
                if not composition:
                    self._send_json({"error": "No composition specified"})
                else:
                    job_id = _sec.token_urlsafe(12)
                    _start_render_job(job_id, composition, props)
                    self._send_json({"job_id": job_id})
            elif p.path == "/publish":
                li = body.get("linkedin_text", [""])[0]
                fb = body.get("facebook_text", [""])[0]
                sched_type = body.get("sched_type", ["now"])[0]
                scheduled_at = body.get("scheduled_at", [""])[0].strip() if sched_type == "later" else ""
                self._publish(token, li, fb, scheduled_at)
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

    def _save_setup(self, body: dict, current_username: str = ""):
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

        self._send(200, _page_setup(alert=alert_msg, alert_type="success", current_username=current_username))

    def _admin_approve_user(self, body: dict):
        from src import user_store as _us
        cu = _session_get_username(_get_session_cookie(self))
        current_user = _us.get_by_username(cu)
        if not current_user or current_user.get("role") != "admin":
            self._send(403, self._simple_page("Forbidden", "Admin only.", "#e74c3c"))
            return
        username = body.get("username", [""])[0].strip()
        if username:
            _us.update_status(username, "active")
            logger.info(f"Admin '{cu}' approved user '{username}'")
        self._send(200, _page_setup(alert=f"User '{_esc(username)}' approved.", alert_type="success", current_username=cu))

    def _admin_delete_user(self, body: dict):
        from src import user_store as _us
        cu = _session_get_username(_get_session_cookie(self))
        current_user = _us.get_by_username(cu)
        if not current_user or current_user.get("role") != "admin":
            self._send(403, self._simple_page("Forbidden", "Admin only.", "#e74c3c"))
            return
        username = body.get("username", [""])[0].strip()
        if username == cu:
            self._send(200, _page_setup(alert="You cannot delete your own account.", alert_type="error", current_username=cu))
            return
        if username:
            _us.delete_user(username)
            logger.info(f"Admin '{cu}' deleted user '{username}'")
        self._send(200, _page_setup(alert=f"User '{_esc(username)}' deleted.", alert_type="success", current_username=cu))

    def _save_account(self, body: dict):
        current_pw   = body.get("current_password", [""])[0]
        new_username = body.get("username", [""])[0].strip()
        new_password = body.get("new_password", [""])[0]
        confirm_pw   = body.get("confirm_password", [""])[0]

        # Verify current password
        if not _password_valid(current_pw):
            self._send(200, _page_setup(
                alert="Incorrect current password — no changes saved.",
                alert_type="error",
            ))
            return

        # Passwords must match if a new one is provided
        if new_password and new_password != confirm_pw:
            self._send(200, _page_setup(
                alert="New passwords do not match — no changes saved.",
                alert_type="error",
            ))
            return

        updates = {}
        if new_username:
            updates["APP_USERNAME"] = new_username
        if new_password:
            updates["APP_PASSWORD"] = new_password

        if updates:
            _write_env(updates)
            # Reload config so new credentials take effect immediately
            from dotenv import load_dotenv as _ldenv
            _ldenv(override=True)
            from config import config as _cfg
            if "APP_USERNAME" in updates:
                _cfg.app_username = updates["APP_USERNAME"]
            if "APP_PASSWORD" in updates:
                _cfg.app_password = updates["APP_PASSWORD"]
            self._send(200, _page_setup(
                alert="Login credentials updated successfully.",
                alert_type="success",
            ))
        else:
            self._send(200, _page_setup(
                alert="No changes to save.",
                alert_type="success",
            ))

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

    def _youtube_connect(self):
        """Redirect user to Google OAuth for YouTube."""
        from config import config as _config
        from dotenv import load_dotenv as _ldenv
        _ldenv(override=True)
        import os as _os
        client_id = _os.getenv("YOUTUBE_CLIENT_ID", "") or _config.youtube_client_id
        if not client_id:
            self._send(400, self._simple_page("Missing Client ID", "Save your YouTube Client ID in Setup first.", "#e74c3c"))
            return
        redirect_uri = _config.get_public_url("/setup/youtube/callback")
        from src import youtube_client
        auth_url = youtube_client.get_auth_url(client_id, redirect_uri)
        self.send_response(302)
        self.send_header("Location", auth_url)
        self.end_headers()

    def _youtube_callback(self, qs):
        """Handle OAuth callback, exchange code for refresh token, save to .env."""
        try:
            from dotenv import load_dotenv as _ldenv
            _ldenv(override=True)
            import os as _os
            from config import config as _config
            code = (qs.get("code", [""])[0] or "").strip()
            if not code:
                error = qs.get("error", ["unknown"])[0]
                self._send(400, self._simple_page("OAuth Error", f"Google returned error: {error}", "#e74c3c"))
                return
            client_id = _os.getenv("YOUTUBE_CLIENT_ID", "")
            client_secret = _os.getenv("YOUTUBE_CLIENT_SECRET", "")
            redirect_uri = _config.get_public_url("/setup/youtube/callback")
            from src import youtube_client
            refresh_token = youtube_client.exchange_code(client_id, client_secret, code, redirect_uri)
            env = _read_env()
            env["YOUTUBE_REFRESH_TOKEN"] = refresh_token
            _write_env(env)
            self._send(200, self._simple_page("YouTube Connected", "YouTube channel connected successfully! You can now publish videos to YouTube.", "#2ecc71"))
        except Exception as e:
            self._send(500, self._simple_page("OAuth Failed", f"Error: {_esc(str(e))}", "#e74c3c"))

    def _facebook_connect(self):
        """Redirect to Facebook OAuth."""
        from config import config as _cfg
        from dotenv import load_dotenv as _ldenv
        import os as _os
        from urllib.parse import urlencode as _ue
        _ldenv(override=True)
        app_id = _os.getenv("FACEBOOK_APP_ID", "")
        if not app_id:
            self._send(400, self._simple_page("Missing App ID", "Save your Facebook App ID in Setup first.", "#e74c3c"))
            return
        redirect_uri = _cfg.get_public_url("/setup/facebook/callback")
        auth_url = "https://www.facebook.com/v18.0/dialog/oauth?" + _ue({
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "scope": "pages_manage_posts,pages_read_engagement,pages_show_list,instagram_basic,instagram_content_publish,business_management",
            "response_type": "code",
        })
        self.send_response(302)
        self.send_header("Location", auth_url)
        self.end_headers()

    def _facebook_callback(self, qs):
        """Exchange Facebook code for permanent page token + Instagram ID."""
        import requests as _req
        from dotenv import load_dotenv as _ldenv
        import os as _os
        from config import config as _cfg
        _ldenv(override=True)
        try:
            code = (qs.get("code", [""])[0] or "").strip()
            if not code:
                err = qs.get("error_description", qs.get("error", ["unknown"]))[0]
                self._send(400, self._simple_page("OAuth Error", f"Facebook error: {_esc(str(err))}", "#e74c3c"))
                return
            app_id = _os.getenv("FACEBOOK_APP_ID", "")
            app_secret = _os.getenv("FACEBOOK_APP_SECRET", "")
            redirect_uri = _cfg.get_public_url("/setup/facebook/callback")
            # Short-lived user token
            r1 = _req.get("https://graph.facebook.com/v18.0/oauth/access_token", params={
                "client_id": app_id, "client_secret": app_secret,
                "code": code, "redirect_uri": redirect_uri,
            }, timeout=15)
            r1.raise_for_status()
            short_token = r1.json()["access_token"]
            # Long-lived user token (60 days)
            r2 = _req.get("https://graph.facebook.com/v18.0/oauth/access_token", params={
                "grant_type": "fb_exchange_token", "client_id": app_id,
                "client_secret": app_secret, "fb_exchange_token": short_token,
            }, timeout=15)
            r2.raise_for_status()
            long_token = r2.json()["access_token"]
            # Get pages and their permanent tokens
            r3 = _req.get("https://graph.facebook.com/v18.0/me/accounts", params={
                "access_token": long_token, "fields": "id,name,access_token",
            }, timeout=15)
            r3.raise_for_status()
            pages = r3.json().get("data", [])
            env = _read_env()
            ig_id = ""
            pages_info = "none"
            if pages:
                page = pages[0]
                env["FACEBOOK_ACCESS_TOKEN"] = page["access_token"]
                env["FACEBOOK_PAGE_ID"] = page["id"]
                env["INSTAGRAM_ACCESS_TOKEN"] = page["access_token"]
                pages_info = f"{page['name']} ({page['id']})"
                r4 = _req.get(f"https://graph.facebook.com/v18.0/{page['id']}", params={
                    "fields": "instagram_business_account", "access_token": page["access_token"],
                }, timeout=15)
                if r4.ok:
                    ig_data = r4.json().get("instagram_business_account", {})
                    ig_id = ig_data.get("id", "")
                    if ig_id:
                        env["INSTAGRAM_ACCOUNT_ID"] = ig_id
            _write_env(env)
            self._send(200, self._simple_page("Facebook & Instagram Connected",
                f"Page: {pages_info} | Instagram ID: {ig_id or 'not linked'}. Permanent tokens saved!", "#2ecc71"))
        except Exception as e:
            self._send(500, self._simple_page("OAuth Failed", f"Error: {_esc(str(e))}", "#e74c3c"))

    def _linkedin_connect(self):
        """Redirect to LinkedIn OAuth."""
        from config import config as _cfg
        from dotenv import load_dotenv as _ldenv
        import os as _os
        import secrets as _sec
        from urllib.parse import urlencode as _ue
        _ldenv(override=True)
        client_id = _os.getenv("LINKEDIN_CLIENT_ID", "")
        if not client_id:
            self._send(400, self._simple_page("Missing Client ID", "Save your LinkedIn Client ID in Setup first.", "#e74c3c"))
            return
        redirect_uri = _cfg.get_public_url("/setup/linkedin/callback")
        auth_url = "https://www.linkedin.com/oauth/v2/authorization?" + _ue({
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": _sec.token_urlsafe(16),
            "scope": "w_member_social w_organization_social r_liteprofile",
        })
        self.send_response(302)
        self.send_header("Location", auth_url)
        self.end_headers()

    def _linkedin_callback(self, qs):
        """Exchange LinkedIn code for access token + person URN."""
        import requests as _req
        from dotenv import load_dotenv as _ldenv
        import os as _os
        from config import config as _cfg
        _ldenv(override=True)
        try:
            code = (qs.get("code", [""])[0] or "").strip()
            if not code:
                err = qs.get("error_description", qs.get("error", ["unknown"]))[0]
                self._send(400, self._simple_page("OAuth Error", f"LinkedIn error: {_esc(str(err))}", "#e74c3c"))
                return
            client_id = _os.getenv("LINKEDIN_CLIENT_ID", "")
            client_secret = _os.getenv("LINKEDIN_CLIENT_SECRET", "")
            redirect_uri = _cfg.get_public_url("/setup/linkedin/callback")
            r = _req.post("https://www.linkedin.com/oauth/v2/accessToken", data={
                "grant_type": "authorization_code", "code": code,
                "redirect_uri": redirect_uri, "client_id": client_id, "client_secret": client_secret,
            }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
            r.raise_for_status()
            access_token = r.json()["access_token"]
            me = _req.get("https://api.linkedin.com/v2/me",
                headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
            person_urn = ""
            if me.ok:
                person_urn = f"urn:li:person:{me.json().get('id', '')}"
            env = _read_env()
            env["LINKEDIN_ACCESS_TOKEN"] = access_token
            if person_urn:
                env["LINKEDIN_PERSON_URN"] = person_urn
            _write_env(env)
            self._send(200, self._simple_page("LinkedIn Connected",
                f"LinkedIn connected! URN: {person_urn}. Token saved.", "#2ecc71"))
        except Exception as e:
            self._send(500, self._simple_page("OAuth Failed", f"Error: {_esc(str(e))}", "#e74c3c"))

    def _heygen_test(self):
        """Test HeyGen API key and return account info."""
        from dotenv import load_dotenv as _ldenv
        import os as _os
        _ldenv(override=True)
        try:
            from src import heygen_client
            api_key = _os.getenv("HEYGEN_API_KEY", "")
            if not api_key:
                self._send_json({"error": "HEYGEN_API_KEY not set"})
                return
            groups = heygen_client.list_avatar_groups(api_key)
            avatars = heygen_client.list_avatars(api_key)
            self._send_json({"ok": True, "clone_groups": len(groups), "stock_avatars": len(avatars)})
        except Exception as e:
            self._send_json({"error": str(e)})

    def _heygen_raw_debug(self):
        """Return raw HeyGen API responses for debugging."""
        try:
            from dotenv import load_dotenv as _ldenv
            _ldenv(override=True)
            import os as _os
            api_key = _os.getenv("HEYGEN_API_KEY", "") or config.heygen_api_key
            from src import heygen_client
            groups_raw = heygen_client._heygen_get(api_key, "/v2/avatar_group.list", {"include_public": "false"})
            result = {"groups_response": groups_raw}
            groups = groups_raw.get("data", {}).get("avatar_group_list", []) or []
            result["looks_responses"] = {}
            for g in groups:
                gid = g.get("id", "") or g.get("group_id", "")
                looks_raw = heygen_client._heygen_get(api_key, f"/v2/avatar_group/{gid}/avatars")
                result["looks_responses"][gid] = looks_raw
            # Also check list_avatars for Len Onekeo entries
            avatars_raw = heygen_client._heygen_get(api_key, "/v2/avatars")
            all_av = avatars_raw.get("data", {}).get("avatars", []) or []
            result["my_avatars_in_list"] = [a for a in all_av if "Len Onekeo" in (a.get("avatar_name") or "")]
            result["total_avatars_count"] = len(all_av)
            self._send_json(result)
        except Exception as e:
            self._send_json({"error": str(e)})

    def _list_heygen_avatars(self):
        """Fetch avatar groups (AI clones) + stock avatars from HeyGen."""
        try:
            from dotenv import load_dotenv as _ldenv
            _ldenv(override=True)
            import os as _os
            api_key = _os.getenv("HEYGEN_API_KEY", "") or config.heygen_api_key
            if not api_key:
                self._send_json({"error": "HEYGEN_API_KEY is not set in Setup."})
                return
            from src import heygen_client

            def _norm_look(lk):
                return {
                    "id": lk.get("avatar_id") or lk.get("id") or "",
                    "name": lk.get("avatar_name") or lk.get("name") or "",
                    "image_url": (
                        lk.get("preview_image_url")
                        or lk.get("preview_image")
                        or lk.get("image_url")
                        or lk.get("thumbnail_url")
                        or ""
                    ),
                }

            result = []
            clone_ids = set()

            # 1. Fetch user AI clone groups and their looks (paginated)
            try:
                groups = heygen_client.list_avatar_groups(api_key)
                for g in groups:
                    group_id = g.get("id", "") or g.get("group_id", "")
                    group_name = g.get("group_name") or g.get("name") or "(unnamed)"
                    raw_looks = []
                    try:
                        raw_looks = heygen_client.list_group_looks(api_key, group_id)
                    except Exception:
                        pass
                    # Deduplicate looks by id
                    seen = set()
                    looks = []
                    for lk in raw_looks:
                        nl = _norm_look(lk)
                        if nl["id"] and nl["id"] not in seen:
                            seen.add(nl["id"])
                            clone_ids.add(nl["id"])
                            looks.append(nl)
                    result.append({
                        "group_id": group_id,
                        "group_name": group_name,
                        "section": "My AI Clones",
                        "looks": looks,
                    })
            except Exception:
                pass

            # 2. Stock avatars - exclude any avatar_id already shown as a clone look
            try:
                stock = heygen_client.list_avatars(api_key)
                seen_stock = set()
                stock_looks = []
                for a in stock:
                    nl = _norm_look(a)
                    if nl["id"] and nl["id"] not in clone_ids and nl["id"] not in seen_stock:
                        seen_stock.add(nl["id"])
                        stock_looks.append(nl)
                if stock_looks:
                    result.append({
                        "group_id": "",
                        "group_name": "Stock Avatars",
                        "section": "Stock Avatars",
                        "looks": stock_looks,
                    })
            except Exception:
                pass

            self._send_json({"groups": result})
        except Exception as e:
            self._send_json({"error": str(e)})

    def _start_video_generation(self, body: dict, path: str):
        """Start a background video generation job and return a job_id for polling."""
        import secrets as _sec
        video_type = "veo3" if path.endswith("veo3") else "remotion" if path.endswith("remotion") else "heygen"
        text = body.get("prompt" if video_type == "veo3" else "script", [""])[0].strip()
        if not text:
            text = "AI automation and business intelligence services"
        composition = body.get("composition", ["PostCard"])[0].strip() if video_type == "remotion" else "PostCard"
        screenshot_url = body.get("screenshot_url", [""])[0].strip()
        job_id = _sec.token_urlsafe(12)
        _start_video_job(job_id, video_type, text, composition, screenshot_url=screenshot_url)
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
        image_url = d.get("image_url", "")
        video_url = d.get("video_url", "")
        from config import config as _rcfg
        tz_label = _rcfg.timezone or "UTC"

        media_html = ""
        if image_url or video_url:
            media_html = '<div class="card" style="margin-bottom:0"><div class="card-title">Generated Media</div><div style="display:flex;gap:16px;flex-wrap:wrap">'
            if image_url:
                media_html += f'<div style="flex:1;min-width:200px"><div style="font-size:12px;font-weight:600;color:#888;margin-bottom:6px">AI IMAGE</div><img src="{_esc(image_url)}" style="max-width:100%;border-radius:8px;border:1px solid #e0e0e0"></div>'
            if video_url:
                media_html += f'<div style="flex:1;min-width:200px"><div style="font-size:12px;font-weight:600;color:#888;margin-bottom:6px">VIDEO</div><video src="{_esc(video_url)}" controls style="max-width:100%;border-radius:8px;max-height:260px"></video></div>'
            media_html += '</div></div>'

        html = _head(f"Review — {d.get('theme','').replace('_',' ').title()}") + _nav() + f"""
<div class="container" style="max-width:760px">
  <h1>Review Draft Post</h1>
  <p class="subtitle">
    <span class="badge badge-none">{d.get("theme","?").replace("_"," ").title()}</span>
    &nbsp;{d.get("industry","?")} &nbsp;·&nbsp; {ts}
  </p>

  {media_html}

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
      <div class="field" style="margin-top:20px;padding-top:16px;border-top:1px solid #eee">
        <div style="font-weight:600;font-size:14px;margin-bottom:10px">Publishing</div>
        <div style="display:flex;gap:20px;margin-bottom:12px;flex-wrap:wrap">
          <label style="display:inline-flex;align-items:center;gap:8px;font-weight:normal;cursor:pointer">
            <input type="radio" name="sched_type" value="now" checked onchange="toggleReviewSched()">
            Publish Now
          </label>
          <label style="display:inline-flex;align-items:center;gap:8px;font-weight:normal;cursor:pointer">
            <input type="radio" name="sched_type" value="later" onchange="toggleReviewSched()">
            Schedule for a specific date &amp; time
          </label>
        </div>
        <div id="review-sched-picker" style="display:none">
          <input type="datetime-local" name="scheduled_at" id="review-scheduled-at" style="max-width:280px">
          <div style="font-size:12px;color:#888;margin-top:4px">{tz_label} — post will publish automatically at this time</div>
        </div>
      </div>
      <div class="section-actions">
        <button type="submit" class="btn btn-primary" id="review-submit-btn">Publish Now</button>
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
</div>
<script>
function toggleReviewSched() {{
  const later = document.querySelector('input[name="sched_type"][value="later"]').checked;
  document.getElementById("review-sched-picker").style.display = later ? "block" : "none";
  document.getElementById("review-submit-btn").textContent = later ? "Schedule" : "Publish Now";
}}
</script>
</body></html>"""
        self._send(200, html)

    def _publish(self, token, li_text, fb_text, scheduled_at: str = ""):
        d = _find_by_token(token)
        if not d:
            self._send(404, self._simple_page("Already processed", "This draft has already been processed.", "#e74c3c"))
            return
        d["linkedin_text"] = li_text
        d["facebook_text"] = fb_text
        if scheduled_at:
            try:
                from zoneinfo import ZoneInfo
                import datetime as _dtmod
                from config import config as _pcfg
                tz_name = _pcfg.timezone or "UTC"
                naive_dt = _dtmod.datetime.fromisoformat(scheduled_at)
                aware_dt = naive_dt.replace(tzinfo=ZoneInfo(tz_name))
                utc_dt = aware_dt.astimezone(_dtmod.timezone.utc)
                d["scheduled_at"] = utc_dt.strftime("%Y-%m-%dT%H:%M:%S")
            except Exception as _e:
                logger.warning(f"Review schedule timezone conversion failed: {_e}")
                d["scheduled_at"] = scheduled_at
            d["status"] = "pending"
            _update_draft(d)
            self._send(200, self._simple_page("📅 Scheduled", f"Your post is scheduled for {scheduled_at}. It will publish automatically.", "#2ecc71"))
        else:
            d["status"] = "approved"
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
