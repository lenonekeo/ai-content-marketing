"""
Content influence management.

Stores brand guidelines, topics, style examples, audience description,
and inspiration URLs (social media / web pages) that guide the AI when
generating social media content.

URL content is fetched once and cached for 24 hours so generation stays fast.
"""

import hashlib
import json
import logging
import os
import re
import time

import requests

logger = logging.getLogger(__name__)

INFLUENCE_FILE = "influence.json"
CACHE_FILE = "influence_cache.json"
CACHE_TTL = 86400  # 24 hours

_FIELDS = {
    "topics": "",
    "target_audience": "",
    "brand_voice": "",
    "style_notes": "",
    "example_posts": "",
    "avoid": "",
    "inspiration_urls": "",
}


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# URL fetching + cache
# ---------------------------------------------------------------------------

def _load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save URL cache: {e}")


def _fetch_url(url: str) -> str:
    """Fetch a public URL and extract readable text (max 800 chars)."""
    try:
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove noise elements
        for tag in soup(["script", "style", "nav", "footer", "header",
                         "noscript", "iframe", "aside"]):
            tag.decompose()

        # Extract meta description as priority signal
        meta_desc = ""
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            meta_desc = meta["content"].strip()

        # Extract og:title and og:description (social graph tags)
        og_title = ""
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            og_title = og["content"].strip()

        # Get page body text
        body_text = soup.get_text(separator=" ", strip=True)
        body_text = re.sub(r"\s+", " ", body_text).strip()

        # Build summary: og_title + meta_desc + first chunk of body
        parts = []
        if og_title:
            parts.append(f"Page: {og_title}")
        if meta_desc:
            parts.append(f"Description: {meta_desc}")
        if body_text:
            # Take enough body text to give good context
            remaining = 800 - sum(len(p) for p in parts)
            if remaining > 100:
                parts.append(body_text[:remaining])

        result = " | ".join(parts) if parts else ""
        if len(result) < 30:
            return ""
        return result

    except Exception as e:
        logger.warning(f"Could not fetch {url}: {e}")
        return ""


def fetch_inspiration_content(urls: list[str]) -> str:
    """
    Fetch content from inspiration URLs (max 5), using 24h cache.
    Returns a formatted string ready for prompt injection.
    """
    cache = _load_cache()
    now = time.time()
    results = []
    cache_updated = False

    for url in urls[:5]:
        url = url.strip()
        if not url or not url.startswith("http"):
            continue

        cache_key = hashlib.md5(url.encode()).hexdigest()
        entry = cache.get(cache_key, {})

        if entry and (now - entry.get("timestamp", 0)) < CACHE_TTL:
            content = entry.get("content", "")
            logger.debug(f"Inspiration cache hit: {url}")
        else:
            logger.info(f"Fetching inspiration URL: {url}")
            content = _fetch_url(url)
            cache[cache_key] = {"url": url, "content": content, "timestamp": now}
            cache_updated = True

        if content:
            domain = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
            results.append(f"  [{domain}] {content}")

    if cache_updated:
        _save_cache(cache)

    return "\n".join(results)


# ---------------------------------------------------------------------------
# Prompt context
# ---------------------------------------------------------------------------

def get_prompt_context() -> str:
    """Return additional brand context string to inject into AI post prompts."""
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

    # Inspiration URLs
    urls = [u.strip() for u in d.get("inspiration_urls", "").splitlines() if u.strip()]
    if urls:
        inspiration = fetch_inspiration_content(urls)
        if inspiration:
            parts.append(
                "Content from inspiration sources — use these as reference for "
                "relevant topics, trends, and content ideas (do NOT copy directly):\n"
                + inspiration
            )

    if not parts:
        return ""

    return "\n\nBrand Context (follow these guidelines strictly):\n" + "\n".join(
        f"- {p}" for p in parts
    )
