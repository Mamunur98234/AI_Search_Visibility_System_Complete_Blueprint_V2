# AI Search Visibility System

Multi-tenant AI Search Visibility Intelligence & Optimization platform for agencies and their clients.

> **Status: Phase 0 (design).** No application code exists yet. Nothing described in `docs/` is
> implemented unless a later phase report says so and links to passing tests.

## Core principle

Evidence before claims. Human approval before consequential changes. No fabricated metrics, no
guaranteed AI citations, rankings, traffic or revenue. Every number carries source, timestamp,
method, scope, denominator and a confidence label.

## Repository layout (current)

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
| `prototype/index.html` | Static clickable UI prototype — **demo fixtures only, no backend** |

## Planned layout (Phase 1+)

```
apps/web      Next.js + TypeScript frontend
apps/api      FastAPI modular monolith (/api/v1)
apps/worker   Celery workers (crawl, imports, provider runs, reports)
infra/        Docker Compose, deployment configs
docs/         Architecture, methodology, runbooks
```

## Viewing the prototype

Open `prototype/index.html` in a browser. It is self-contained static HTML. All data shown is a
labelled demo fixture and does not represent any real organization or measurement.
