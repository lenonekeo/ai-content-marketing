import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise EnvironmentError(f"Missing required environment variable: {key}")
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


class Config:
    # OpenAI
    openai_api_key: str = _require("OPENAI_API_KEY")
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.8
    openai_max_tokens: int = 500

    # HeyGen
    heygen_api_key: str = _optional("HEYGEN_API_KEY")
    heygen_avatar_id: str = _optional("HEYGEN_AVATAR_ID")
    heygen_voice_id: str = _optional("HEYGEN_VOICE_ID")
    heygen_enabled: bool = bool(_optional("HEYGEN_API_KEY"))

    # Google VEO 3 + Gemini Imagen 3 (same API key)
    google_api_key: str = _optional("GOOGLE_API_KEY")
    google_project_id: str = _optional("GOOGLE_PROJECT_ID")
    veo3_enabled: bool = bool(_optional("GOOGLE_API_KEY"))
    imagen_enabled: bool = bool(_optional("GOOGLE_API_KEY"))

    # LinkedIn
    linkedin_access_token: str = _optional("LINKEDIN_ACCESS_TOKEN")
    linkedin_person_urn: str = _optional("LINKEDIN_PERSON_URN")
    linkedin_org_urn: str = _optional("LINKEDIN_ORG_URN")
    linkedin_enabled: bool = bool(_optional("LINKEDIN_ACCESS_TOKEN"))

    @property
    def linkedin_author_urn(self) -> str:
        return self.linkedin_org_urn or self.linkedin_person_urn

    # Facebook
    facebook_access_token: str = _optional("FACEBOOK_ACCESS_TOKEN")
    facebook_page_id: str = _optional("FACEBOOK_PAGE_ID")
    facebook_enabled: bool = bool(_optional("FACEBOOK_ACCESS_TOKEN"))

    # Business Info
    business_name: str = _optional("BUSINESS_NAME", "AI Automation Company")
    business_website: str = _optional("BUSINESS_WEBSITE", "https://yourwebsite.com")
    contact_email: str = _optional("CONTACT_EMAIL", "")

    # SMTP
    smtp_host: str = _optional("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(_optional("SMTP_PORT", "587"))
    smtp_user: str = _optional("SMTP_USER")
    smtp_password: str = _optional("SMTP_PASSWORD")
    smtp_enabled: bool = bool(_optional("SMTP_USER") and _optional("SMTP_PASSWORD"))

    # Schedule
    post_hour: int = int(_optional("POST_HOUR", "9"))
    post_days: str = _optional("POST_DAYS", "mon,wed,fri")

    # Paths
    downloads_dir: str = "downloads"
    logs_file: str = "logs/posts.jsonl"


config = Config()
