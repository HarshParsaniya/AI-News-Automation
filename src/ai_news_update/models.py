"""In-memory data models shared by workflow stages."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NewsArticle:
    """A news article with its original metadata and available text."""

    title: str
    published_at: str
    source: str
    url: str
    content: str


@dataclass(frozen=True)
class SummarizedArticle:
    """An article summary ready for email delivery."""

    title: str
    published_at: str
    source: str
    url: str
    summary: str
