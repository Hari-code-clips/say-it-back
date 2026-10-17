# The permit-to-work stub for Cloud Run (deploy/04_deploy_ptw_stub.sh): FastAPI on uvicorn, on $PORT.
FROM python:3.13-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.9.8 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY ptw_stub ./ptw_stub

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    PORT=8080
RUN useradd --system --uid 10001 --home-dir /app app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
USER app
EXPOSE 8080
# Shell form so $PORT expands. Cloud Run injects PORT.
CMD ["sh", "-c", "exec uvicorn ptw_stub.app:app --host 0.0.0.0 --port ${PORT:-8080} --no-server-header"]
