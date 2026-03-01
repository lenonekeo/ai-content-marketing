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


def generate_video(prompt: str) -> str:
    """Submit a VEO 3 video generation job. Returns operation name."""
    client = _get_client()
    logger.info("Submitting VEO 3 video generation...")
    operation = client.models.generate_video(
        model="veo-3.0-generate-preview",
        prompt=prompt,
        config=types.GenerateVideoConfig(
            aspect_ratio="16:9",
            duration_seconds=8,
            number_of_videos=1,
        ),
    )
    logger.info(f"VEO 3 operation started: {operation.name}")
    return operation.name


def wait_for_video(operation_name: str, timeout: int = 300) -> str:
    """Poll until VEO 3 video is ready. Returns video download URI."""
    client = _get_client()
    deadline = time.time() + timeout
    interval = 15

    while time.time() < deadline:
        operation = client.operations.get(operation_name)
        logger.info(f"VEO 3 operation done: {operation.done}")

        if operation.done:
            if not operation.response or not operation.response.generated_videos:
                raise RuntimeError("VEO 3 completed but no video in response")
            video_uri = operation.response.generated_videos[0].video.uri
            logger.info(f"VEO 3 video ready: {video_uri}")
            return video_uri

        time.sleep(interval)
        interval = min(interval * 1.3, 30)

    raise TimeoutError(f"VEO 3 operation timed out after {timeout}s")


def download_video(uri: str, filename: str) -> str:
    """Download VEO 3 video to downloads/. Returns local path."""
    os.makedirs(config.downloads_dir, exist_ok=True)
    path = os.path.join(config.downloads_dir, filename)

    # URI may require API key auth
    download_url = uri
    if "?" not in download_url:
        download_url += f"?key={config.google_api_key}"

    resp = requests.get(download_url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    logger.info(f"VEO 3 video downloaded to {path}")
    return path


def make_video(prompt: str, filename: str = "veo3_video.mp4") -> str:
    """Full pipeline: generate → poll → download. Returns local path."""
    operation_name = generate_video(prompt)
    video_uri = wait_for_video(operation_name)
    return download_video(video_uri, filename)
