import time
import logging
import os
import requests
from config import config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.heygen.com"


def _heygen_get(api_key: str, path: str, params: dict = None) -> dict:
    """Make an authenticated GET request to the HeyGen API."""
    resp = requests.get(
        f"{BASE_URL}{path}",
        headers={"X-Api-Key": api_key},
        params=params or {},
        timeout=15,
    )
    if not resp.ok:
        try:
            err_body = resp.json()
        except Exception:
            err_body = resp.text
        raise RuntimeError(f"HeyGen API error {resp.status_code}: {err_body}")
    return resp.json()


def list_avatars(api_key: str) -> list:
    """Return flat list of stock/public avatars."""
    data = _heygen_get(api_key, "/v2/avatars")
    return data.get("data", {}).get("avatars", []) or data.get("data", []) or []


def list_avatar_groups(api_key: str) -> list:
    """Return the user's own avatar groups (AI clones / InstantAvatars)."""
    data = _heygen_get(api_key, "/v2/avatar_group.list", {"include_public": "false"})
    return data.get("data", {}).get("avatar_group_list", []) or []


def list_group_looks(api_key: str, group_id: str) -> list:
    """Return individual looks within an avatar group. Each look has its own id used as avatar_id."""
    data = _heygen_get(api_key, f"/v2/avatar_group/{group_id}/avatars")
    return data.get("data", {}).get("avatar_list", []) or []


def create_video(script: str) -> str:
    """Submit a HeyGen avatar video generation job. Returns video_id."""
    if not config.heygen_api_key:
        raise RuntimeError("HEYGEN_API_KEY is not set — go to Setup and enter your HeyGen API key.")
    if not config.heygen_avatar_id:
        raise RuntimeError("HEYGEN_AVATAR_ID is not set — go to Setup and enter your avatar ID.")
    if not config.heygen_voice_id:
        raise RuntimeError("HEYGEN_VOICE_ID is not set — go to Setup and enter your voice ID.")

    logger.info(f"HeyGen create_video: avatar_id={config.heygen_avatar_id!r} voice_id={config.heygen_voice_id!r} key_prefix={config.heygen_api_key[:8]}...")
    url = f"{BASE_URL}/v2/video/generate"
    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": config.heygen_avatar_id,
                },
                "voice": {
                    "type": "text",
                    "input_text": script,
                    "voice_id": config.heygen_voice_id,
                },
            }
        ],
        "dimension": {"width": 720, "height": 1280},
        "aspect_ratio": "9:16",
    }
    headers = {
        "X-Api-Key": config.heygen_api_key,
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    if not resp.ok:
        try:
            err_body = resp.json()
        except Exception:
            err_body = resp.text
        raise RuntimeError(f"HeyGen API error {resp.status_code}: {err_body}")
    data = resp.json()
    if data.get("error") or not data.get("data"):
        raise RuntimeError(f"HeyGen API returned error: {data}")
    video_id = data["data"]["video_id"]
    logger.info(f"HeyGen video job created: {video_id}")
    return video_id


def wait_for_video(video_id: str, timeout: int = 1200) -> str:
    """Poll until video is complete. Returns download URL. Default 20 min timeout."""
    url = f"{BASE_URL}/v1/video_status.get"
    headers = {"X-Api-Key": config.heygen_api_key}
    deadline = time.time() + timeout
    interval = 15
    elapsed = 0

    while time.time() < deadline:
        resp = requests.get(url, params={"video_id": video_id}, headers=headers, timeout=15)
        if not resp.ok:
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            raise RuntimeError(f"HeyGen status check failed {resp.status_code}: {err_body}")
        data = resp.json().get("data", {})
        status = data.get("status")
        logger.info(f"HeyGen video {video_id} status: {status} (elapsed {elapsed}s)")

        if status == "completed":
            video_url = data.get("video_url")
            if not video_url:
                raise RuntimeError(f"HeyGen completed but no video_url in response: {data}")
            return video_url
        if status == "failed":
            error_detail = data.get("error") or data.get("msg") or str(data)
            raise RuntimeError(f"HeyGen video generation failed: {error_detail}")

        time.sleep(interval)
        elapsed += interval
        interval = min(interval * 1.3, 30)

    raise TimeoutError(
        f"HeyGen video {video_id} timed out after {timeout}s — "
        "the video is still processing in HeyGen. Check your HeyGen dashboard at app.heygen.com/videos to see if it completed."
    )


def download_video(url: str, filename: str) -> str:
    """Download video to downloads/ dir. Returns local file path."""
    os.makedirs(config.downloads_dir, exist_ok=True)
    path = os.path.join(config.downloads_dir, filename)
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    logger.info(f"HeyGen video downloaded to {path}")
    return path


def make_video(script: str, filename: str = "heygen_video.mp4") -> str:
    """Full pipeline: create → poll → download. Returns local path."""
    video_id = create_video(script)
    video_url = wait_for_video(video_id)
    return download_video(video_url, filename)
