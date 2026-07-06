FROM node:24-bookworm-slim@sha256:e8e2e91b1378f83c5b2dd15f0247f34110e2fe895f6ca7719dbb780f929368eb AS deps

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:24-bookworm-slim@sha256:e8e2e91b1378f83c5b2dd15f0247f34110e2fe895f6ca7719dbb780f929368eb AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY apps/web ./

ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_APP_ENV=production \
    NEXT_PUBLIC_USE_FIXTURES=false

RUN npm run build

FROM node:24-bookworm-slim@sha256:e8e2e91b1378f83c5b2dd15f0247f34110e2fe895f6ca7719dbb780f929368eb AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 vyu \
    && useradd --uid 10001 --gid vyu --create-home vyu

COPY --from=builder /app/public ./public
COPY --from=builder --chown=vyu:vyu /app/.next/standalone ./
COPY --from=builder --chown=vyu:vyu /app/.next/static ./.next/static
COPY deploy/docker/web-entrypoint.sh /usr/local/bin/web-entrypoint.sh

RUN chmod +x /usr/local/bin/web-entrypoint.sh

USER vyu

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3000/api/health || exit 1

ENTRYPOINT ["/usr/local/bin/web-entrypoint.sh"]
