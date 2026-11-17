# AI Search Visibility System

Multi-tenant AI Search Visibility Intelligence & Optimization platform for agencies and their clients.

> **Status: Phase 2 complete — awaiting approval for Phase 3.** Implemented: auth, MFA, multi-tenancy with
> PostgreSQL row-level security, roles, members, client CRM, audit log, UI shell (Phase 1); domain verification,
> SSRF-safe crawler with Celery worker, and evidence-backed technical SEO audit (Phase 2). See
> `docs/phase-1-report.md` and `docs/phase-2-report.md`. Everything else in `docs/` is design only.

## Core principle

Evidence before claims. Human approval before consequential changes. No fabricated metrics, no
guaranteed AI citations, rankings, traffic or revenue. Every number carries source, timestamp,
method, scope, denominator and a confidence label.

## Quick start

See [`docs/setup.md`](docs/setup.md) for local development, tests, Docker Compose deployment and backups.

## Repository layout

| Path | Contents |
|---|---|
| `blueprint/` | Source requirements: Complete Blueprint V2 (PDF) and Master Coding Prompt V2 (TXT) |
| `docs/00-repository-audit.md` | Phase 0 repository audit |
| `docs/architecture.md` | Target architecture and module boundaries |
| `docs/adr/` | Architecture decision records |
| `docs/data-model.md` | Entities, relationships, tenant ownership, indexes |
| `docs/api-surface.md` | Versioned REST API outline |
| `docs/metrics-methodology.md` | Metric definitions, denominators, confidence labels |
| `docs/provider-capabilities.md` | Integration/provider capability registry (initial, unverified) |
| `docs/threat-model.md` | Security threats and mitigations |
| `docs/screen-map.md` | Dashboard screens, roles and states |
| `docs/roadmap.md` | Phases, acceptance criteria, approval gates |
| `docs/open-questions.md` | Decisions needed from the product owner |
| `docs/setup.md` | Development, testing, deployment, backup/restore |
| `docs/phase-1-report.md` | Phase 1 deliverables, test results, limitations |
| `docs/phase-2-report.md` | Phase 2 deliverables, test results, limitations |
| `docs/crawler-methodology.md` | Crawl scope, robots handling, SSRF controls, audit rules and denominators |
| `apps/api` | FastAPI API, Alembic migrations, tests, demo seed |
| `apps/web` | Next.js web app, Playwright e2e tests |
| `infra/` | PostgreSQL role bootstrap, Caddy config |
| `docker-compose.yml` | Reference deployment |
| `prototype/index.html` | Phase 0 static prototype — **demo fixtures only, no backend** |

## Viewing the prototype

Open `prototype/index.html` in a browser. It is self-contained static HTML. All data shown is a
labelled demo fixture and does not represent any real organization or measurement.
