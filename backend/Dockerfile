# Say It Back API for Cloud Run: FastAPI plus ADK on uvicorn, HTTP and WebSockets on $PORT (default 8080).
# Build context is backend/. Deploy with a request timeout of at least 900 s (live sockets last up to
# 10 minutes); see README.md "Cloud Run". Use deploy/02_deploy_backend.sh: it stages eval_data/ first.
#
# EXTRAS are the optional features installed into the image. The defaults cover SIB_TRACE_TO_CLOUD and
# SIB_BQ_DATASET so one image serves every environment; use --build-arg EXTRAS="" for a smaller one.

FROM python:3.13-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.9.8 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
ARG EXTRAS="--extra trace --extra bigquery"
WORKDIR /app
# Dependencies first, so this layer is cached until pyproject.toml or uv.lock change.
# No BuildKit-only syntax: Cloud Build's docker builder may not enable it.
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project ${EXTRAS}
COPY sayitback ./sayitback
RUN uv sync --frozen --no-dev ${EXTRAS}
# Endpoints 16-19 read the evaluation test set and its latest report from SIB_EVAL_DIR. eval/ is outside
# this build context, so deploy/02_deploy_backend.sh copies eval/testset and eval/reports/latest.json
# into eval_data/ first. Built any other way the folder holds only a placeholder, and those endpoints
# answer 404 (no_testset, no_report).
COPY eval_data ./eval

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    SIB_EVAL_DIR=/app/eval \
    PORT=8080
RUN useradd --system --uid 10001 --home-dir /app app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
USER app
EXPOSE 8080
# Shell form so $PORT expands. Cloud Run injects PORT; WebSockets need no extra flag there.
# --ws-max-size caps a WebSocket message at 64 KB (the relay needs at most 8 KB per frame).
CMD ["sh", "-c", "exec uvicorn sayitback.main:app --host 0.0.0.0 --port ${PORT:-8080} --ws websockets --ws-max-size 65536"]
