# ADR 0001 — Stack, monorepo and tenancy strategy

Status: Proposed · Date: 2026-11-17

## Context
Empty repository. Blueprint prefers Next.js + FastAPI + PostgreSQL + Redis/Celery + object storage,
with strict multi-tenant isolation and honest assessment of shared hosting.

## Decision
1. Monorepo: `apps/web` (Next.js/TS), `apps/api` (FastAPI, Python 3.12+), `apps/worker` (Celery, shares `apps/api` package).
2. PostgreSQL 16 with SQLAlchemy 2.x + Alembic. UUIDv7 primary keys (sortable, non-guessable).
3. Shared-schema multi-tenancy (`tenant_id` on every tenant-owned row) with **two enforcement layers**:
   application `TenantContext` + PostgreSQL Row-Level Security.
4. Redis 7 for queue broker, rate limiting and tenant-prefixed cache.
5. S3-compatible private object storage (MinIO locally).
6. First-party session auth in the API (no third-party auth SaaS) to keep tenant data in one trust boundary.
7. Docker Compose is the reference deployment; cPanel/shared hosting is explicitly unsupported for the app.

## Alternatives considered
- **Schema-per-tenant / DB-per-tenant:** stronger isolation, but migration and connection-pool cost
  is high for many small client workspaces. Revisit for enterprise tier (Phase 7).
- **Node-only backend:** would unify language, but Python has stronger tooling for crawling/parsing,
  NLP extraction and PDF rendering, and the blueprint prefers FastAPI.
- **Managed auth (Auth0/Clerk):** faster MFA/SSO, but adds a processor of client PII and cost; SSO
  can be added later via OIDC.

## Consequences
- RLS requires setting `app.tenant_id` per transaction and testing that a missing setting yields zero rows.
- Two languages in CI (Python + TypeScript); OpenAPI codegen keeps the contract in sync.
