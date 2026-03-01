import re

LINKEDIN_HASHTAGS = [
    "#AIAutomation", "#BusinessAutomation", "#ProcessOptimization",
    "#AI", "#Productivity", "#DigitalTransformation", "#Automation",
]

FACEBOOK_HASHTAGS = [
    "#AIAutomation", "#SmallBusiness", "#Productivity",
    "#BusinessGrowth", "#AI", "#Automation",
]


def _extract_hashtags(text: str) -> list[str]:
    return re.findall(r"#\w+", text)


def _strip_hashtags(text: str) -> str:
    return re.sub(r"\s*#\w+", "", text).strip()


def format_linkedin(text: str, website: str) -> str:
    tags = _extract_hashtags(text)
    if len(tags) >= 3:
        body = _strip_hashtags(text)
    else:
        body = text
        tags = LINKEDIN_HASHTAGS[:5]
    return f"{body}\n\n{' '.join(tags[:5])}\n\n{website}"


def format_facebook(text: str, website: str) -> str:
    tags = _extract_hashtags(text)
    if len(tags) >= 3:
        body = _strip_hashtags(text)
    else:
        body = text
    return f"{body}\n\n{' '.join(FACEBOOK_HASHTAGS[:5])}\n\nLearn more: {website}"
