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
