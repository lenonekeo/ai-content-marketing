"""
Remotion client — renders video compositions via subprocess.

Compositions:
  PostCard  - Animated social media post card (1080x1080, 8s)
  Intro     - Branded YouTube intro (1920x1080, 3s)
  Outro     - Branded YouTube outro with CTA (1920x1080, 6s)

Requires Node.js + Remotion installed in the remotion/ subfolder.
Uses ffmpeg for intro/outro stitching (must be on PATH).
"""

import datetime
import json
import logging
import os
import subprocess
import tempfile

from config import config

logger = logging.getLogger(__name__)

_REMOTION_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "remotion")
)
_ENTRY = "src/index.jsx"


def _render(composition_id: str, props: dict, output_path: str, timeout: int = 300) -> str:
    """Call npx remotion render and return the output path."""
    abs_output = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)

    cmd = [
        "npx", "remotion", "render",
        _ENTRY,
        composition_id,
        abs_output,
        f"--props={json.dumps(props)}",
        "--gl=swiftshader",          # software rendering — required on VPS (no GPU)
        "--disable-web-security",    # needed on headless Linux
    ]

    logger.info(f"Remotion: rendering {composition_id} → {abs_output}")
    result = subprocess.run(
        cmd,
        cwd=_REMOTION_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Remotion render failed for {composition_id}:\n{result.stderr[-2000:]}"
        )

    if not os.path.exists(abs_output):
        raise RuntimeError(
            f"Remotion render reported success but output not found: {abs_output}"
        )

    logger.info(f"Remotion: render complete → {abs_output}")
    return abs_output


def render_post_card(post_text: str, filename: str) -> str:
    """
    Render an animated post card video (1080x1080).
    Returns the local mp4 path.
    """
    output_path = os.path.join(config.downloads_dir, filename)
    props = {
        "text": post_text,
        "businessName": config.business_name,
        "website": config.business_website,
    }
    return _render("PostCard", props, output_path)


def render_intro(filename: str) -> str:
    """
    Render the branded intro clip (1920x1080, 3s).
    Returns the local mp4 path.
    """
    output_path = os.path.join(config.downloads_dir, filename)
    props = {
        "businessName": config.business_name,
        "tagline": "AI Automation Experts",
    }
    return _render("Intro", props, output_path, timeout=120)


def render_outro(filename: str) -> str:
    """
    Render the branded outro clip (1920x1080, 6s).
    Returns the local mp4 path.
    """
    output_path = os.path.join(config.downloads_dir, filename)
    props = {
        "businessName": config.business_name,
        "website": config.business_website,
        "ctaText": "Book a free discovery call",
    }
    return _render("Outro", props, output_path, timeout=180)


def stitch_intro_outro(main_video_path: str) -> str | None:
    """
    Render intro + outro and stitch them around the main video using ffmpeg.
    Returns the stitched mp4 path, or None if ffmpeg is unavailable.

    Note: all three clips must share the same resolution and codec for
    -c copy to work. If they differ, re-encoding is applied automatically.
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    intro_path = None
    outro_path = None
    concat_file = None

    try:
        logger.info("Remotion: rendering intro + outro for YouTube stitching")
        intro_path = render_intro(f"intro_{ts}.mp4")
        outro_path = render_outro(f"outro_{ts}.mp4")

        # Write ffmpeg concat list
        fd, concat_file = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w") as f:
            f.write(f"file '{os.path.abspath(intro_path)}'\n")
            f.write(f"file '{os.path.abspath(main_video_path)}'\n")
            f.write(f"file '{os.path.abspath(outro_path)}'\n")

        stitched_path = os.path.join(
            config.downloads_dir, f"stitched_{ts}.mp4"
        )

        ffmpeg_result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_file,
                "-c:v", "libx264", "-c:a", "aac",
                "-movflags", "+faststart",
                stitched_path,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )

        if ffmpeg_result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg concat failed:\n{ffmpeg_result.stderr[-1500:]}"
            )

        logger.info(f"Remotion: stitched video ready → {stitched_path}")
        return stitched_path

    except FileNotFoundError:
        logger.warning("ffmpeg not found on PATH — skipping intro/outro stitching")
        return None
    except Exception as e:
        logger.error(f"Intro/outro stitching failed: {e}")
        return None
    finally:
        for p in [intro_path, outro_path, concat_file]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
