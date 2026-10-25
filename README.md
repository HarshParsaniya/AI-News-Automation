# AI Latest News Update Agent

A Python 3.12 application that uses LangGraph to search for current-day AI news, summarize a maximum of ten unique articles with Groq, and deliver a readable HTML digest over SMTP. Articles and summaries exist only in workflow memory; the application has no database.

## Project conventions

The implementation was based on an inspection of [Diamond-Price-Prediction](https://github.com/HarshParsaniya/Diamond-Price-Prediction). The reference project uses a modular `src/` package, a dedicated logging module and directory, root-level deployment files, and a README for setup and execution. This project follows those applicable conventions while using `pyproject.toml` and `uv` for dependency management.

## Workflow

1. Search Google News RSS for articles published today in `NEWS_TIMEZONE`.
2. Discard undated, outdated, duplicate, and non-AI results; retrieve article paragraphs when available.
3. At the summarization stage, deduplicate again, sort newest first, and select at most `MAX_NEWS_COUNT` articles (default `10`).
4. Summarize each selected article using the configured Groq model, grounding the summary in the article title and available text.
5. Send the summaries as a multipart plain-text/HTML email. If search returns no eligible articles, finish with `no_news` and do not send an email.

Search/feed failures, summarization failures, and email failures are logged and fail the run rather than being silently treated as success. Individual article-page fetch failures are logged; the RSS description is used as fallback content when available.

## Local setup

Prerequisites: Python 3.12+, `uv`, and an SMTP account that can send mail.

```powershell
uv sync
Copy-Item .env.example .env
```

Set at least `GROQ_API_KEY`, `NEWS_RECIPIENT`, `EMAIL_SENDER`, `SMTP_HOST`, `SMTP_USERNAME`, and `SMTP_PASSWORD` in `.env`. Never commit `.env`. The optional Langfuse keys enable tracing; if they are absent, the application logs that tracing is disabled.

Run a digest:

```powershell
uv run python -m src.ai_news_update.main
```

Useful configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | — | Groq API credential |
| `GROQ_MODEL` | `qwen/qwen3.8-27b` | Groq-compatible summarization model; can be changed in `.env` |
| `MAX_NEWS_COUNT` | `10` | Positive integer maximum articles summarized and emailed |
| `NEWS_TIMEZONE` | `UTC` | IANA timezone used to define the publication date |
| `NEWS_RECIPIENT`, `EMAIL_SENDER` | — | Digest recipient and sender |
| `SMTP_HOST`, `SMTP_PORT` | —, `587` | SMTP host and port |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | — | SMTP authentication credentials |
| `SMTP_USE_TLS` | `true` | Whether to negotiate STARTTLS |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | unset | Optional Langfuse credentials |
| `LANGFUSE_BASE_URL` | `https://cloud.langfuse.com` | Langfuse endpoint |

Logs are written to `logs/ai_news_update_YYYY-MM-DD.log` (for example, `logs/ai_news_update_2026-10-25.log`) and appended to that day's file across runs. Logs are also sent to standard output. Credentials and email passwords are not included in application log messages.

## Lint

```powershell
uv run ruff check .
```

## Docker Compose

Create `.env` as above, then build and execute one digest:

```powershell
docker compose build
docker compose run --rm ai-news-agent
```

`compose.yaml` mounts `logs/` from the host. This is a one-shot process, not a web service, so a continuously running container health check is not applicable. Schedule it with a host scheduler, Kubernetes CronJob, or another job scheduler.

## Kubernetes

Build and publish the image, then configure cluster secrets and apply the manifests:

```powershell
docker build -t YOUR_REGISTRY/ai-news-agent:latest .
docker push YOUR_REGISTRY/ai-news-agent:latest
kubectl create secret generic ai-news-agent-secrets `
  --from-literal=GROQ_API_KEY='...' `
  --from-literal=NEWS_RECIPIENT='...' `
  --from-literal=EMAIL_SENDER='...' `
  --from-literal=SMTP_HOST='...' `
  --from-literal=SMTP_USERNAME='...' `
  --from-literal=SMTP_PASSWORD='...'
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/cronjob.yaml
```

Update the image in `k8s/cronjob.yaml` to the image you pushed. The schedule defaults to `07:00` cluster time; adjust it and `NEWS_TIMEZONE` to your preferred delivery time. To enable Langfuse, add `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` to the same Kubernetes Secret. Kubernetes `Secret` values are deliberately not committed in this repository. Logs are available through the container output and an ephemeral pod-local log volume; export them using your cluster's normal log collection.

## Dependencies and lockfile

`pyproject.toml` declares runtime and development dependencies. `uv.lock` pins the full environment. Update dependencies with `uv lock` and install the locked environment with `uv sync --frozen`.
