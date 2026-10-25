FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p logs \
    && chown -R appuser:appuser /app

USER 10001:10001
CMD ["python", "-m", "src.ai_news_update.main"]
