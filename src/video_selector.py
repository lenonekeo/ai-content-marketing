import logging
from datetime import datetime
from config import config
from src import heygen_client, veo3_client

logger = logging.getLogger(__name__)


def get_video(theme: dict, post_text: str, script: str | None) -> str | None:
    """
    Route to HeyGen or VEO 3 based on theme preference.
    Returns local mp4 path, or None on failure (allows text-only fallback).
    """
    video_type = theme.get("video_type")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if video_type == "heygen":
        if not config.heygen_enabled:
            logger.warning("HeyGen not configured, skipping video")
            return None
        if not script:
            logger.warning("No script for HeyGen, skipping video")
            return None
        try:
            filename = f"heygen_{timestamp}.mp4"
            return heygen_client.make_video(script, filename)
        except Exception as e:
            logger.error(f"HeyGen video failed: {e}")
            return None

    elif video_type == "veo3":
        if not config.veo3_enabled:
            logger.warning("VEO 3 not configured, skipping video")
            return None
        veo_prompt = theme.get("veo_prompt")
        if not veo_prompt:
            logger.warning("No VEO prompt for this theme, skipping video")
            return None
        try:
            filename = f"veo3_{timestamp}.mp4"
            return veo3_client.make_video(veo_prompt, filename)
        except Exception as e:
            logger.error(f"VEO 3 video failed: {e}")
            return None

    logger.info("No video type set for this theme")
    return None
