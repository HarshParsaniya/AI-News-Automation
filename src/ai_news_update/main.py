"""Command-line entry point for the daily AI news digest."""

from __future__ import annotations

import logging
import os

from src.ai_news_update.config import Settings
from src.ai_news_update.logging_config import configure_logging
from src.ai_news_update.workflow import run_news_workflow


def _langfuse_callback(settings: Settings) -> object | None:
    """Create the Langfuse LangChain callback when credentials are configured."""
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        if settings.langfuse_public_key or settings.langfuse_secret_key:
            logging.getLogger(__name__).warning(
                "Langfuse tracing is disabled because both credentials are required"
            )
        else:
            logging.getLogger(__name__).info("Langfuse tracing is disabled")
        return None

    try:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
        os.environ["LANGFUSE_BASE_URL"] = settings.langfuse_base_url

        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_base_url,
        )
        return CallbackHandler(public_key=settings.langfuse_public_key)
    except (ImportError, RuntimeError, ValueError):
        logging.getLogger(__name__).exception("Could not initialize Langfuse tracing")
        raise


def main() -> int:
    """Configure services, run the workflow, and flush telemetry."""
    settings: Settings | None = None
    try:
        configure_logging()
        settings = Settings.from_env()
        configure_logging(settings.log_level)
        callback = _langfuse_callback(settings)
        result = run_news_workflow(settings, callbacks=[callback] if callback else None)
        logging.getLogger(__name__).info("Workflow completed with status: %s", result["status"])
        return 0
    except Exception:
        logging.getLogger(__name__).exception("AI news update execution failed")
        return 1
    finally:
        if settings and settings.langfuse_public_key and settings.langfuse_secret_key:
            try:
                from langfuse import get_client

                get_client().flush()
            except Exception:
                logging.getLogger(__name__).exception("Could not flush Langfuse telemetry")


if __name__ == "__main__":
    raise SystemExit(main())
