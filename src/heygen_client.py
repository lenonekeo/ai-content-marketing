import time
import logging
import os
import requests
from config import config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.heygen.com"


def create_video(script: str) -> str:
    """Submit a HeyGen avatar video generation job. Returns video_id."""
    url = f"{BASE_URL}/v2/video/generate"
    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": config.heygen_avatar_id,
                    "avatar_style": "happy",
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
    resp.raise_for_status()
    data = resp.json()
    video_id = data["data"]["video_id"]
    logger.info(f"HeyGen video job created: {video_id}")
    return video_id


def wait_for_video(video_id: str, timeout: int = 600) -> str:
    """Poll until video is complete. Returns download URL."""
    url = f"{BASE_URL}/v1/video_status.get"
    headers = {"X-Api-Key": config.heygen_api_key}
    deadline = time.time() + timeout
    interval = 10

    while time.time() < deadline:
        resp = requests.get(url, params={"video_id": video_id}, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()["data"]
        status = data.get("status")
        logger.info(f"HeyGen video {video_id} status: {status}")

        if status == "completed":
            return data["video_url"]
        if status == "failed":
            raise RuntimeError(f"HeyGen video failed: {data.get('error')}")

        time.sleep(interval)
        interval = min(interval * 1.5, 30)

    raise TimeoutError(f"HeyGen video {video_id} timed out after {timeout}s")


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
