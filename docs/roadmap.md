# Roadmap & Approval Gates

Each phase ends with: working demo, checklist, exact commands + test results, known limitations,
next plan. **Work stops until the product owner explicitly approves.**

## Phase 0 — Discovery & design (this deliverable)
- [x] Repository audit (`00-repository-audit.md`)
- [x] Architecture + ADR 0001
- [x] Data model, API surface, screen map
- [x] Metric methodology, provider registry (draft), threat model
- [x] Static clickable prototype with labelled demo fixtures (`prototype/index.html`)
- [ ] **Owner:** design-partner interviews / workflow validation (cannot be done by the coding agent)
- [ ] **Owner:** answers to `open-questions.md`

## Phase 1 — Foundation
Scope: monorepo scaffold, Docker Compose (postgres, redis, minio, api, worker, web), CI
(ruff, mypy, pytest, eslint, tsc, vitest, Playwright, pip-audit, npm audit, secret scan);
auth (login, logout, sessions, CSRF, password reset, invitations, optional TOTP MFA); tenants,
memberships, 10 system roles, permissions, client/project grants; RLS; audit log; CRM CRUD
(clients, contacts, projects, brands, domains (unverified), markets, languages, competitors, notes);
UI shell with navigation, role-aware menus, disabled future modules, all states; seed script for
**labelled demo fixtures**.

Acceptance:
1. An Agency Owner can sign up a tenant, invite a member, assign a role, create a client with brand, domain, project and competitor.
2. Every CRM mutation writes an audit log entry visible to Auditor.
3. Cross-tenant test suite: for every route, a user of tenant B receives 404 for tenant A object IDs; RLS returns 0 rows without tenant context.
4. Role matrix tests pass; a route without a permission declaration fails CI.
5. CSRF, session rotation, login rate limit tests pass.
6. Lighthouse/axe: no critical accessibility violations on shell screens.

## Phase 2 — Domain verification, safe crawler, technical SEO MVP
Acceptance: DNS TXT / meta / file verification; crawl only verified domains; SSRF test suite passes;
robots respected; pause/cancel works; issues for status, redirects, canonical, robots, sitemap,
title/meta, headings, internal/broken links, duplicate titles/descriptions, JSON-LD syntax;
each issue shows affected/eligible and evidence URL list.

## Phase 3 — GSC/GA4 + imports, provenance, page mapping
Acceptance: OAuth connect/disconnect with encrypted tokens; sync jobs with status/errors; CSV import
with validation report; provenance shown on all imported numbers; page-to-topic mapping with rules.

## Phase 4 — AI visibility
Acceptance: prompt sets with versions; at least one provider adapter behind registry gating
(given a key) **and** import path; idempotent runs with cost tracking; mention/citation detection
with analyst correction; metrics with denominators; competitor comparison on identical run set;
prompt-injection test corpus passes.

## Phase 5 — Recommendations, tasks, approvals, portal, PDF
Acceptance: recommendation → task → approval → implementation record chain with audit trail; client
portal scoped to client; monthly PDF with all required sections and methodology/limitations, numbers
matching dashboard.

## Phase 6 — Verification, alerts, content workflows, advanced modules
## Phase 7 — Billing, white-label, performance, enterprise controls

## MVP = Phases 1–5 + verification from Phase 6.
