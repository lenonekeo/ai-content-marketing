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
    Removes hashtags, bullets, titles, URLs. Returns clean 30-60s spoken text."""
    prompt = (
        "Convert the following social media post into a natural, conversational spoken script "
        "for an AI avatar video. Rules:\n"
        "- Write ONLY what should be spoken out loud — no stage directions, no labels\n"
        "- Remove all hashtags, bullet points, numbered lists, titles, headers\n"
        "- Remove all URLs and website links\n"
        "- Remove emojis (or replace with the word they represent if needed for flow)\n"
        "- Keep the core message and key points, but rewrite as natural flowing speech\n"
        "- Use short sentences and a conversational tone\n"
        "- Target length: 30 to 60 seconds when spoken (about 75-150 words)\n"
        "- Do NOT add an intro like 'Hi I'm...' — start directly with the message\n\n"
        f"Post:\n{post_text}\n\nSpoken script:"
    )
    logger.info("Converting post to spoken script with OpenAI...")
    response = _client.chat.completions.create(
        model=config.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=300,
    )
    script = response.choices[0].message.content.strip()
    logger.info(f"Generated {len(script)} character spoken script")
    return script


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
