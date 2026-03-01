import json
import logging
import logging.handlers
import os
from datetime import datetime
from config import config


def setup_logging():
    os.makedirs("logs", exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(),
            logging.handlers.RotatingFileHandler(
                "logs/app.log", maxBytes=5 * 1024 * 1024, backupCount=3
            ),
        ],
    )


def log_execution(
    theme: str,
    video_type: str,
    linkedin: dict,
    facebook: dict,
    content_preview: str,
):
    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "theme": theme,
        "video_type": video_type,
        "content_preview": content_preview[:200],
        "linkedin": linkedin,
        "facebook": facebook,
        "overall_success": linkedin.get("success") or facebook.get("success"),
    }
    os.makedirs("logs", exist_ok=True)
    with open(config.logs_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


def read_recent(n: int = 5) -> list[dict]:
    if not os.path.exists(config.logs_file):
        return []
    with open(config.logs_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    records = []
    for line in lines[-n:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return list(reversed(records))
