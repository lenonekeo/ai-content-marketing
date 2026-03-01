import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import config

logger = logging.getLogger(__name__)


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
