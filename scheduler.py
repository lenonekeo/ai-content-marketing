import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from config import config

logger = logging.getLogger(__name__)

_scheduler: BlockingScheduler | None = None


def reschedule_job(days: str, hour: int, minute: int, tz: str):
    """Update the posting schedule live — no service restart needed."""
    if _scheduler is None:
        logger.warning("reschedule_job called but scheduler is not running")
        return
    try:
        _scheduler.reschedule_job(
            "content_marketing_post",
            trigger=CronTrigger(
                day_of_week=days,
                hour=hour,
                minute=minute,
                timezone=tz,
            ),
        )
        logger.info(f"Schedule updated live: {days} at {hour:02d}:{minute:02d} {tz}")
    except Exception as e:
        logger.error(f"Failed to reschedule job: {e}")


def start_scheduler():
    global _scheduler

    if config.approval_required:
        from main import generate_draft as job_fn
        logger.info("Approval required — scheduler will generate drafts and send approval emails")
    else:
        from main import run_job as job_fn
        logger.info("No approval required — scheduler will post directly")

    tz = config.timezone or "UTC"
    _scheduler = BlockingScheduler(timezone=tz)
    _scheduler.add_job(
        job_fn,
        trigger=CronTrigger(
            day_of_week=config.post_days,
            hour=config.post_hour,
            minute=config.post_minute,
            timezone=tz,
        ),
        id="content_marketing_post",
        name="content_marketing_post",
        misfire_grace_time=3600,   # Allow up to 1h late if server was down
        coalesce=True,             # Run once even if multiple triggers missed
    )

    logger.info(
        f"Scheduler started. Next runs: {config.post_days} at "
        f"{config.post_hour:02d}:{config.post_minute:02d} {tz}"
    )

    try:
        _scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
        _scheduler.shutdown()
