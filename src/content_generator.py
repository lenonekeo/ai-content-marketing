import logging
from openai import OpenAI
from config import config
from src.influence import get_prompt_context

logger = logging.getLogger(__name__)
_client = OpenAI(api_key=config.openai_api_key)


def generate_post(prompt: str) -> str:
    influence = get_prompt_context()
    full_prompt = prompt + influence
    logger.info("Generating post content with OpenAI...")
    response = _client.chat.completions.create(
        model=config.openai_model,
        messages=[{"role": "user", "content": full_prompt}],
        temperature=config.openai_temperature,
        max_tokens=config.openai_max_tokens,
    )
    text = response.choices[0].message.content.strip()
    logger.info(f"Generated {len(text)} characters of content")
    return text


def post_to_spoken_script(post_text: str) -> str:
    """Convert a social media post into a natural spoken script for an AI avatar.
    Removes hashtags, bullets, titles, URLs. Returns clean 20-35s spoken text."""
    prompt = (
        "Convert the following social media post into a SHORT spoken script for an AI avatar video.\n"
        "Pick ONE key message or benefit only - do NOT cover all bullet points.\n"
        "Rules:\n"
        "- Write ONLY spoken words - no labels, formatting, or stage directions\n"
        "- Remove all hashtags, URLs, emojis, bullet points, headers\n"
        "- Use 2-3 flowing, natural sentences - confident and direct\n"
        "- MAXIMUM 50 words total - stop with a complete sentence\n"
        "- Do NOT greet - start directly with the value\n\n"
        f"Post:\n{post_text}\n\nSpoken script (50 words max):"
    )
    logger.info("Converting post to spoken script with OpenAI...")
    response = _client.chat.completions.create(
        model=config.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=120,
    )
    script = response.choices[0].message.content.strip()
    for punct in [". ", "! ", "? "]:
        last = script.rfind(punct)
        if last > len(script) // 2:
            script = script[:last + 1].strip()
            break
    logger.info(f"Generated {len(script)} character spoken script")
    return script


def post_to_veo3_prompt(post_text: str) -> str:
    """Convert a social media post into a cinematic VEO3 prompt for an 8-second video.
    Extracts the single core idea and describes one powerful visual scene."""
    prompt = (
        "You are writing a prompt for an AI video generator (VEO 3). The video is exactly 8 seconds long.\n"
        "Read the social media post below and identify the ONE core idea or benefit.\n"
        "Then write a single cinematic scene that visually represents that idea in 8 seconds.\n\n"
        "Rules:\n"
        "- Describe ONLY what to SHOW — camera movement, setting, atmosphere, action\n"
        "- Professional business / technology aesthetic\n"
        "- No text overlays, no logos, no people holding signs\n"
        "- 2 sentences max — vivid, specific, present tense\n"
        "- Example: 'A marketing team gathered around a glowing dashboard, data visualizations animating in real time. Smooth cinematic push-in, warm office lighting, confident energy.'\n\n"
        f"Post:\n{post_text}\n\nVEO3 video prompt (2 sentences, 8-second scene):"
    )
    response = _client.chat.completions.create(
        model=config.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=80,
    )
    return response.choices[0].message.content.strip()


def extract_remotion_props(post_text: str, composition: str) -> dict:
    """
    Use AI to extract structured props from chat content for a Remotion composition.
    Returns a dict ready to pass as --props to the Remotion renderer.
    """
    import json

    prompts = {
        "PostCard": (
            "Extract a social media post card from this content.\n"
            "Return JSON with exactly these keys:\n"
            '- "text": the main post text (max 200 chars, punchy and engaging)\n'
            '- "hashtags": 3-5 relevant hashtags as a string like "#AI #Marketing"\n'
            "Rules: JSON only, no explanation.\n\n"
            f"Content:\n{post_text}"
        ),
        "Intro": (
            "Extract a branded video intro from this content.\n"
            "Return JSON with exactly these keys:\n"
            '- "tagline": one powerful tagline (max 6 words, e.g. "AI That Works For You")\n'
            "Rules: JSON only, no explanation.\n\n"
            f"Content:\n{post_text}"
        ),
        "Outro": (
            "Extract a video outro call-to-action from this content.\n"
            "Return JSON with exactly these keys:\n"
            '- "ctaText": one clear call to action (max 8 words, e.g. "Book Your Free Strategy Call")\n'
            "Rules: JSON only, no explanation.\n\n"
            f"Content:\n{post_text}"
        ),
        "ProductLaunch": (
            "Extract a product launch video script from this content.\n"
            "Return JSON with exactly these keys:\n"
            '- "hookLine1": a provocative question or problem statement (max 10 words)\n'
            '- "hookLine2": the empowering answer (max 8 words, e.g. "There\'s a smarter way.")\n'
            '- "productName": the product or brand name (max 3 words)\n'
            '- "tagline": one-line product description (max 8 words)\n'
            '- "features": array of exactly 3 objects, each with "icon" (single emoji), "title" (max 5 words), "desc" (max 20 words)\n'
            '- "stats": array of exactly 3 objects, each with "value" (short like "10x" or "24/7") and "label" (max 3 words)\n'
            '- "ctaText": call to action button text (max 6 words)\n'
            '- "subText": supporting line above CTA (max 8 words)\n'
            "Rules: JSON only, no explanation, all fields required.\n\n"
            f"Content:\n{post_text}"
        ),
    }

    prompt = prompts.get(composition)
    if not prompt:
        return {}

    logger.info(f"Extracting Remotion props for {composition} from chat content...")
    try:
        response = _client.chat.completions.create(
            model=config.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        props = json.loads(raw)
        logger.info(f"Extracted props for {composition}: {list(props.keys())}")
        return props
    except Exception as e:
        logger.warning(f"Props extraction failed for {composition}: {e} — using defaults")
        return {}


def generate_script(post_text: str, script_prompt_template: str) -> str:
    prompt = script_prompt_template.format(post=post_text)
    logger.info("Generating video script with OpenAI...")
    response = _client.chat.completions.create(
        model=config.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=300,
    )
    script = response.choices[0].message.content.strip()
    logger.info(f"Generated {len(script)} character video script")
    return script
