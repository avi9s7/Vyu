FROM python:3.13-slim-bookworm@sha256:129f9f5d5729767916d79f0021ba4fe56ff113332b08ef1213ecf529a9da7ebb

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.9.7 \
    && useradd --create-home --uid 10001 vyu

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY apps/api ./apps/api
COPY config ./config
COPY alembic.ini ./
COPY src/vyu/migrations ./src/vyu/migrations

RUN uv sync --frozen --no-dev \
    && chown -R vyu:vyu /app

USER vyu

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/v1/health/live || exit 1

CMD ["uv", "run", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
