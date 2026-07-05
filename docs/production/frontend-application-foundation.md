# Frontend Application Foundation

This document tracks the first frontend production-readiness slice for Vyu.

## Scope

The repository now reserves `apps/web` for a Next.js App Router frontend while keeping the Python backend and framework-neutral route runtimes under `src/vyu`.

The first slice implements:

- A Next.js, React, TypeScript, and Tailwind workspace scaffold.
- Reusable app shell primitives for sidebar, topbar, page headers, cards, badges, buttons, and inputs.
- Role-aware navigation with review/admin visibility kept behind permission helpers.
- A dashboard route at `/dashboard` backed by a typed `DashboardSummary` boundary and fixture data.
- Route placeholders for the remaining product surfaces from the frontend brief:
  - `/search/new`
  - `/search/[searchId]/results`
  - `/search/[searchId]/sources`
  - `/search/[searchId]/governance`
  - `/reports/generate`
  - `/evidence-library`
  - `/reviews`
- Strict environment parsing for public frontend configuration.
- A central API client for future JSON REST integration.

## Current Backend Compatibility

The frontend is intentionally API-ready but not yet wired to deployed backend endpoints. The dashboard API module uses fixture data by default and switches to `GET /v1/dashboard/summary` when `NEXT_PUBLIC_USE_FIXTURES=false`.

The current backend repository already has framework-neutral route runtimes for health, review queue, and report export. The endpoints listed in the frontend brief still need concrete backend route support before mock data can be removed from production paths.

## Local Commands

After installing frontend dependencies inside `apps/web`, use:

```bash
npm run dev
npm run build
npm run test
npm run test:e2e
```

The Python repository-level scaffold contract is covered by:

```bash
python -m unittest tests.test_frontend_app_scaffold
```

## Production Limits

- Fixture data remains the default for local UI development.
- Cognito/OIDC authentication is not implemented yet.
- File uploads and report downloads are not implemented yet.
- No large files are uploaded through the Next.js server.
- The frontend does not call PubMed, model providers, or source APIs directly.
- Backend permission enforcement is still required for every protected workflow.

## Next Frontend Slice

The next implementation slice should build the `/search/new` form with React Hook Form and Zod, then add a typed `POST /v1/research/searches` API boundary with loading, error, empty, and permission-denied states.
