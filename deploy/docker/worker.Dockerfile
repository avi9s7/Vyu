FROM python:3.13-slim-bookworm@sha256:654c64537da60f783180c2412a10e01588969b4b907fecd1683c7879b91ea0d

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv==0.9.7 \
    && useradd --create-home --uid 10001 vyu

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY apps/worker ./apps/worker
COPY config ./config

RUN uv sync --frozen --no-dev \
    && chown -R vyu:vyu /app

USER vyu

CMD ["uv", "run", "python", "-m", "apps.worker.main"]
