"""Grounded article summarization with a configurable per-run limit."""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from src.ai_news_update.config import Settings
from src.ai_news_update.models import NewsArticle, SummarizedArticle
from src.ai_news_update.news_search import _normalized_url

logger = logging.getLogger(__name__)


def select_articles(articles: list[NewsArticle], limit: int) -> list[NewsArticle]:
    """Deduplicate articles and select the newest articles up to the configured limit."""
    if limit < 1:
        raise ValueError("Article limit must be at least 1")

    selected: list[NewsArticle] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for article in sorted(articles, key=lambda item: item.published_at, reverse=True):
        normalized_url = _normalized_url(article.url)
        normalized_title = re.sub(r"\W+", " ", article.title.casefold()).strip()
        if normalized_url in seen_urls or normalized_title in seen_titles:
            continue
        seen_urls.add(normalized_url)
        seen_titles.add(normalized_title)
        selected.append(article)
        if len(selected) == limit:
            break
    return selected


def summarize_ai_news(
    articles: list[NewsArticle],
    settings: Settings,
    *,
    model: object | None = None,
) -> list[SummarizedArticle]:
    """Summarize no more than MAX_NEWS_COUNT unique articles using Groq."""
    selected = select_articles(articles, settings.max_news_count)
    if not selected:
        logger.info("No articles selected for summarization")
        return []
    settings.validate_for_summarization()

    llm = model or ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0,
    )
    summaries: list[SummarizedArticle] = []
    for article in selected:
        messages = [
            SystemMessage(
                content=(
                    "Summarize the supplied news article accurately in 7-8 non-empty lines, "
                    "preferably 7. Write one concise sentence per line, with no heading or "
                    "bullet points. Cover the main topic, development, relevant details, and "
                    "key takeaway. Use only facts in the provided title and article text. If "
                    "details are unavailable, do not infer them or pad the summary with "
                    "repetition. Do not add external facts or opinions."
                )
            ),
            HumanMessage(
                content=f"Title: {article.title}\nSource: {article.source}\n"
                f"Published: {article.published_at}\nArticle text:\n{article.content[:12_000]}"
            ),
        ]
        try:
            response = llm.invoke(messages)
        except Exception:
            logger.exception("Failed to summarize article: %s", article.title)
            raise

        summary = str(response.content).strip()
        if not summary:
            raise RuntimeError(f"Summarizer returned an empty summary for: {article.title}")
        summaries.append(
            SummarizedArticle(
                title=article.title,
                published_at=article.published_at,
                source=article.source,
                url=article.url,
                summary=summary,
            )
        )

    logger.info("Summarized %d of %d eligible articles", len(summaries), len(articles))
    return summaries
