import logging
import mimetypes
import os
import requests
from config import config
from src.staging import simulate_post

logger = logging.getLogger(__name__)
API = "https://api.linkedin.com/v2"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.linkedin_access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


def post_text(text: str) -> dict:
    if config.is_staging:
        return simulate_post("linkedin", "text", text)
    author = config.linkedin_author_urn
    payload = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    try:
        resp = requests.post(f"{API}/ugcPosts", json=payload, headers=_headers(), timeout=30)
        resp.raise_for_status()
        post_id = resp.headers.get("x-restli-id", resp.json().get("id", "unknown"))
        logger.info(f"LinkedIn text post published: {post_id}")
        return {"success": True, "post_id": post_id, "error": None}
    except Exception as e:
        logger.error(f"LinkedIn text post failed: {e}")
        return {"success": False, "post_id": None, "error": str(e)}


def post_video(text: str, video_path: str) -> dict:
    if config.is_staging:
        return simulate_post("linkedin", "video", text)
    author = config.linkedin_author_urn
    file_size = os.path.getsize(video_path)

    # Step 1: Register upload
    try:
        register_payload = {
            "registerUploadRequest": {
                "owner": author,
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-video"],
                "serviceRelationships": [
                    {
                        "identifier": "urn:li:userGeneratedContent",
                        "relationshipType": "OWNER",
                    }
                ],
                "supportedUploadMechanism": ["SYNCHRONOUS_UPLOAD"],
            }
        }
        reg_resp = requests.post(
            f"{API}/assets?action=registerUpload",
            json=register_payload,
            headers=_headers(),
            timeout=30,
        )
        reg_resp.raise_for_status()
        reg_data = reg_resp.json()["value"]
        upload_url = reg_data["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
        asset_urn = reg_data["asset"]
        logger.info(f"LinkedIn upload registered, asset: {asset_urn}")

        # Step 2: Upload binary
        with open(video_path, "rb") as f:
            upload_headers = {
                "Authorization": f"Bearer {config.linkedin_access_token}",
                "Content-Type": "video/mp4",
                "Content-Length": str(file_size),
            }
            up_resp = requests.put(upload_url, data=f, headers=upload_headers, timeout=300)
            up_resp.raise_for_status()
        logger.info("LinkedIn video binary uploaded")

        # Step 3: Create post with video
        post_payload = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "VIDEO",
                    "media": [
                        {
                            "status": "READY",
                            "media": asset_urn,
                        }
                    ],
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        post_resp = requests.post(f"{API}/ugcPosts", json=post_payload, headers=_headers(), timeout=30)
        post_resp.raise_for_status()
        post_id = post_resp.headers.get("x-restli-id", "unknown")
        logger.info(f"LinkedIn video post published: {post_id}")
        return {"success": True, "post_id": post_id, "error": None}

    except Exception as e:
        logger.error(f"LinkedIn video post failed: {e}, falling back to text-only")
        return post_text(text)


def post_image(text: str, image_path: str) -> dict:
    """Post text + image to LinkedIn (3-step: register → upload → create post)."""
    if config.is_staging:
        return simulate_post("linkedin", "image", text)
    author = config.linkedin_author_urn
    mime_type = mimetypes.guess_type(image_path)[0] or "image/png"

    try:
        # Step 1: Register upload
        register_payload = {
            "registerUploadRequest": {
                "owner": author,
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "serviceRelationships": [
                    {
                        "identifier": "urn:li:userGeneratedContent",
                        "relationshipType": "OWNER",
                    }
                ],
                "supportedUploadMechanism": ["SYNCHRONOUS_UPLOAD"],
            }
        }
        reg_resp = requests.post(
            f"{API}/assets?action=registerUpload",
            json=register_payload,
            headers=_headers(),
            timeout=30,
        )
        reg_resp.raise_for_status()
        reg_data = reg_resp.json()["value"]
        upload_url = reg_data["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
        asset_urn = reg_data["asset"]
        logger.info(f"LinkedIn image upload registered, asset: {asset_urn}")

        # Step 2: Upload image binary
        with open(image_path, "rb") as f:
            upload_headers = {
                "Authorization": f"Bearer {config.linkedin_access_token}",
                "Content-Type": mime_type,
            }
            up_resp = requests.put(upload_url, data=f, headers=upload_headers, timeout=60)
            up_resp.raise_for_status()
        logger.info("LinkedIn image binary uploaded")

        # Step 3: Create post with image
        post_payload = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "IMAGE",
                    "media": [{"status": "READY", "media": asset_urn}],
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        post_resp = requests.post(
            f"{API}/ugcPosts", json=post_payload, headers=_headers(), timeout=30
        )
        post_resp.raise_for_status()
        post_id = post_resp.headers.get("x-restli-id", "unknown")
        logger.info(f"LinkedIn image post published: {post_id}")
        return {"success": True, "post_id": post_id, "error": None}

    except Exception as e:
        logger.error(f"LinkedIn image post failed: {e}, falling back to text-only")
        return post_text(text)
