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
