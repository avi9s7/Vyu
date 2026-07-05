## Summary

- Add FastAPI application shell with stable error envelope, health/readiness/version, and OpenAPI export (`docs/api/openapi.json`).
- Bind OIDC/HS256 bearer auth to PostgreSQL membership; add authenticated research search API with idempotency.
- Introduce Alembic `0003` job/research/outbox schema, idempotent job repository, transactional outbox publisher, and SQS worker runtime.
- Containerize API and worker (non-root Python 3.13 slim) and extend compose with LocalStack + worker.

## Test plan

- [ ] CI backend job green (unit + PostgreSQL integration for db, jobs, api)
- [ ] CI platform job builds API and worker images
- [ ] `uv run python scripts/verify.py --scope backend` passes locally
- [ ] OpenAPI artifact matches `/v1/research/searches` routes
- [ ] Cross-tenant auth returns 404; duplicate idempotency key returns same IDs
