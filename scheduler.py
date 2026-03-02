import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from config import config

logger = logging.getLogger(__name__)


def start_scheduler():
    if config.approval_required:
        from main import generate_draft as job_fn
        logger.info("Approval required — scheduler will generate drafts and send approval emails")
    else:
        from main import run_job as job_fn
        logger.info("No approval required — scheduler will post directly")

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        job_fn,
        trigger=CronTrigger(
            day_of_week=config.post_days,
            hour=config.post_hour,
            minute=0,
        ),
        name="content_marketing_post",
        misfire_grace_time=3600,   # Allow up to 1h late if server was down
        coalesce=True,             # Run once even if multiple triggers missed
    )

    logger.info(
        f"Scheduler started. Next runs: {config.post_days} at {config.post_hour:02d}:00 UTC"
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
        scheduler.shutdown()
