from datetime import datetime

THEMES = [
    {
        "type": "use_case",
        "name": "Use Case",
        "video_type": "heygen",
        "post_prompt": (
            "You are a content marketer for an AI automation consultancy called {business_name}. "
            "Create an engaging LinkedIn post about a specific use case for AI automation in {industry}.\n\n"
            "Requirements:\n"
            "- Start with a hook that highlights a common business pain point\n"
            "- Explain how AI automation solves this specific problem\n"
            "- Include 1-2 concrete benefits with metrics if possible\n"
            "- End with a soft call-to-action\n"
            "- Professional but conversational tone, 150-200 words\n"
            "- Include 3-5 relevant hashtags at the end\n"
            "- Do not use emojis. Write naturally and professionally."
        ),
        "script_prompt": (
            "Convert the following social media post into a 30-45 second spoken video script "
            "for an energetic AI avatar. Use a high-energy, enthusiastic, and dynamic delivery. "
            "Short punchy sentences. Varied pacing — start fast, slow down for key points. "
            "Conversational and direct, as if talking to a friend. "
            "Remove all hashtags and website links. Start immediately with impact.\n\nPost:\n{post}"
        ),
        "veo_prompt": None,
    },
    {
        "type": "tips",
        "name": "Tips & Best Practices",
        "video_type": "veo3",
        "post_prompt": (
            "You are a content marketer for an AI automation consultancy called {business_name}. "
            "Create a helpful tip post about AI automation.\n\n"
            "Requirements:\n"
            "- Share one actionable tip for improving business processes with AI\n"
            "- Make it practical and immediately applicable with a brief scenario\n"
            "- Professional, helpful tone, 100-150 words\n"
            "- Call-to-action: Offer more tips or consultation\n"
            "- Include 3-5 relevant hashtags\n"
            "- Do not use emojis. Write naturally and professionally."
        ),
        "script_prompt": None,
        "veo_prompt": (
            "A professional business animation showing a workflow being automated: "
            "documents flying into a computer, gears turning, and a dashboard showing efficiency metrics. "
            "Clean, modern corporate aesthetic. No text overlay. 8 seconds."
        ),
    },
    {
        "type": "success_story",
        "name": "Success Story",
        "video_type": "heygen",
        "post_prompt": (
            "You are a content marketer for an AI automation consultancy called {business_name}. "
            "Create a success story post (anonymized/hypothetical).\n\n"
            "Requirements:\n"
            "- Start with the client's challenge\n"
            "- Explain the AI automation solution implemented\n"
            "- Share specific results (time saved, cost reduced, efficiency gained)\n"
            "- Keep client details general/anonymized\n"
            "- Inspiring but credible tone, 150-200 words\n"
            "- CTA: 'Ready for similar results?'\n"
            "- Include 3-5 hashtags\n"
            "- Do not use emojis. Write naturally and professionally."
        ),
        "script_prompt": (
            "Convert the following social media post into a 30-45 second spoken video script "
            "for an energetic AI avatar delivering a client success story. "
            "Enthusiastic and inspiring — like sharing exciting news with a colleague. "
            "Build momentum toward the result. Use emphasis on the key win. "
            "Remove all hashtags and website links.\n\nPost:\n{post}"
        ),
        "veo_prompt": None,
    },
    {
        "type": "trends",
        "name": "AI Trends",
        "video_type": "veo3",
        "post_prompt": (
            "You are a content marketer for an AI automation consultancy called {business_name}. "
            "Create a post about a current trend in AI or automation.\n\n"
            "Requirements:\n"
            "- Highlight an interesting development in AI/automation\n"
            "- Explain why it matters for businesses\n"
            "- Connect to practical business applications\n"
            "- Thought leadership tone, 150-200 words\n"
            "- CTA: Stay ahead of the curve\n"
            "- Include 3-5 hashtags\n"
            "- Do not use emojis. Write naturally and professionally."
        ),
        "script_prompt": None,
        "veo_prompt": (
            "Futuristic digital visualization: glowing neural network nodes connecting across a dark background, "
            "data streams flowing between AI chips, abstract representation of machine learning. "
            "Cinematic, high-tech aesthetic. No text. 8 seconds."
        ),
    },
    {
        "type": "problem_solution",
        "name": "Problem/Solution",
        "video_type": "veo3",
        "post_prompt": (
            "You are a content marketer for an AI automation consultancy called {business_name}. "
            "Create a before/after style post.\n\n"
            "Requirements:\n"
            "- Describe a common manual process (before)\n"
            "- Show how AI automation transforms it (after)\n"
            "- Use specific, relatable examples\n"
            "- Emphasize time/cost savings\n"
            "- Conversational tone, 150-200 words\n"
            "- CTA: 'Let us automate your process'\n"
            "- Include 3-5 hashtags\n"
            "- Do not use emojis. Write naturally and professionally."
        ),
        "script_prompt": None,
        "veo_prompt": (
            "Split-screen video: left side shows a stressed office worker manually processing stacks of paperwork, "
            "right side shows the same task completed instantly by an AI dashboard. "
            "Clean office environment, professional lighting. No text overlay. 8 seconds."
        ),
    },
    {
        "type": "educational",
        "name": "Educational",
        "video_type": "heygen",
        "post_prompt": (
            "You are a content marketer for an AI automation consultancy called {business_name}. "
            "Create an educational post explaining an AI/automation concept.\n\n"
            "Requirements:\n"
            "- Explain one AI or automation concept in simple terms\n"
            "- Use analogies or examples for clarity\n"
            "- Show how businesses can apply it\n"
            "- Helpful, teacher-like tone, 150-200 words\n"
            "- CTA: Learn more or ask questions\n"
            "- Include 3-5 hashtags\n"
            "- Do not use emojis. Write naturally and professionally."
        ),
        "script_prompt": (
            "Convert the following social media post into a 30-45 second educational video script "
            "for an energetic AI avatar explaining a concept. "
            "Excited about the topic — like sharing something that genuinely blows your mind. "
            "Keep it simple, punchy, and easy to follow. High energy from the first word. "
            "Remove all hashtags and website links.\n\nPost:\n{post}"
        ),
        "veo_prompt": None,
    },
    {
        "type": "service_highlight",
        "name": "Service Highlight",
        "video_type": "heygen",
        "post_prompt": (
            "You are a content marketer for an AI automation consultancy called {business_name}. "
            "Create a post highlighting your services.\n\n"
            "Requirements:\n"
            "- Focus on one service or capability\n"
            "- Emphasize the value and outcomes\n"
            "- Include what makes your approach unique\n"
            "- Avoid being too sales-y\n"
            "- Professional, confident tone, 150-200 words\n"
            "- CTA: Book a consultation or learn more\n"
            "- Include 3-5 hashtags\n"
            "- Do not use emojis. Write naturally and professionally."
        ),
        "script_prompt": (
            "Convert the following social media post into a 30-45 second service pitch video script "
            "for an energetic AI avatar. Bold and confident — like someone who truly believes in what they do. "
            "High energy opening, punchy sentences, strong close. "
            "Remove all hashtags and website links.\n\nPost:\n{post}"
        ),
        "veo_prompt": None,
    },
]

INDUSTRIES = [
    "Finance",
    "Healthcare",
    "E-commerce",
    "Manufacturing",
    "Professional Services",
]


def get_theme_for_today(force_theme: str | None = None) -> tuple[dict, str]:
    today = datetime.now()
    day_of_year = today.timetuple().tm_yday
    if force_theme:
        theme = next((t for t in THEMES if t["type"] == force_theme), None)
        if not theme:
            valid = [t["type"] for t in THEMES]
            raise ValueError(f"Unknown theme '{force_theme}'. Valid: {valid}")
    else:
        theme = THEMES[day_of_year % len(THEMES)]
    industry = INDUSTRIES[day_of_year % len(INDUSTRIES)]
    return theme, industry
