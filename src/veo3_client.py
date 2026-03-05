import time
import logging
import os
import requests
from google import genai
from google.genai import types
from config import config

logger = logging.getLogger(__name__)


def _get_client() -> genai.Client:
    return genai.Client(api_key=config.google_api_key)


def generate_video(prompt: str) -> any:
    """Submit a VEO video generation job. Returns operation object."""
    client = _get_client()
    logger.info("Submitting VEO video generation...")

    # Try generate_videos (1.x API) then fall back to generate_video (older API)
    generate_fn = getattr(client.models, "generate_videos", None) or getattr(client.models, "generate_video", None)
    if generate_fn is None:
        raise RuntimeError("VEO video generation not supported by the installed google-genai version")

    VideoConfig = getattr(types, "GenerateVideosConfig", None) or getattr(types, "GenerateVideoConfig", None)
    operation = generate_fn(
        model="veo-2.0-generate-001",
        prompt=prompt,
        config=VideoConfig(
            aspect_ratio="16:9",
            duration_seconds=8,
            number_of_videos=1,
        ),
    )
    logger.info(f"VEO operation started: {getattr(operation, 'name', operation)}")
    return operation


def wait_for_video(operation: any, timeout: int = 300) -> str:
    """Poll until VEO video is ready. Returns video download URI."""
    client = _get_client()
    deadline = time.time() + timeout
    interval = 15

    while time.time() < deadline:
        # Newer SDK expects the operation object; older SDK expects name string
        try:
            op = client.operations.get(operation)
        except (TypeError, AttributeError):
            op_name = getattr(operation, "name", operation)
            op = client.operations.get(op_name)

        logger.info(f"VEO operation status: done={op.done}")

        if op.done:
            resp = op.response
            videos = getattr(resp, "generated_videos", None) or getattr(resp, "videos", None)
            if not videos:
                raise RuntimeError("VEO completed but no video in response")
            video = videos[0]
            uri = getattr(video, "uri", None) or getattr(getattr(video, "video", None), "uri", None)
            logger.info(f"VEO video ready: {uri}")
            return uri

        operation = op
        time.sleep(interval)
        interval = min(interval * 1.3, 30)

    raise TimeoutError(f"VEO operation timed out after {timeout}s")

def download_video(uri: str, filename: str) -> str:
    """Download VEO video to downloads/. Returns local path."""
    os.makedirs(config.downloads_dir, exist_ok=True)
    path = os.path.join(config.downloads_dir, filename)

    download_url = uri
    if "?" not in download_url:
        download_url += f"?key={config.google_api_key}"

    resp = requests.get(download_url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    logger.info(f"VEO video downloaded to {path}")
    return path


def make_video(prompt: str, filename: str = "veo3_video.mp4") -> str:
    """Full pipeline: generate → poll → download. Returns local path."""
    operation = generate_video(prompt)
    video_uri = wait_for_video(operation)
    return download_video(video_uri, filename)
