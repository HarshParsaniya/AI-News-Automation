"""Search and clean current-day AI news from Google News RSS."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

from src.ai_news_update.config import Settings
from src.ai_news_update.models import NewsArticle

logger = logging.getLogger(__name__)
AI_TERMS = re.compile(
    r"\b(ai|artificial intelligence|machine learning|deep learning|"
    r"generative ai|large language model|llm|chatgpt|openai|anthropic|"
    r"google gemini|claude|copilot|neural network|robotics)\b",
    re.IGNORECASE,
)


class NewsSearchError(RuntimeError):
    """Raised when the news feed cannot be searched."""


def _article_date(entry: object) -> datetime | None:
    """Return an entry's publication timestamp in UTC when available."""
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        return datetime(*parsed[:6], tzinfo=UTC)
    for field in ("published", "updated"):
        value = getattr(entry, field, None)
        if value:
            try:
                result = parsedate_to_datetime(value)
                if result.tzinfo is None:
                    return result.replace(tzinfo=UTC)
                return result.astimezone(UTC)
            except (TypeError, ValueError, OverflowError):
                continue
    return None


def _normalized_url(url: str) -> str:
    """Normalize article URLs for duplicate detection."""
    parts = urlsplit(url)
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query)
            if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
        ]
    )
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, "")
    )


def _fetch_article(
    url: str, session: requests.Session, timeout: float
) -> tuple[str, str]:
    """Fetch article paragraphs and return the final publisher URL after redirects."""
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        final_url = response.url
        if urlsplit(final_url).scheme.lower() not in {"http", "https"}:
            logger.warning("Ignoring non-web article redirect from %s", url)
            return url, ""
        soup = BeautifulSoup(response.content, "html.parser")
        article = soup.find("article") or soup
        paragraphs = [
            paragraph.get_text(" ", strip=True)
            for paragraph in article.find_all("p")
            if paragraph.get_text(" ", strip=True)
        ]
        return final_url, "\n".join(paragraphs)[:20_000]
    except requests.RequestException as error:
        logger.warning("Could not fetch article content from %s: %s", url, error)
        return url, ""


def search_latest_ai_news(
    settings: Settings,
    *,
    now: datetime | None = None,
    session: requests.Session | None = None,
    timeout: float = 15.0,
    article_fetcher: Callable[
        [str, requests.Session, float], tuple[str, str]
    ] = _fetch_article,
) -> list[NewsArticle]:
    """Fetch and deduplicate relevant AI articles published today in configured timezone."""
    timezone = ZoneInfo(settings.news_timezone)
    current_time = now or datetime.now(timezone)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone)
    current_time = current_time.astimezone(timezone)
    today = current_time.date()
    start = datetime.combine(today, time.min, tzinfo=timezone).astimezone(UTC)
    end = (datetime.combine(today, time.min, tzinfo=timezone) + timedelta(days=1)).astimezone(UTC)
    query = f"AI after:{start:%Y-%m-%d} before:{end:%Y-%m-%d}"
    feed_url = "https://news.google.com/rss/search?" + urlencode(
        {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    http = session or requests.Session()
    http.headers.update({"User-Agent": "AINewsUpdate/1.0 (+https://news.google.com)"})

    try:
        response = http.get(feed_url, timeout=timeout)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except requests.RequestException as error:
        logger.exception("AI news RSS search failed")
        raise NewsSearchError("Could not retrieve the AI news feed") from error

    if feed.bozo and not feed.entries:
        logger.error("Google News returned an invalid RSS feed: %s", feed.bozo_exception)
        raise NewsSearchError("Google News returned an invalid RSS feed")

    dated_entries = []
    for entry in feed.entries:
        published = _article_date(entry)
        if published is not None and start <= published < end:
            dated_entries.append((published, entry))

    articles: list[NewsArticle] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for published, entry in sorted(dated_entries, key=lambda item: item[0], reverse=True):
        title = str(getattr(entry, "title", "")).strip()
        description = BeautifulSoup(
            str(getattr(entry, "summary", "")), "html.parser"
        ).get_text(" ", strip=True)
        if not title or not AI_TERMS.search(f"{title} {description}"):
            continue

        link = str(getattr(entry, "link", "")).strip()
        try:
            link_parts = urlsplit(link)
        except ValueError:
            logger.warning("Ignoring malformed article URL for %s", title)
            continue
        if link_parts.scheme.lower() not in {"http", "https"} or not link_parts.netloc:
            continue
        normalized_url = _normalized_url(link)
        normalized_title = re.sub(r"\W+", " ", title.casefold()).strip()
        if normalized_url in seen_urls or normalized_title in seen_titles:
            continue

        source_value = getattr(entry, "source", {})
        source = str(source_value.get("title", "Unknown source")).strip()
        original_url, content = article_fetcher(link, http, timeout)
        try:
            original_parts = urlsplit(original_url)
        except ValueError:
            logger.warning("Ignoring malformed resolved article URL for %s", title)
            continue
        if original_parts.scheme.lower() not in {"http", "https"} or not original_parts.netloc:
            logger.warning("Ignoring non-web resolved article URL for %s", title)
            continue
        resolved_identity = _normalized_url(original_url)
        if resolved_identity != normalized_url and resolved_identity in seen_urls:
            continue

        seen_urls.add(normalized_url)
        seen_urls.add(resolved_identity)
        seen_titles.add(normalized_title)
        content = content or description
        articles.append(
            NewsArticle(
                title=title,
                published_at=published.astimezone(timezone).isoformat(),
                source=source or "Unknown source",
                url=original_url,
                content=content,
            )
        )

    articles.sort(
        key=lambda article: datetime.fromisoformat(article.published_at), reverse=True
    )
    logger.info("Found %d unique AI news articles published on %s", len(articles), today)
    return articles
