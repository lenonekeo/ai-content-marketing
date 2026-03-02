"""
Draft management and HTTP approval server.

Saves generated post drafts to disk and serves a simple web UI for reviewing,
editing, and approving/rejecting posts before publishing to social media.
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


_publish_callback = None  # set by start_approval_server


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path)
        qs = parse_qs(p.query)
        token = qs.get("token", [None])[0]
        if p.path == "/review":
            self._review(token)
        elif p.path == "/reject":
            self._reject(token)
        else:
            self._send(404, "<h2>Not found</h2>")

    def do_POST(self):
        p = urlparse(self.path)
        qs = parse_qs(p.query)
        token = qs.get("token", [None])[0]
        if p.path == "/publish":
            n = int(self.headers.get("Content-Length", 0))
            body = parse_qs(self.rfile.read(n).decode())
            li = body.get("linkedin_text", [""])[0]
            fb = body.get("facebook_text", [""])[0]
            self._publish(token, li, fb)
        else:
            self._send(404, "<h2>Not found</h2>")

    def _review(self, token):
        d = _find_by_token(token)
        if not d:
            self._send(404, self._page("Draft not found", "This draft was not found or has already been processed.", "#e74c3c"))
            return

        li = d.get("linkedin_text", "").replace("&", "&amp;").replace("<", "&lt;")
        fb = d.get("facebook_text", "").replace("&", "&amp;").replace("<", "&lt;")
        ts = d.get("timestamp", "")[:19].replace("T", " ")

        html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review Post — {d.get("theme", "").replace("_", " ").title()}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; background: #f0f2f5; min-height: 100vh; padding: 20px; }}
  .card {{ background: #fff; border-radius: 12px; max-width: 740px; margin: 0 auto; padding: 32px; box-shadow: 0 2px 12px rgba(0,0,0,.08); }}
  h1 {{ font-size: 22px; color: #1a1a2e; margin-bottom: 6px; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 28px; }}
  .meta span {{ background: #f0f2f5; border-radius: 4px; padding: 2px 8px; margin-right: 6px; }}
  label {{ font-weight: 600; font-size: 14px; color: #444; display: block; margin-bottom: 8px; margin-top: 24px; }}
  .hint {{ font-weight: 400; color: #aaa; font-size: 12px; margin-left: 6px; }}
  textarea {{ width: 100%; height: 230px; font-size: 14px; line-height: 1.6; padding: 14px; border: 1px solid #ddd; border-radius: 8px; resize: vertical; color: #222; }}
  textarea:focus {{ outline: none; border-color: #2ecc71; box-shadow: 0 0 0 3px rgba(46,204,113,.15); }}
  .actions {{ margin-top: 28px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
  .btn {{ padding: 13px 28px; font-size: 15px; font-weight: 600; cursor: pointer; border: none; border-radius: 8px; transition: opacity .2s; }}
  .btn:hover {{ opacity: .88; }}
  .publish {{ background: #2ecc71; color: #fff; }}
  .reject {{ background: #fff; color: #e74c3c; border: 2px solid #e74c3c; }}
  .divider {{ border: none; border-top: 1px solid #eee; margin: 28px 0 0; }}
</style>
</head><body>
<div class="card">
  <h1>Review Draft Post</h1>
  <p class="meta">
    <span>{d.get("theme", "?").replace("_", " ").title()}</span>
    <span>{d.get("industry", "?")}</span>
    <span>{ts}</span>
  </p>

  <form method="POST" action="/publish?token={token}">
    <label>LinkedIn Post <span class="hint">editable — changes will be published as-is</span></label>
    <textarea name="linkedin_text">{li}</textarea>

    <label>Facebook Post <span class="hint">editable</span></label>
    <textarea name="facebook_text">{fb}</textarea>

    <div class="actions">
      <button class="btn publish" type="submit">Publish Now</button>
    </div>
  </form>

  <hr class="divider">
  <div style="margin-top:20px">
    <form method="GET" action="/reject">
      <input type="hidden" name="token" value="{token}">
      <button class="btn reject" type="submit">Reject &amp; Discard</button>
    </form>
  </div>
</div>
</body></html>"""
        self._send(200, html)

    def _publish(self, token, li_text, fb_text):
        d = _find_by_token(token)
        if not d:
            self._send(404, self._page("Already processed", "This draft was not found or has already been processed.", "#e74c3c"))
            return
        d["status"] = "approved"
        d["linkedin_text"] = li_text
        d["facebook_text"] = fb_text
        _update_draft(d)
        if _publish_callback:
            threading.Thread(target=_publish_callback, args=(d,), daemon=True).start()
        self._send(200, self._page(
            "✅ Approved! Publishing now...",
            "Your post is being published to LinkedIn and Facebook. Check your feeds in a few minutes.",
            "#2ecc71",
        ))

    def _reject(self, token):
        d = _find_by_token(token)
        if not d:
            self._send(404, self._page("Not found", "Draft not found.", "#e74c3c"))
            return
        d["status"] = "rejected"
        _update_draft(d)
        self._send(200, self._page(
            "❌ Post rejected",
            "The draft has been discarded. No post was published.",
            "#e74c3c",
        ))

    def _page(self, title, message, color):
        return f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title></head>
<body style="font-family:-apple-system,Arial,sans-serif;text-align:center;padding:80px 20px;background:#f0f2f5">
<div style="background:#fff;border-radius:12px;max-width:500px;margin:0 auto;padding:48px 32px;box-shadow:0 2px 12px rgba(0,0,0,.08)">
  <h2 style="color:{color};margin-bottom:16px">{title}</h2>
  <p style="color:#666;font-size:15px">{message}</p>
</div></body></html>"""

    def _send(self, code, html):
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        logger.debug(f"ApprovalServer: {fmt % args}")


def start_approval_server(publish_callback, port: int = 8080):
    """Start the HTTP approval server in a background daemon thread."""
    global _publish_callback
    _publish_callback = publish_callback
    server = HTTPServer(("0.0.0.0", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info(f"Approval server started on port {port}")
    return server
