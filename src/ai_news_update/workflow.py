"""LangGraph workflow coordinating the three news tools."""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from src.ai_news_update.config import Settings
from src.ai_news_update.email_delivery import send_news_email
from src.ai_news_update.models import NewsArticle, SummarizedArticle
from src.ai_news_update.news_search import search_latest_ai_news
from src.ai_news_update.summarization import summarize_ai_news

logger = logging.getLogger(__name__)


class NewsWorkflowState(TypedDict):
    """In-memory state passed between graph stages."""

    settings: Settings
    articles: list[NewsArticle]
    summaries: list[SummarizedArticle]
    status: str
    error: NotRequired[str]


def build_news_workflow():
    """Build the sequential search, summarize, and email LangGraph workflow."""

    def search_node(state: NewsWorkflowState) -> dict[str, object]:
        logger.info("Starting current-day AI news search")
        articles = search_latest_ai_news(state["settings"])
        return {"articles": articles, "status": "searched"}

    def summarize_node(state: NewsWorkflowState) -> dict[str, object]:
        summaries = summarize_ai_news(state["articles"], state["settings"])
        if not summaries:
            logger.info("No current-day AI news found; skipping email delivery")
            return {"summaries": [], "status": "no_news"}
        return {"summaries": summaries, "status": "summarized"}

    def email_node(state: NewsWorkflowState) -> dict[str, str]:
        send_news_email(state["summaries"], state["settings"])
        return {"status": "sent"}

    def next_after_search(state: NewsWorkflowState) -> str:
        return "summarize"

    def next_after_summarize(state: NewsWorkflowState) -> str:
        return "email" if state["summaries"] else END

    builder = StateGraph(NewsWorkflowState)
    builder.add_node("search", search_node)
    builder.add_node("summarize", summarize_node)
    builder.add_node("email", email_node)
    builder.add_edge(START, "search")
    builder.add_conditional_edges("search", next_after_search, {"summarize": "summarize"})
    builder.add_conditional_edges("summarize", next_after_summarize, {"email": "email", END: END})
    builder.add_edge("email", END)
    return builder.compile()


def run_news_workflow(
    settings: Settings, *, callbacks: list[object] | None = None
) -> NewsWorkflowState:
    """Execute the graph without persisting news data outside the run."""
    initial_state: NewsWorkflowState = {
        "settings": settings,
        "articles": [],
        "summaries": [],
        "status": "started",
    }
    graph = build_news_workflow()
    try:
        result = graph.invoke(
            initial_state,
            config={"callbacks": callbacks or [], "run_name": "ai-news-email-digest"},
        )
    except Exception:
        logger.exception("AI news workflow failed")
        raise
    return result
