"""Application logging configuration."""

import logging
from datetime import datetime
from pathlib import Path


def configure_logging(level: str = "INFO", log_directory: Path = Path("logs")) -> None:
    """Log to the console and append to one date-named file for the current day."""
    log_directory.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s:%(lineno)d - %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    log_date = datetime.now().strftime("%Y-%m-%d")
    file_handler = logging.FileHandler(
        log_directory / f"ai_news_update_{log_date}.log",
        mode="a",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
