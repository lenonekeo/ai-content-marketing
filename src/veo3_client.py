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

    generate_fn = getattr(client.models, "generate_videos", None) or getattr(client.models, "generate_video", None)
    if generate_fn is None:
        raise RuntimeError("VEO video generation not supported by the installed google-genai version")

    VideoConfig = getattr(types, "GenerateVideosConfig", None) or getattr(types, "GenerateVideoConfig", None)
    operation = generate_fn(
        model="veo-3.1-generate-preview",
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
    if "alt=media" not in download_url:
        download_url += ("&" if "?" in download_url else "?") + "alt=media"
    if "key=" not in download_url:
        download_url += "&key=" + config.google_api_key

    resp = requests.get(download_url, stream=True, timeout=300)
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    size = os.path.getsize(path)
    logger.info(f"VEO video downloaded to {path} ({size} bytes)")
    if size == 0:
        raise RuntimeError("Downloaded video is 0 bytes")
    return path


def caption_video(video_path: str, caption_text: str) -> str:
    """Burn word-chunked captions into video with ffmpeg. Returns video_path."""
    import subprocess
    import shutil
    if not shutil.which("ffmpeg"):
        logger.warning("ffmpeg not found - skipping captions")
        return video_path
    words = caption_text.replace("\n", " ").split()[:50]
    chunk_size = 5
    chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
    if not chunks:
        return video_path
    duration = 8.0
    chunk_dur = duration / len(chunks)
    filters = []
    for i, chunk in enumerate(chunks):
        start = i * chunk_dur
        end = start + chunk_dur
        safe = chunk.replace("'", "").replace(":", " ").replace("\\", "")
        filters.append(
            f"drawtext=text='{safe}':"
            f"fontsize=38:fontcolor=white:x=(w-text_w)/2:y=h*0.82:"
            f"box=1:boxcolor=black@0.55:boxborderw=8:"
            f"enable='between(t\\,{start:.2f}\\,{end:.2f})'"
        )
    vf = ",".join(filters)
    tmp = video_path.replace(".mp4", "_cap.mp4")
    result = subprocess.run(
        ["ffmpeg", "-i", video_path, "-vf", vf, "-c:a", "copy", "-y", tmp],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0 and os.path.getsize(tmp) > 0:
        os.replace(tmp, video_path)
        logger.info(f"Captions burned into {video_path}")
    else:
        logger.warning(f"ffmpeg captions failed: {result.stderr[-300:]}")
        if os.path.exists(tmp):
            os.remove(tmp)
    return video_path


def make_video(prompt: str, filename: str = "veo3_video.mp4", caption_text: str = None) -> str:
    """Full pipeline: generate -> poll -> download -> caption. Returns local path."""
    operation = generate_video(prompt)
    video_uri = wait_for_video(operation)
    path = download_video(video_uri, filename)
    if caption_text:
        caption_video(path, caption_text)
    return path