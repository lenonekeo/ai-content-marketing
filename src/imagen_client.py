"""
Google Gemini Image Generation (Imagen 3)
Generates branded visuals to accompany social media posts.
"""

import base64
import logging
import os
from datetime import datetime
from google import genai
from google.genai import types
from config import config

logger = logging.getLogger(__name__)


def _get_client() -> genai.Client:
    return genai.Client(api_key=config.google_api_key)


def generate_image(prompt: str, filename: str | None = None) -> str:
    """
    Generate an image using Gemini Imagen 3.
    Returns the local file path of the saved image.
    """
    client = _get_client()

    # Enrich prompt with professional branding context
    full_prompt = (
        f"{prompt} "
        "Professional, modern corporate aesthetic. "
        "Clean design, high quality, suitable for LinkedIn and Facebook business posts. "
        "No text or watermarks in the image."
    )

    logger.info("Generating image with Gemini Imagen 3...")
    response = client.models.generate_images(
        model="imagen-3.0-generate-002",
        prompt=full_prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="16:9",       # Ideal for social media
            safety_filter_level="block_some",
            person_generation="allow_adult",
        ),
    )

    if not response.generated_images:
        raise RuntimeError("Imagen returned no images")

    # Save image to downloads/
    os.makedirs(config.downloads_dir, exist_ok=True)
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"imagen_{ts}.png"
    path = os.path.join(config.downloads_dir, filename)

    image_bytes = response.generated_images[0].image.image_bytes
    with open(path, "wb") as f:
        f.write(image_bytes)

    logger.info(f"Imagen image saved to {path}")
    return path


def build_image_prompt(theme_type: str, post_text: str, industry: str) -> str:
    """Build a context-aware image prompt based on theme and post content."""
    prompts = {
        "use_case": (
            f"A professional business scene showing AI automation in the {industry} industry. "
            "Modern office with digital dashboards, data flowing through screens, "
            "automated workflows visualized as connected nodes. Blue and white color palette."
        ),
        "tips": (
            "An elegant infographic-style image showing a lightbulb connected to gears and circuits, "
            "representing AI automation tips. Minimalist design, blue gradient background, "
            "modern icons for productivity and efficiency."
        ),
        "success_story": (
            "A triumphant business professional at a modern desk, surrounded by upward trending charts "
            "and AI dashboard metrics. Warm golden lighting, success and achievement atmosphere. "
            "Corporate but approachable aesthetic."
        ),
        "trends": (
            "A futuristic visualization of AI technology: neural network nodes glowing in blue and purple, "
            "abstract data streams, holographic interfaces. Dark background with neon accents. "
            "Forward-looking, innovative atmosphere."
        ),
        "problem_solution": (
            "A split composition: left side shows cluttered manual paperwork and stressed workflow, "
            "right side shows a clean, automated digital dashboard with smooth data flow. "
            "Clear contrast between old and new. Blue and white theme."
        ),
        "educational": (
            "A clean educational illustration: a simple diagram explaining AI automation concepts, "
            "connected blocks showing workflow steps, icons for data, AI, and output. "
            "Whiteboard-style design with blue accents. Clear and approachable."
        ),
        "service_highlight": (
            "A professional hero image for an AI automation consultancy: "
            "abstract representation of business growth through automation, "
            "rising graph lines integrated with circuit patterns, "
            "corporate blue gradient, modern and trustworthy feel."
        ),
    }
    return prompts.get(theme_type, prompts["service_highlight"])
