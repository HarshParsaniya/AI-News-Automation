"""HTML email rendering and SMTP delivery."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from html import escape

from src.ai_news_update.config import Settings
from src.ai_news_update.models import SummarizedArticle

logger = logging.getLogger(__name__)


def render_news_email(articles: list[SummarizedArticle]) -> str:
    """Render summarized articles in a readable HTML digest."""
    if not articles:
        raise ValueError("Refusing to render an empty news digest")

    cards = []
    for article in articles:
        safe_url = escape(article.url, quote=True)
        cards.append(
            "<article style='padding:16px 0;border-bottom:1px solid #ddd'>"
            f"<h2 style='font-size:18px'><a href='{safe_url}'>{escape(article.title)}</a></h2>"
            f"<p>{escape(article.summary)}</p>"
            f"<p style='color:#555;font-size:13px'>Published: {escape(article.published_at)}"
            f" | Source: {escape(article.source)}</p>"
            f"<p><a href='{safe_url}'>Read original article</a></p>"
            "</article>"
        )
    return (
        "<!doctype html><html><body style='font-family:Arial,sans-serif;color:#222'>"
        "<main style='max-width:720px;margin:auto'>"
        "<h1>Today's AI News</h1>"
        + "".join(cards)
        + "</main></body></html>"
    )


def send_news_email(articles: list[SummarizedArticle], settings: Settings) -> None:
    """Send the non-empty digest over authenticated SMTP with explicit failures."""
    if not articles:
        raise ValueError("Refusing to send an empty news digest")
    settings.validate_for_email()

    message = EmailMessage()
    message["Subject"] = "Today's AI News Update"
    message["From"] = settings.email_sender
    message["To"] = settings.news_recipient
    message.set_content(
        "\n\n".join(
            f"{article.title}\n{article.summary}\nPublished: {article.published_at}"
            f"\nSource: {article.source}\n{article.url}"
            for article in articles
        )
    )
    message.add_alternative(render_news_email(articles), subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            if settings.smtp_use_tls:
                server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            refused_recipients = server.send_message(message)
            if refused_recipients:
                raise smtplib.SMTPRecipientsRefused(refused_recipients)
    except (OSError, smtplib.SMTPException):
        logger.exception("Email delivery failed for %d articles", len(articles))
        raise

    logger.info("Email digest delivered with %d articles", len(articles))
