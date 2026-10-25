"""Environment-based application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Validated runtime settings loaded from environment variables."""

    groq_api_key: str
    groq_model: str
    news_recipient: str
    email_sender: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    max_news_count: int
    news_timezone: str
    log_level: str
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_base_url: str

    @classmethod
    def from_env(cls) -> Settings:
        """Load and validate settings, including local .env values."""
        load_dotenv()

        try:
            max_news_count = int(os.getenv("MAX_NEWS_COUNT", "10"))
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
        except ValueError as error:
            raise ValueError("MAX_NEWS_COUNT and SMTP_PORT must be integers") from error

        if max_news_count < 1:
            raise ValueError("MAX_NEWS_COUNT must be at least 1")
        if not 1 <= smtp_port <= 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535")

        timezone = os.getenv("NEWS_TIMEZONE", "UTC")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown NEWS_TIMEZONE: {timezone}") from error

        tls_value = os.getenv("SMTP_USE_TLS", "true").strip().lower()
        if tls_value not in {"true", "false"}:
            raise ValueError("SMTP_USE_TLS must be true or false")

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be a standard Python logging level")

        return cls(
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            news_recipient=os.getenv("NEWS_RECIPIENT", ""),
            email_sender=os.getenv("EMAIL_SENDER", ""),
            smtp_host=os.getenv("SMTP_HOST", ""),
            smtp_port=smtp_port,
            smtp_username=os.getenv("SMTP_USERNAME", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            smtp_use_tls=tls_value == "true",
            max_news_count=max_news_count,
            news_timezone=timezone,
            log_level=log_level,
            langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            langfuse_base_url=os.getenv(
                "LANGFUSE_BASE_URL", "https://cloud.langfuse.com"
            ),
        )

    def validate_for_summarization(self) -> None:
        """Reject a missing Groq credential only when articles need summarizing."""
        if not self.groq_api_key.strip():
            raise ValueError("Missing required environment variable: GROQ_API_KEY")

    def validate_for_email(self) -> None:
        """Reject missing SMTP credentials only when a digest will be sent."""
        required = {
            "NEWS_RECIPIENT": self.news_recipient,
            "EMAIL_SENDER": self.email_sender,
            "SMTP_HOST": self.smtp_host,
            "SMTP_USERNAME": self.smtp_username,
            "SMTP_PASSWORD": self.smtp_password,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
