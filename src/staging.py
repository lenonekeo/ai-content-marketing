"""
Staging helpers — simulate social media posts without making real API calls.
Active when APP_ENV=staging.
"""
import logging

logger = logging.getLogger(__name__)


def simulate_post(platform: str, post_type: str, text: str = "", **kwargs) -> dict:
    """Return a fake success result and log what would have been posted."""
    fake_id = f"staging_{platform}_{post_type}_dry_run"
    logger.info(f"[STAGING] {platform} {post_type} simulated — no real post made.")
    logger.info(f"[STAGING] Preview: {text[:120]}")
    return {"success": True, "post_id": fake_id, "error": None}


def simulate_upload(platform: str, title: str = "", **kwargs) -> str:
    """Return a fake URL for upload simulations (e.g. YouTube)."""
    logger.info(f"[STAGING] {platform} upload simulated — no real upload made. Title: {title[:80]}")
    return f"https://staging.example.com/{platform}/dry_run"
