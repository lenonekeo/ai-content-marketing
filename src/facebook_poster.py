import logging
import requests
from config import config

logger = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com/v18.0"


def _params() -> dict:
    return {"access_token": config.facebook_access_token}


def post_text(text: str) -> dict:
    url = f"{GRAPH}/{config.facebook_page_id}/feed"
    try:
        resp = requests.post(url, params=_params(), data={"message": text}, timeout=30)
        resp.raise_for_status()
        post_id = resp.json().get("id", "unknown")
        logger.info(f"Facebook text post published: {post_id}")
        return {"success": True, "post_id": post_id, "error": None}
    except Exception as e:
        logger.error(f"Facebook text post failed: {e}")
        return {"success": False, "post_id": None, "error": str(e)}


def post_video(text: str, video_path: str) -> dict:
    url = f"{GRAPH}/{config.facebook_page_id}/videos"
    try:
        with open(video_path, "rb") as f:
            resp = requests.post(
                url,
                params=_params(),
                data={"description": text},
                files={"source": ("video.mp4", f, "video/mp4")},
                timeout=300,
            )
        resp.raise_for_status()
        post_id = resp.json().get("id", "unknown")
        logger.info(f"Facebook video post published: {post_id}")
        return {"success": True, "post_id": post_id, "error": None}
    except Exception as e:
        logger.error(f"Facebook video post failed: {e}, falling back to text-only")
        return post_text(text)


def post_image(text: str, image_path: str) -> dict:
    """Post text + image to Facebook Page."""
    url = f"{GRAPH}/{config.facebook_page_id}/photos"
    try:
        with open(image_path, "rb") as f:
            resp = requests.post(
                url,
                params=_params(),
                data={"caption": text},
                files={"source": ("image.png", f, "image/png")},
                timeout=60,
            )
        resp.raise_for_status()
        post_id = resp.json().get("id", "unknown")
        logger.info(f"Facebook image post published: {post_id}")
        return {"success": True, "post_id": post_id, "error": None}
    except Exception as e:
        logger.error(f"Facebook image post failed: {e}, falling back to text-only")
        return post_text(text)
