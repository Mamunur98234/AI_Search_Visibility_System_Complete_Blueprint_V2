# Phase 1 Report — Foundation

Date: 2026-11-17 · Status: **complete, awaiting approval for Phase 2**

## Delivered

| Area | What works |
|---|---|
| Auth | Signup (creates workspace + owner), login, logout, Argon2id hashing, server-side sessions (HttpOnly cookie, rotated on login/MFA/tenant switch/password change), idle + absolute expiry, password reset (token in URL fragment, single use, revokes sessions), password change (revokes other sessions), optional TOTP MFA with 10 single-use recovery codes, MFA secret encrypted at rest (Fernet, key rotation supported) |
| Abuse controls | Login rate limits per IP and per account (Redis; in-memory only in dev/test), limits on signup, reset, MFA attempts; generic login errors; no account enumeration on reset |
| Web security | CSRF double-submit token + Origin check on all unsafe methods; strict CORS; API security headers; per-request nonce CSP on pages; X-Frame-Options/`frame-ancestors 'none'`; no `dangerouslySetInnerHTML` (lint rule); open-redirect guard on `next=` |
| Tenancy | Shared schema with `tenant_id`; tenant resolved only from the session; composite FKs so children cannot reference another tenant's parent; **PostgreSQL RLS (FORCE)** on every tenant table; app connects as a non-owner role without BYPASSRLS |
| Roles | 9 tenant roles + platform-admin flag; 18 permissions; tenant-wide vs client-granted scope; only owners grant owner; last-owner protection; self-removal blocked |
| Members | Invite (72h, single-use, hashed token, header-transported), accept as new or existing user, multi-workspace switching, role / status / client-access edits, removal, revocation |
| CRM | Clients (search, status filter, cursor pagination, archive), contacts, brands (aliases), domains (strict hostname validation, IDNA, uniqueness, single primary; **unverified until Phase 2**), projects (dates validated), project markets/languages (reference data), competitors (domains, aliases), internal notes (hidden from client roles) |
| Audit log | Every CRM, membership and workspace mutation writes an append-only entry (app role lacks UPDATE/DELETE) with actor, diff, IP, request ID; secrets redacted; filterable UI with pagination |
| UI shell | Next.js 16 app: sidebar with role-aware items and **disabled future modules labelled by phase**, workspace switcher, all Phase 1 screens with empty/loading/error/success states, keyboard tabs, native modal dialogs, responsive to 375 px, light/dark |
| Demo data | `scripts/seed_demo.py`: fictional "(demo)" organizations on `example.*` domains; refuses to run in production |
| Delivery | Dockerfiles, Compose (Caddy edge, internal backend network), CI workflow, OpenAPI contract + generated TS types |

## Test results (run 2026-11-17 in this environment)

| Command | Result |
|---|---|
| `ruff check app tests scripts` | All checks passed |
| `mypy app` (strict) | No issues in 26 files |
| `pytest -q` (real PostgreSQL 16, RLS active) | **66 passed** |
| `pip-audit --skip-editable` | No known vulnerabilities |
| `eslint . --max-warnings=0` | Passed |
| `tsc --noEmit` | Passed |
| `next build` | Passed (13 routes) |
| `npm audit` | 0 vulnerabilities |
| `playwright test` (Next prod build → FastAPI → PostgreSQL) | **4 passed** |
| `docker compose config -q` | Valid |
| `docker compose build` | **Not verified** (sandbox network; see setup.md) |

Notable backend tests:
- `test_every_object_route_returns_404_for_foreign_ids` — tenant B's owner calls **every** route with a path parameter using tenant A's IDs: all 404 and tenant A data unchanged.
- `test_role_matrix[*]` — for 8 roles × all 47 permission-guarded route/methods: 403 exactly when the role lacks the permission.
- `test_access_policy_snapshot` / `test_every_route_declares_access` — CI fails if a route has no declared access policy or its policy changes without review.
- RLS: no tenant context → 0 rows on all 13 tables; cross-tenant INSERT rejected by policy; UPDATE affects 0 rows; app role cannot UPDATE/DELETE audit log; app role is not superuser/BYPASSRLS.

End-to-end: owner signup → client → invalid then valid domain → brand → note containing `<img onerror>` rendered inert → invite scoped Client Viewer → accept in a separate browser → viewer sees only the granted client, no notes tab, no audit log, disabled "New client" → audit trail visible; axe-core (WCAG 2.1 AA tags) reports no serious/critical violations on 6 screens; nonce CSP header present with no CSP console errors; no horizontal scroll at 375 px.

## Issues found and fixed during the phase
- Next.js 16.4.4 had a moderate advisory (GHSA-mfr8-8qww-v76h); pinned 16.4.5.
- Next.js rewrites pass client-supplied `X-Forwarded-For` through: deployment now relies on Caddy overwriting it, documented.
- `FORCE ROW LEVEL SECURITY` blocked the invitation-lookup SECURITY DEFINER function; added an owner-only read policy.

## Known limitations / deferred
- Domain verification, crawling, integrations, AI visibility: Phases 2–4 (shown disabled in the UI).
- Access grants are per client, not yet per project.
- No workspace-level "require MFA" policy, no TOTP replay window tracking, no session list/revoke-other-devices UI.
- Platform Super Admin is a stored flag only; break-glass access workflow not built.
- Access events (logins) are stored but not yet shown in the UI.
- Email is sent synchronously; background worker (Celery) arrives with the crawler in Phase 2.
- Inline edit exists for clients only; other CRM records are add/delete in the UI (PATCH exists in the API).
- Retention, deletion requests and exports: later phases.
- Docker image build not verified here (see above).

## Next: Phase 2 plan (awaiting approval)
Domain verification (DNS TXT, meta tag, well-known file) → Celery + Redis worker → SafeFetcher (SSRF-safe, DNS pinning, redirect re-validation, size/time caps, robots.txt) → crawl jobs with pause/cancel and skip reasons → technical SEO rules with affected/eligible denominators and evidence → audit workspace UI. SSRF test suite first.
