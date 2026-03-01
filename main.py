"""
AI Content Marketing App
Generates AI text + image + video content and posts to LinkedIn & Facebook.

Usage:
  python main.py run              # Run once immediately (full pipeline)
  python main.py run --text-only  # Run once, skip video & image generation
  python main.py run --no-video   # Run once, generate image but skip video
  python main.py start            # Start scheduled posting (production)
  python main.py status           # Show last 5 execution results
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.logger import setup_logging, log_execution, read_recent
from src.themes import get_theme_for_today
from src import content_generator, formatter, video_selector
from src import linkedin_poster, facebook_poster, notifier
from src import imagen_client
from config import config

setup_logging()
logger = logging.getLogger(__name__)


def _cleanup(*paths: str | None):
    for p in paths:
        if p and os.path.exists(p):
            os.remove(p)
            logger.info(f"Cleaned up: {p}")


def run_job(text_only: bool = False, no_video: bool = False, force_theme: str | None = None):
    logger.info("=" * 60)
    logger.info("Starting content marketing job")

    # 1. Select theme
    theme, industry = get_theme_for_today(force_theme=force_theme)
    logger.info(f"Theme: {theme['name']} | Industry: {industry}")

    # 2. Generate post text
    post_prompt = theme["post_prompt"].format(
        business_name=config.business_name,
        industry=industry,
    )
    post_text = content_generator.generate_post(post_prompt)
    logger.info(f"Post preview: {post_text[:100]}...")

    image_path = None
    video_path = None

    if not text_only:
        # 3. Generate Gemini image (always, as visual companion)
        if config.imagen_enabled:
            try:
                img_prompt = imagen_client.build_image_prompt(
                    theme["type"], post_text, industry
                )
                ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
                image_path = imagen_client.generate_image(
                    img_prompt, filename=f"imagen_{ts}.png"
                )
                logger.info(f"Gemini image ready: {image_path}")
            except Exception as e:
                logger.error(f"Gemini image generation failed: {e}")

        # 4. Generate video script (for HeyGen themes)
        script = None
        if not no_video and theme.get("script_prompt"):
            try:
                script = content_generator.generate_script(
                    post_text, theme["script_prompt"]
                )
            except Exception as e:
                logger.error(f"Script generation failed: {e}")

        # 5. Generate video (HeyGen or VEO 3)
        if not no_video:
            video_path = video_selector.get_video(theme, post_text, script)
            if video_path:
                logger.info(f"Video ready: {video_path}")
            else:
                logger.info("No video — will post with image if available")

    # 6. Format text for each platform
    li_text = formatter.format_linkedin(post_text, config.business_website)
    fb_text = formatter.format_facebook(post_text, config.business_website)

    # 7. Post to LinkedIn (video > image > text, in priority order)
    li_result = {"success": False, "post_id": None, "error": "LinkedIn not configured"}
    if config.linkedin_enabled and config.linkedin_author_urn:
        if video_path:
            li_result = linkedin_poster.post_video(li_text, video_path)
        elif image_path:
            li_result = linkedin_poster.post_image(li_text, image_path)
        else:
            li_result = linkedin_poster.post_text(li_text)
    else:
        logger.warning("LinkedIn not configured, skipping")

    # 8. Post to Facebook (video > image > text, in priority order)
    fb_result = {"success": False, "post_id": None, "error": "Facebook not configured"}
    if config.facebook_enabled and config.facebook_page_id:
        if video_path:
            fb_result = facebook_poster.post_video(fb_text, video_path)
        elif image_path:
            fb_result = facebook_poster.post_image(fb_text, image_path)
        else:
            fb_result = facebook_poster.post_text(fb_text)
    else:
        logger.warning("Facebook not configured, skipping")

    # 9. Determine what media was used
    media_used = "video" if video_path else ("image" if image_path else "text_only")

    # 10. Log results
    record = log_execution(
        theme=theme["type"],
        video_type=theme.get("video_type", "none") if not text_only else "none",
        linkedin=li_result,
        facebook=fb_result,
        content_preview=post_text,
    )
    record["media_used"] = media_used

    # 11. Cleanup temp files
    _cleanup(video_path, image_path)

    # 12. Send error notification if needed
    if not record["overall_success"]:
        notifier.send_error_email(record)

    logger.info(
        f"Job complete | Media: {media_used} | "
        f"LinkedIn: {'OK' if li_result['success'] else 'FAILED'} | "
        f"Facebook: {'OK' if fb_result['success'] else 'FAILED'}"
    )
    logger.info("=" * 60)
    return record


def cmd_status():
    records = read_recent(5)
    if not records:
        print("No executions found in logs/posts.jsonl")
        return
    print(f"\nLast {len(records)} executions:\n")
    for r in records:
        li = r.get("linkedin", {})
        fb = r.get("facebook", {})
        media = r.get("media_used", r.get("video_type", "?"))
        print(f"  {r['timestamp']}")
        print(f"    Theme:    {r['theme']}  |  Media: {media}")
        print(f"    LinkedIn: {'OK  ' if li.get('success') else 'FAIL'} {li.get('post_id') or li.get('error', '')}")
        print(f"    Facebook: {'OK  ' if fb.get('success') else 'FAIL'} {fb.get('post_id') or fb.get('error', '')}")
        print(f"    Preview:  {r.get('content_preview', '')[:80]}...")
        print()


def cmd_run(text_only: bool, no_video: bool, force_theme: str | None = None):
    try:
        run_job(text_only=text_only, no_video=no_video, force_theme=force_theme)
    except Exception as e:
        logger.exception(f"Job failed with unexpected error: {e}")
        sys.exit(1)


def cmd_start():
    from scheduler import start_scheduler
    logger.info(
        f"Starting scheduler: {config.post_days} at {config.post_hour:02d}:00 UTC"
    )
    start_scheduler()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Content Marketing App")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run once immediately")
    run_p.add_argument("--text-only", action="store_true", help="Skip all media generation")
    run_p.add_argument("--no-video", action="store_true", help="Generate image but skip video")
    run_p.add_argument("--theme", default=None, help="Force a specific theme: use_case, tips, success_story, trends, problem_solution, educational, service_highlight")

    sub.add_parser("start", help="Start scheduled posting")
    sub.add_parser("status", help="Show recent execution history")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(text_only=args.text_only, no_video=getattr(args, "no_video", False), force_theme=getattr(args, "theme", None))
    elif args.command == "start":
        cmd_start()
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()
