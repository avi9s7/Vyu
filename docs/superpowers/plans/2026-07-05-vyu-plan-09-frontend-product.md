# VYU Frontend Product Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixture-backed Next.js shell and placeholder pages with secure, accessible, tested production workflows for login, search, evidence, governance, review, upload, library, reports, and administration.

**Architecture:** Next.js 16 uses server-side session/BFF handlers for Cognito authorization-code plus PKCE. API types come from generated OpenAPI, not handwritten guesses. Server Components load initial read data; small Client Components own forms and interactive state. TanStack Query handles bounded client refresh for job progress.

**Tech Stack:** Next.js 16, React 19, TypeScript strict mode, Cognito OIDC/PKCE, generated OpenAPI client, TanStack Query, React Hook Form, Zod, Vitest, Testing Library, Playwright, axe accessibility checks.

---

## Entry Gate

- Plans 1-8 provide stable staging APIs and generated OpenAPI.
- Cognito staging client/callback/logout configuration works.
- UX screenshots are reference only; accessible behavior and API truth take priority.

## Task 1: Upgrade Next.js 14 to Next.js 16 Safely

**Files:** `apps/web/package.json`, lock, Next config, React components/tests

- [ ] Create a pre-upgrade Playwright smoke suite for all existing routes, dashboard fixture content, sidebar navigation, and build output.

- [ ] Upgrade 14 -> 15 with official codemod, fix async route params/cookies/headers and React 19 changes, then run typecheck/lint/test/build/smoke.

- [ ] Commit the 15 migration separately.

- [ ] Upgrade 15 -> 16 with official codemod, replace removed `next lint` command with direct ESLint flat configuration when required, then run the same suite.

- [ ] Commit the 16 migration separately. Do not combine redesign or API integration with framework migration.

Verification:

```powershell
npm.cmd run typecheck --prefix apps/web
npm.cmd run lint --prefix apps/web
npm.cmd test --prefix apps/web
npm.cmd run build --prefix apps/web
npm.cmd run test:e2e --prefix apps/web
```

Expected: all current routes render and no hydration/console errors occur.

## Task 2: Generate and Enforce the API Client

**Files:** `apps/web/lib/api/generated/*`, generation script/config, contract-drift tests

- [ ] Generate TypeScript schemas/client from `docs/api/openapi.json` using a pinned generator. Never edit generated files manually.

- [ ] Wrap generated calls in `lib/api/server-client.ts` and `client.ts` to add request ID, session authorization, timeout, and common error mapping.

- [ ] Server wrapper obtains access token only from server session. Browser JavaScript never receives refresh token and does not store access token in `localStorage`.

- [ ] CI regenerates to a temporary directory and fails when diff exists. Handwritten `features/*/types.ts` matching API resources are removed or limited to view-only models with mapping tests.

- [ ] Tests prove request IDs, timeout, `401` session path, `403`, `404`, validation fields, rate limit/retry-after display, and safe internal-error behavior.

## Task 3: Implement Cognito Login, Callback, Session, and Logout

**Files:** auth route handlers, session encryption, middleware, auth tests

- [ ] `/login` creates PKCE verifier/challenge, state, nonce, and same-site HTTP-only secure transient cookie, then redirects to exact Cognito authorization endpoint.

- [ ] Callback validates state/nonce, exchanges code server-side, validates issuer/audience/signature/expiry/token use, creates encrypted HTTP-only session, clears transient values, and redirects only to allowlisted internal paths.

- [ ] Session refresh is server-side with rotation and bounded clock skew. Logout clears local session and redirects through Cognito logout URL.

- [ ] Middleware protects application routes but does not trust UI role claims for API authorization. Login/callback errors have safe user messages and request IDs.

- [ ] Tests cover state mismatch, nonce mismatch, code replay, expired token, unverified email, open redirect, missing refresh, logout, cookie flags, and production HTTPS requirement.

## Task 4: Remove Demo Session and Production Fixtures

**Files:** `features/auth/permissions.ts`, dashboard API, env schema, build guard/tests

- [ ] Delete `demoSession`. Load `/v1/me` and map server-returned role/permissions to navigation visibility.

- [ ] Dashboard calls `/v1/dashboard/summary`. Fixtures are imported only by tests/story fixtures, never production feature modules.

- [ ] Startup/build fails when `NEXT_PUBLIC_USE_FIXTURES=true` in staging/production. Local fixture mode is explicit and visually labeled.

- [ ] Add repository test scanning production frontend source for imports from `tests/mocks` and identifiers `demoSession`/`PlaceholderSurface` after final page replacement.

## Task 5: Build the New Search Form and Submission Flow

**Files:** `features/search/components/NewSearchForm.tsx`, schemas/mappers, page/tests

- [ ] Use generated source/evidence enums plus Zod refinements for question length, at least one approved source, valid date range, optional PICO fields, and `onlyApprovedSources=true` in production.

- [ ] Load available sources from `/v1/sources`; display disabled source reason and terms/coverage information.

- [ ] Submit with a UUID idempotency key, handle validation/conflict/rate-limit errors, and route to `/search/{searchId}/results` on `202`.

- [ ] Prevent double submit while allowing retry with the same key/body after network uncertainty.

- [ ] Component tests cover keyboard submission, validation, disabled source, duplicate click, server field errors, retry, and successful navigation. Playwright submits a real staging/local-stack job.

## Task 6: Build Research Status and Results

**Files:** results page, progress timeline, answer/claim/citation components, tests

- [ ] Initial server render loads search detail. Client polling uses bounded intervals/backoff and stops on terminal state or hidden/offline browser. Avoid one timer per component.

- [ ] Show planning/search/retrieval/synthesis/governance/review steps, timestamps, safe errors, cancellation, and retry guidance.

- [ ] Completed answer renders claims and citations, uncertainty, contradictions, limitations, abstention, and model/index/policy version disclosure. Never show a partial model stream as an approved answer.

- [ ] Citation activation opens exact source/chunk detail, is keyboard accessible, and indicates retraction/correction/quality warnings.

- [ ] Tests cover every run state, empty result, abstention, unknown citation defensive failure, polling stop, cancellation, stale version, and safe errors.

## Task 7: Build Sources and Evidence Details

**Files:** sources page, evidence table/detail drawer, filters, tests

- [ ] Use server pagination and URL search params for source/type/quality/date/cited/retraction filters. Do not load entire evidence sets into browser memory.

- [ ] Detail shows document/version/source/license metadata, methodology, exact excerpt/location, quality assessment, correction/retraction status, and cited claims.

- [ ] Full text appears only when source policy and user permission allow it. Presigned access is short-lived and not embedded in cached HTML.

- [ ] Tests cover filter URL state, pagination, inaccessible full text, retracted warning, table keyboard navigation, and cross-scope `404`.

## Task 8: Build Governance Transparency

**Files:** governance page/components, score explanation, audit timeline, tests

- [ ] Display Trust Score component inputs/weights and explicitly state it is not an accuracy probability.

- [ ] Show source compliance, evidence methodology, model/prompt/index/policy versions, citation validation, warnings, export decision, review state/history, and audit ID.

- [ ] Blocked/review-required states are prominent and cannot be hidden. Download-governance action uses approved API/export path.

- [ ] Tests cover incomplete/blocked/review/eligible/exported/superseded states, score override display, warning accessibility, and version changes.

## Task 9: Build Review Queue and Decision Workspace

**Files:** review list/detail/checklist/comment/decision components, tests

- [ ] Queue uses scoped server filters for status, priority, reason, assignee, due age, and pagination.

- [ ] Detail co-locates answer, citations/evidence, governance, audit history, assignment, required roles, and reviewer checklist.

- [ ] Decision forms require current version, explicit decision, reason/comment policy, and idempotency key. Stale `409` reloads current state and does not discard draft comment without warning.

- [ ] UI hides actions without permission but API denial remains tested. Self-review restriction and multi-role requirements are explained.

- [ ] Component/Playwright tests cover assign, comment, approve, changes request, reject, escalate, stale race, notification failure display, and unauthorized role.

## Task 10: Build Upload and Evidence Library

**Files:** upload form/progress, library list/detail, tests

- [ ] Upload requires source, non-PHI attestation, supported file, size/type checks, and explains quarantine/scanning.

- [ ] Request presigned POST, upload directly with progress, finalize idempotently, then poll ingestion status. Never send file through Next.js/API server memory.

- [ ] Display blocked malware/PHI/unknown/parser results with safe guidance; never reveal sensitive matched text.

- [ ] Library supports pagination/filter/version/status/source/date, reprocess for authorized admin, and retention/delete request.

- [ ] Tests cover invalid/double extension, too large, expired presign, interrupted upload/resume guidance, checksum failure, blocked scan, duplicate document, ready detail, and wrong role.

## Task 11: Build Report Generation and Downloads

**Files:** report form/preview/status/history components, tests

- [ ] Load eligible exact answer/governance/review versions. Disable generation with explicit reason when blocked/pending/superseded.

- [ ] First-release options are title, audience, detail level, PDF/DOCX, and approved section toggles that cannot remove citations, limitations, governance, review history, or audit ID.

- [ ] Submit export idempotently, show job status, render safe preview from persisted data, and request short-lived download URL on explicit click.

- [ ] Tests cover review gate, version mismatch, duplicate submit, failed render, expired URL refresh, download authorization, and mandatory sections.

## Task 12: Build Workspace and Admin Views

**Files:** workspace page, admin routes/pages, tests

- [ ] Workspace page displays tenant/workspace identity, membership/role, approved sources, active model/index/policy versions, and safe usage summary.

- [ ] Admin views manage memberships, source/model/prompt/methodology/governance policies only through versioned APIs with reason, idempotency, confirmation, and audit history.

- [ ] Connector health, queue/system readiness, index status, provider health/cost, audit events, and release version are visible to authorized roles.

- [ ] No admin page displays secret values, hashes usable for authentication, raw provider payloads, or unrestricted cross-tenant data.

## Task 13: Accessibility, Performance, and Browser Matrix

- [ ] Every page has one main landmark, hierarchical headings, labels/descriptions, keyboard focus, visible focus, status announcements, skip navigation, and color-independent warning meaning.
- [ ] Run axe on critical routes with zero serious/critical violations. Manually verify keyboard-only and screen-reader flows for search, citation, review, upload, and export.
- [ ] Use bundle analysis to prevent provider SDKs/server secrets from client bundles. Lazy-load heavy report/admin components. Avoid client waterfalls by server-loading independent initial data in parallel.
- [ ] Define performance budgets for shared JS, route JS, LCP, CLS, and INP; CI fails on approved budget regression.
- [ ] Playwright runs Chromium plus one Firefox/WebKit smoke set at desktop and mobile widths. Capture console/network failures and screenshots on test failure.

## Task 14: Remove All Placeholder Surfaces and Validate Staging

- [ ] Repository scan proves no application route imports `PlaceholderSurface`, `demoSession`, or dashboard test fixtures.
- [ ] Navigate every sidebar/deep link with researcher, reviewer, admin, compliance, and viewer roles; verify allowed/forbidden actions.
- [ ] Complete full login -> search -> evidence -> governance -> review -> export and upload -> library -> retrieval flows in staging.
- [ ] Test expired session, provider failure, offline/retry, stale version, cross-tenant URL, mobile layout, and browser back/forward behavior.
- [ ] Record Playwright report, accessibility report, bundle budgets, OpenAPI client hash, staging deployment ID, and owner sign-off; mark Plan 9 complete.

## Exit Gate

- Next.js 16/React 19 upgrade passes tests independently.
- Browser auth uses Cognito PKCE and secure server session; no token is in local storage.
- All product pages use real typed APIs with complete states.
- No production fixture, demo session, or placeholder surface remains.
- Search, evidence, governance, review, upload, library, report, workspace, and admin journeys pass Playwright.
- Accessibility and performance budgets pass.
- UI cannot bypass API authorization, governance, review, or export gates.

## Handoff

Plan 10 evaluates the integrated frontend/backend/cloud release under operational, security, performance, recovery, support, and controlled-pilot conditions.

