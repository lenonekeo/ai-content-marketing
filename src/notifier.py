import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import config

logger = logging.getLogger(__name__)


def send_approval_email(draft: dict, review_url: str):
    if not config.smtp_enabled or not config.contact_email:
        logger.warning("SMTP not configured, skipping approval email")
        return

    theme = draft.get("theme", "?").replace("_", " ").title()
    industry = draft.get("industry", "?")
    ts = draft.get("timestamp", "")[:19].replace("T", " ")
    li_text = draft.get("linkedin_text", "")
    fb_text = draft.get("facebook_text", "")

    html = f"""
    <div style="font-family:-apple-system,Arial,sans-serif;max-width:680px;margin:0 auto">
      <h2 style="color:#1a1a2e">Post Ready for Approval</h2>
      <p style="color:#666"><strong>Theme:</strong> {theme} &nbsp;|&nbsp;
         <strong>Industry:</strong> {industry} &nbsp;|&nbsp;
         <strong>Generated:</strong> {ts}</p>

      <p style="margin:24px 0">
        <a href="{review_url}"
           style="display:inline-block;padding:14px 32px;background:#2ecc71;color:#fff;
                  text-decoration:none;border-radius:8px;font-weight:bold;font-size:16px">
          Review &amp; Approve Post
        </a>
      </p>
      <p style="color:#aaa;font-size:12px;margin-bottom:24px">
        You can edit both posts in the review page before publishing.
      </p>

      <hr style="border:none;border-top:1px solid #eee;margin:24px 0">

      <h3 style="color:#1a1a2e;margin-bottom:10px">LinkedIn Draft</h3>
      <pre style="background:#f5f5f5;padding:16px;border-radius:8px;white-space:pre-wrap;
                  font-size:14px;line-height:1.6;color:#333">{li_text}</pre>

      <h3 style="color:#1a1a2e;margin:24px 0 10px">Facebook Draft</h3>
      <pre style="background:#f5f5f5;padding:16px;border-radius:8px;white-space:pre-wrap;
                  font-size:14px;line-height:1.6;color:#333">{fb_text}</pre>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Approval] {theme} — {ts}"
    msg["From"] = config.smtp_user
    msg["To"] = config.contact_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(config.smtp_user, config.smtp_password)
            server.sendmail(config.smtp_user, config.contact_email, msg.as_string())
        logger.info(f"Approval email sent to {config.contact_email}")
    except Exception as e:
        logger.error(f"Failed to send approval email: {e}")


def send_error_email(record: dict):
    if not config.smtp_enabled or not config.contact_email:
        logger.warning("SMTP not configured, skipping error email")
        return

    li = record.get("linkedin", {})
    fb = record.get("facebook", {})

    html = f"""
    <h2>Content Marketing - Posting Failure</h2>
    <p><strong>Timestamp:</strong> {record.get('timestamp')}</p>
    <p><strong>Content Theme:</strong> {record.get('theme')}</p>
    <p><strong>Video Type:</strong> {record.get('video_type', 'none')}</p>

    <h3>Platform Results</h3>
    <ul>
      <li><strong>LinkedIn:</strong> {'Success' if li.get('success') else 'FAILED - ' + str(li.get('error', 'unknown'))}</li>
      <li><strong>Facebook:</strong> {'Success' if fb.get('success') else 'FAILED - ' + str(fb.get('error', 'unknown'))}</li>
    </ul>

    <h3>Content Preview</h3>
    <pre>{record.get('content_preview', '')}</pre>

    <p>Check your VPS logs for full details: <code>journalctl -u content-marketing -n 50</code></p>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Content Marketing - Posting Failure"
    msg["From"] = config.smtp_user
    msg["To"] = config.contact_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(config.smtp_user, config.smtp_password)
            server.sendmail(config.smtp_user, config.contact_email, msg.as_string())
        logger.info(f"Error notification sent to {config.contact_email}")
    except Exception as e:
        logger.error(f"Failed to send error email: {e}")
