"""
Instagram Graph API poster.

Supports posting images (Feed) and videos (Reels) to an Instagram Business
or Creator account linked to a Facebook Page.

Requirements:
  - Instagram Business or Creator account connected to a Facebook Page
  - Facebook Page Access Token with permissions:
      instagram_basic, instagram_content_publish, pages_read_engagement
  - INSTAGRAM_ACCOUNT_ID: numeric ID of the Instagram Business/Creator account
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)


def _is_staging():
    from config import config
    return config.is_staging


def _simulate(post_type: str, caption: str):
    from src.staging import simulate_post
    return simulate_post("instagram", post_type, caption)

IG_API_BASE = "https://graph.facebook.com/v18.0"


def _cfg():
    from config import config
    return config.instagram_access_token, config.instagram_account_id


def post_image(caption: str, image_url: str) -> dict:
    """
    Post an image with caption to the Instagram Feed.
    image_url must be a publicly accessible HTTPS URL (JPEG or PNG).
    Returns {"success": bool, "post_id": str|None, "error": str|None}.
    """
    if _is_staging():
        return _simulate("image", caption)
    token, account_id = _cfg()
    if not token or not account_id:
        return {"success": False, "post_id": None, "error": "Instagram not configured"}

    try:
        # Step 1: Create media container
        r = requests.post(
            f"{IG_API_BASE}/{account_id}/media",
            params={
                "image_url": image_url,
                "caption": caption,
                "access_token": token,
            },
            timeout=60,
        )
        r.raise_for_status()
        creation_id = r.json().get("id")
        if not creation_id:
            return {"success": False, "post_id": None, "error": f"No creation_id returned: {r.text[:200]}"}

        # Step 2: Publish the container
        r2 = requests.post(
            f"{IG_API_BASE}/{account_id}/media_publish",
            params={
                "creation_id": creation_id,
                "access_token": token,
            },
            timeout=60,
        )
        r2.raise_for_status()
        post_id = r2.json().get("id")
        logger.info(f"Instagram image posted: {post_id}")
        return {"success": True, "post_id": post_id, "error": None}

    except Exception as e:
        logger.error(f"Instagram post_image failed: {e}")
        return {"success": False, "post_id": None, "error": str(e)}


def post_video(caption: str, video_url: str) -> dict:
    """
    Post a video as an Instagram Reel (shared to feed).
    video_url must be a publicly accessible HTTPS URL (MP4, H.264, max 15 min).
    Returns {"success": bool, "post_id": str|None, "error": str|None}.
    """
    if _is_staging():
        return _simulate("video", caption)
    token, account_id = _cfg()
    if not token or not account_id:
        return {"success": False, "post_id": None, "error": "Instagram not configured"}

    try:
        # Step 1: Create Reel media container
        r = requests.post(
            f"{IG_API_BASE}/{account_id}/media",
            params={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "share_to_feed": "true",
                "access_token": token,
            },
            timeout=60,
        )
        r.raise_for_status()
        creation_id = r.json().get("id")
        if not creation_id:
            return {"success": False, "post_id": None, "error": f"No creation_id returned: {r.text[:200]}"}

        # Step 2: Poll until processing is complete (up to 3 minutes)
        for _ in range(18):
            time.sleep(10)
            status_r = requests.get(
                f"{IG_API_BASE}/{creation_id}",
                params={"fields": "status_code", "access_token": token},
                timeout=30,
            )
            status = status_r.json().get("status_code", "")
            if status == "FINISHED":
                break
            elif status == "ERROR":
                return {"success": False, "post_id": None, "error": "Instagram video processing failed"}

        # Step 3: Publish
        r2 = requests.post(
            f"{IG_API_BASE}/{account_id}/media_publish",
            params={"creation_id": creation_id, "access_token": token},
            timeout=60,
        )
        r2.raise_for_status()
        post_id = r2.json().get("id")
        logger.info(f"Instagram video/reel posted: {post_id}")
        return {"success": True, "post_id": post_id, "error": None}

    except Exception as e:
        logger.error(f"Instagram post_video failed: {e}")
        return {"success": False, "post_id": None, "error": str(e)}
