# Architecture

Status: **Proposed (Phase 0)** — not implemented.

## 1. System context

```
            ┌──────────────┐        HTTPS (cookie session + CSRF)
 Browser ──►│ apps/web     │──────────────┐
            │ Next.js (SSR)│              ▼
            └──────────────┘       ┌──────────────┐     ┌────────────┐
                                   │ apps/api     │────►│ PostgreSQL │ (source of truth, RLS)
                                   │ FastAPI /v1  │     └────────────┘
                                   └──────┬───────┘     ┌────────────┐
                                          │ enqueue     ►│ Redis      │ (queue, rate limits, cache)
                                          ▼             └────────────┘
                                   ┌──────────────┐     ┌────────────┐
                                   │ apps/worker  │────►│ Object     │ (private: evidence, reports)
                                   │ Celery       │     │ storage S3 │
                                   └──────┬───────┘     └────────────┘
                                          │ egress only via SafeFetcher / ProviderAdapter
                                          ▼
                     Customer websites · Google APIs · Approved AI provider APIs
```

The web app never calls third parties directly and never holds secrets. All outbound network
traffic from workers goes through two choke points: `SafeFetcher` (crawler) and
`ProviderAdapter` (APIs). Both enforce allow-lists, quotas and audit logging.

## 2. Backend modules (modular monolith)

Each module owns its tables, service layer and router. Cross-module calls go through service
interfaces, not direct table access.

| Module | Responsibility | Blueprint ref |
|---|---|---|
| `core` | config, DB session, tenant context, errors, pagination, audit log writer | — |
| `auth` | users, sessions, MFA, invitations, password reset | §3 |
| `tenancy` | tenants, agencies, memberships, roles, permissions, project access | §3 |
| `crm` | clients, contacts, projects, brands, domains, markets, languages, competitors, goals, notes | A |
| `provenance` | data sources, provenance records, confidence labels | §2 |
| `crawl` | domain verification, crawl jobs, SafeFetcher, robots, sitemaps, pages | B |
| `audit` | technical SEO checks, issues, structured data | C, K |
| `integrations` | OAuth connections, GSC/GA4 clients, CSV imports, encrypted credentials | D |
| `visibility` | providers, prompt sets, runs, observations, mentions, citations, competitors | E–H |
| `content` | content assets/versions, topic mapping, gaps, briefs | I, J |
| `workflow` | recommendations, tasks, approvals, implementation changes, comments | L–N |
| `verification` | before/after re-crawls and re-tests | O |
| `analytics` | analytics events, conversions, leads, attribution | P |
| `reports` | report assembly, PDF rendering, client portal | Q |
| `alerts` | notification rules and delivery | R |
| `governance` | retention, deletion requests, exports, consent | §11 |

## 3. Tenancy model

- **Tenant** = one agency workspace (the billing/isolation boundary). Clients belong to exactly one tenant.
- Every tenant-owned table has a non-null `tenant_id` FK and a composite index leading with `tenant_id`.
- **Layer 1 (application):** the request's tenant is resolved from the authenticated membership,
  never from a client-supplied header or body. Repositories require a `TenantContext`; there is no
  un-scoped query helper for tenant-owned tables.
- **Layer 2 (database):** PostgreSQL Row-Level Security on tenant-owned tables using
  `current_setting('app.tenant_id')`, set per transaction. The app connects as a non-owner role
  without `BYPASSRLS`. Migrations run as a separate owner role.
- **Jobs:** every Celery task payload carries `tenant_id`; the task re-establishes tenant context
  and re-checks that referenced objects belong to it.
- **Cache keys** are prefixed `t:{tenant_id}:`. **Object keys** are `tenants/{tenant_id}/...`;
  downloads use short-lived signed URLs issued only after an authorization check.
- **Client portal users** (Client Admin/Viewer) are tenant members restricted to specific client IDs.

## 4. Authorization

RBAC with permissions as strings (`client.read`, `crawl.run`, `approval.decide`, …). A membership
carries a role at tenant scope plus optional client/project grants. Every endpoint declares its
required permission; a test enumerates all routes and fails if any route lacks a declaration.

| Role | Scope | Notable rights |
|---|---|---|
| Platform Super Admin | platform | tenant lifecycle; **no** silent data access (break-glass, audit-logged) |
| Agency Owner | tenant | everything incl. billing, roles, retention |
| Agency Admin | tenant | everything except ownership transfer/billing |
| Account Manager | assigned clients | CRM, reports, request client approval |
| SEO/AEO Analyst | assigned projects | crawls, prompt sets, observation review/correction |
| Content Editor | assigned projects | briefs, content versions |
| Technical Implementer | assigned projects | tasks, record implementation changes |
| Client Admin | own client | view, approve/reject, invite client viewers |
| Client Viewer | own client | read-only portal |
| Auditor | tenant or client | read-only incl. audit log |

## 5. Auth & sessions

- Argon2id password hashing; breached-password check optional (k-anonymity API, opt-in).
- Server-side sessions in Postgres/Redis; cookie `__Host-session`, `Secure`, `HttpOnly`, `SameSite=Lax`.
- CSRF: double-submit token required on all unsafe methods.
- Optional TOTP MFA with recovery codes; tenants may require MFA.
- Invitations: single-use, hashed tokens, 72h expiry, bound to email.
- Login rate limiting per IP and per account; generic error messages.

## 6. Crawler (SafeFetcher)

1. Domain must be **verified** (DNS TXT, HTML meta tag, or file at `/.well-known/`) for the tenant.
2. URL scheme `http`/`https` only; ports 80/443 by default.
3. Resolve DNS; reject if **any** resolved IP is loopback, private (RFC1918, ULA), link-local,
   CGNAT, multicast, reserved, unspecified, or IPv4-mapped forms of these.
4. Connect **to the validated IP** (pinning) with SNI/Host set to the hostname — defeats rebinding.
5. Redirects followed manually (max 5), each hop re-validated (steps 2–4) and kept within the
   verified domain scope (configurable to allow `www` and subdomains).
6. Limits: connect/read timeouts, max response bytes (e.g. 5 MB HTML), content-type allow-list,
   per-host concurrency 1–2, configurable delay, depth and page caps, per-tenant daily caps.
7. robots.txt fetched and honoured for the declared user agent; `Crawl-delay` respected.
8. Identifies itself: `AISVBot/<ver> (+https://<deployment>/bot)`.
9. Never executes JavaScript. HTML parsed with a non-executing parser; stored text sanitized.
10. All skips (robots, scope, size, type, error) recorded with reason. Pause/cancel via job state.
11. Environment proxy variables ignored by the fetcher.

## 7. Provider / AI layer

- `ProviderAdapter` interface: `capabilities()`, `run(prompt, params) -> RawResponse`, `estimate_cost()`.
- Capability registry (see `provider-capabilities.md`) stored in DB and versioned; a provider is
  unusable until an admin marks its terms reviewed and supplies a key.
- Raw responses stored as evidence (where provider terms permit) with hash, model, params, locale, cost, latency.
- Extraction (mentions, citations, sentiment) is a separate step producing **schema-validated**
  output (Pydantic). Deterministic extraction (URL parsing, exact/alias brand match) runs first;
  LLM-assisted extraction is labelled `ai_extracted_unverified` until an analyst reviews it.
- Untrusted text (pages, provider answers) is passed only as delimited data, never concatenated
  into system instructions. Model outputs can never invoke tools or external actions.
- Retries with exponential backoff and jitter; idempotency key per run to avoid duplicate runs.
- Token and cost tracking per run, per tenant, with budget caps that halt scheduling.

## 8. Frontend

- Next.js App Router, TypeScript strict, server components for data fetching via a typed client
  generated from the API's OpenAPI schema.
- Accessible components (Radix primitives), WCAG 2.2 AA target, keyboard navigable, visible focus.
- Every screen implements empty / loading / error / success states. Controls that are not yet
  implemented are rendered **disabled with an explanation**, never as dead buttons.
- Every metric component requires a `provenance` prop (source, method, scope, n, timestamp,
  confidence) — enforced by types so a number cannot render without it.
- CSP with nonces, no inline event handlers, no third-party scripts by default.

## 9. Reports

HTML templates rendered server-side to PDF (WeasyPrint). The report engine reads the same query
services as the dashboard, so exported numbers match on-screen numbers. Each report is an
immutable snapshot (inputs + rendered PDF hash) once issued.

## 10. Deployment

| Target | Viable? | Notes |
|---|---|---|
| Docker Compose on a VPS (≥2 vCPU, 4 GB) | **Yes — default** | web, api, worker, beat, postgres, redis, minio/S3, caddy |
| Managed containers (Fly, Render, ECS, Cloud Run) + managed Postgres/Redis/S3 | Yes | Preferred for production scale |
| cPanel / basic shared hosting | **No** for full product | No Redis, no persistent workers, process limits kill crawls. At most a static marketing site. |

Operational requirements: Alembic migrations on deploy, structured JSON logs (secrets redacted),
error tracking, health/readiness endpoints, nightly Postgres backups with **tested** restore,
object storage versioning.
