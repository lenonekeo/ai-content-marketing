"""
AI Content Marketing App
Generates AI text + image + video content and posts to LinkedIn & Facebook.

Usage:
  python main.py run              # Run once immediately (full pipeline, no approval)
  python main.py run --text-only  # Run once, skip video & image generation
  python main.py run --no-video   # Run once, generate image but skip video
  python main.py run --draft      # Generate draft + send approval email (test approval flow)
  python main.py start            # Start scheduler + approval server (production)
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
from src import imagen_client, instagram_poster
from config import config

setup_logging()
logger = logging.getLogger(__name__)


def _cleanup(*paths: str | None):
    for p in paths:
        if p and os.path.exists(p):
            os.remove(p)
            logger.info(f"Cleaned up: {p}")


def _generate_content(text_only: bool = False, no_video: bool = False, force_theme: str | None = None):
    """Shared content generation logic. Returns (theme, industry, post_text, li_text, fb_text, image_path, video_path)."""
    theme, industry = get_theme_for_today(force_theme=force_theme)
    logger.info(f"Theme: {theme['name']} | Industry: {industry}")

    post_prompt = theme["post_prompt"].format(
        business_name=config.business_name,
        industry=industry,
    )
    post_text = content_generator.generate_post(post_prompt)
    logger.info(f"Post preview: {post_text[:100]}...")

    image_path = None
    video_path = None

    if not text_only:
        if config.imagen_enabled:
            try:
                import datetime as _dt
                img_prompt = imagen_client.build_image_prompt(theme["type"], post_text, industry)
                ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                image_path = imagen_client.generate_image(img_prompt, filename=f"imagen_{ts}.png")
                logger.info(f"Gemini image ready: {image_path}")
            except Exception as e:
                logger.error(f"Gemini image generation failed: {e}")

        script = None
        if not no_video and theme.get("script_prompt"):
            try:
                script = content_generator.generate_script(post_text, theme["script_prompt"])
            except Exception as e:
                logger.error(f"Script generation failed: {e}")

        if not no_video:
            video_path = video_selector.get_video(theme, post_text, script)
            if video_path:
                logger.info(f"Video ready: {video_path}")
            else:
                logger.info("No video — will post with image if available")

    li_text = formatter.format_linkedin(post_text, config.business_website)
    fb_text = formatter.format_facebook(post_text, config.business_website)
    return theme, industry, post_text, li_text, fb_text, image_path, video_path


def _do_post(li_text: str, fb_text: str, video_path: str | None, image_path: str | None):
    """Core posting logic. Returns (li_result, fb_result)."""
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

    return li_result, fb_result


def publish_draft(draft: dict):
    """Post an approved draft to LinkedIn, Facebook, and optionally Instagram."""
    logger.info(f"Publishing approved draft: {draft['draft_id']}")
    li_text = draft.get("linkedin_text", "")
    fb_text = draft.get("facebook_text", "")
    video_path = draft.get("video_path")
    image_path = draft.get("image_path")
    image_url = draft.get("image_url", "")  # URL-based image from Create page

    if video_path and not os.path.exists(video_path):
        logger.warning(f"Video file missing: {video_path}, falling back")
        video_path = None
    if image_path and not os.path.exists(image_path):
        logger.warning(f"Image file missing: {image_path}, falling back")
        image_path = None

    li_result, fb_result = _do_post(li_text, fb_text, video_path, image_path)
    media_used = "video" if video_path else ("image" if image_path else "text_only")

    # Instagram (only for drafts that have instagram selected as a platform)
    ig_result = {"success": False, "post_id": None, "error": "not selected"}
    platforms = draft.get("platforms", [])
    if "instagram" in platforms and config.instagram_enabled:
        ig_caption = draft.get("instagram_caption") or draft.get("post_text", li_text)
        video_url = draft.get("video_url", "")
        if video_path:
            # Local video file — cannot use directly with Instagram (needs public URL)
            ig_result = {"success": False, "post_id": None, "error": "Local video file not supported for Instagram; use a public video URL"}
        elif video_url:
            ig_result = instagram_poster.post_video(ig_caption, video_url)
        elif image_path:
            # Local file — cannot use with Instagram
            ig_result = {"success": False, "post_id": None, "error": "Local image file not supported for Instagram; use an image URL"}
        elif image_url:
            ig_result = instagram_poster.post_image(ig_caption, image_url)
        else:
            ig_result = {"success": False, "post_id": None, "error": "Instagram requires an image or video URL"}
        logger.info(f"Instagram: {'OK' if ig_result['success'] else 'FAILED'} — {ig_result.get('error') or ig_result.get('post_id')}")

    record = log_execution(
        theme=draft["theme"],
        video_type=draft.get("video_type", "none"),
        linkedin=li_result,
        facebook=fb_result,
        content_preview=draft.get("post_text", li_text),
    )
    record["media_used"] = media_used
    record["instagram"] = ig_result
    _cleanup(video_path, image_path)

    if not record["overall_success"]:
        notifier.send_error_email(record)

    ig_summary = f" | Instagram: {'OK' if ig_result['success'] else 'N/A'}" if "instagram" in platforms else ""
    logger.info(
        f"Draft published | Media: {media_used} | "
        f"LinkedIn: {'OK' if li_result['success'] else 'FAILED'} | "
        f"Facebook: {'OK' if fb_result['success'] else 'FAILED'}"
        + ig_summary
    )


def generate_draft(text_only: bool = False, no_video: bool = False, force_theme: str | None = None):
    """Generate content, save as pending draft, send approval email. Used by scheduler."""
    from src.approver import save_draft
    logger.info("=" * 60)
    logger.info("Generating draft for approval")

    theme, industry, post_text, li_text, fb_text, image_path, video_path = _generate_content(
        text_only=text_only, no_video=no_video, force_theme=force_theme
    )

    draft = save_draft({
        "theme": theme["type"],
        "industry": industry,
        "post_text": post_text,
        "linkedin_text": li_text,
        "facebook_text": fb_text,
        "video_path": video_path,
        "image_path": image_path,
        "video_type": theme.get("video_type", "none"),
    })

    review_url = f"http://{config.vps_host}:{config.approval_port}/review?token={draft['token']}"
    notifier.send_approval_email(draft, review_url)
    logger.info(f"Draft ready — approval email sent. Review: {review_url}")
    logger.info("=" * 60)


def run_job(text_only: bool = False, no_video: bool = False, force_theme: str | None = None):
    """Full pipeline: generate content + post immediately (no approval). Used for direct testing."""
    logger.info("=" * 60)
    logger.info("Starting content marketing job (direct, no approval)")

    theme, industry, post_text, li_text, fb_text, image_path, video_path = _generate_content(
        text_only=text_only, no_video=no_video, force_theme=force_theme
    )

    li_result, fb_result = _do_post(li_text, fb_text, video_path, image_path)
    media_used = "video" if video_path else ("image" if image_path else "text_only")

    record = log_execution(
        theme=theme["type"],
        video_type=theme.get("video_type", "none") if not text_only else "none",
        linkedin=li_result,
        facebook=fb_result,
        content_preview=post_text,
    )
    record["media_used"] = media_used
    _cleanup(video_path, image_path)

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


def cmd_run(text_only: bool, no_video: bool, force_theme: str | None = None, draft: bool = False):
    try:
        if draft:
            generate_draft(text_only=text_only, no_video=no_video, force_theme=force_theme)
            logger.info("Draft generated. Start the approval server with 'python main.py start' or check the logged URL.")
        else:
            run_job(text_only=text_only, no_video=no_video, force_theme=force_theme)
    except Exception as e:
        logger.exception(f"Job failed with unexpected error: {e}")
        sys.exit(1)


def cmd_start():
    from scheduler import start_scheduler
    if config.approval_required:
        from src.approver import start_approval_server
        start_approval_server(publish_draft, port=config.approval_port)
        logger.info(
            f"Approval server running on port {config.approval_port} — "
            f"review URL: http://{config.vps_host}:{config.approval_port}/review?token=<token>"
        )
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
    run_p.add_argument("--draft", action="store_true", help="Generate draft + send approval email instead of posting directly")
    run_p.add_argument("--theme", default=None, help="Force a specific theme: use_case, tips, success_story, trends, problem_solution, educational, service_highlight")

    sub.add_parser("start", help="Start scheduled posting")
    sub.add_parser("status", help="Show recent execution history")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(text_only=args.text_only, no_video=getattr(args, "no_video", False), force_theme=getattr(args, "theme", None), draft=getattr(args, "draft", False))
    elif args.command == "start":
        cmd_start()
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()
