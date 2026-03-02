"""
Content influence management.

Stores brand guidelines, topics, style examples, and audience description
that guide the AI when generating social media content.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

INFLUENCE_FILE = "influence.json"

_FIELDS = {
    "topics": "",
    "target_audience": "",
    "brand_voice": "",
    "style_notes": "",
    "example_posts": "",
    "avoid": "",
}


def load() -> dict:
    if os.path.exists(INFLUENCE_FILE):
        try:
            with open(INFLUENCE_FILE) as f:
                return {**_FIELDS, **json.load(f)}
        except Exception as e:
            logger.warning(f"Could not load influence.json: {e}")
    return dict(_FIELDS)


def save(data: dict):
    out = {k: str(data.get(k, v)).strip() for k, v in _FIELDS.items()}
    with open(INFLUENCE_FILE, "w") as f:
        json.dump(out, f, indent=2)
    logger.info("influence.json saved")


def get_prompt_context() -> str:
    """Return additional brand context to inject into AI post prompts."""
    d = load()
    parts = []
    if d.get("topics"):
        parts.append(f"Focus on these topics/keywords: {d['topics']}")
    if d.get("target_audience"):
        parts.append(f"Target audience: {d['target_audience']}")
    if d.get("brand_voice"):
        parts.append(f"Brand voice and tone: {d['brand_voice']}")
    if d.get("style_notes"):
        parts.append(f"Additional style guidance: {d['style_notes']}")
    if d.get("avoid"):
        parts.append(f"Avoid these topics or phrases: {d['avoid']}")
    if d.get("example_posts"):
        parts.append(f"Write in the style of these example posts:\n{d['example_posts']}")
    if not parts:
        return ""
    return "\n\nBrand Context (follow these guidelines strictly):\n" + "\n".join(f"- {p}" for p in parts)
