# Threat Model (STRIDE-oriented)

Status: **Proposed (Phase 0)**. Each mitigation gets an automated test in the phase that implements it.

## Assets
Client data (CRM, analytics, leads), OAuth refresh tokens and API keys, crawl/observation evidence,
reports, audit logs, user credentials, tenant isolation itself.

## Trust boundaries
Browser ↔ web/API · API ↔ DB/Redis/storage · Worker ↔ internet (customer sites, Google, AI providers) ·
Untrusted content (crawled HTML, uploaded files, provider answers) ↔ AI extraction layer.

## Threats and mitigations

| # | Threat | Mitigation | Test (phase) |
|---|---|---|---|
| T1 | Cross-tenant read/write (IDOR) | Tenant from session membership only; composite FKs; RLS; object lookup always `(tenant_id, id)`; 404 not 403 for foreign objects | Parametrized test hitting every route with a second tenant's IDs (P1) |
| T2 | Privilege escalation inside tenant | Per-route permission declaration; route-coverage test; client-scoped grants | Role matrix tests (P1) |
| T3 | Session theft / fixation | `__Host-` cookies, HttpOnly, Secure, SameSite; rotate on login/MFA; idle + absolute timeouts; revoke on password change | (P1) |
| T4 | CSRF | Double-submit token on unsafe methods; strict CORS allow-list | (P1) |
| T5 | Credential stuffing / brute force | Per-IP + per-account rate limits, Argon2id, optional MFA, generic errors | (P1) |
| T6 | SSRF via crawler / redirects / sitemaps | SafeFetcher: scheme/port allow-list, IP-range deny-list (v4+v6, mapped addrs), DNS pinning, per-hop re-validation, no env proxies, verified-domain scope | Tests with 127.0.0.1, 169.254.169.254, `[::1]`, decimal/octal IPs, rebinding DNS stub, redirect to private IP (P2) |
| T7 | Crawling unauthorized sites | Domain verification required; scope rules; robots.txt honoured; identified UA | (P2) |
| T8 | Resource exhaustion (zip bombs, huge pages, infinite crawl) | Byte caps on decompressed body, timeouts, depth/page caps, per-tenant quotas | (P2) |
| T9 | Stored XSS from crawled/imported/provider content | Never render untrusted HTML; React escaping; sanitized excerpts; CSP with nonces; no `dangerouslySetInnerHTML` without sanitizer + lint rule | (P1–P4) |
| T10 | SQL injection | ORM/bound parameters only; lint banning raw string SQL | (P1) |
| T11 | Unsafe uploads (CSV/attachments) | Size/type allow-list, content sniffing, store outside web root with random keys, CSV formula-injection escaping on export, AV scan hook | (P3) |
| T12 | Secret leakage | Envelope encryption (KEK in env/KMS, per-record DEK), key versioning + rotation, secrets never in API responses/logs/URLs; log redaction filter; secret scanning in CI | (P1/P3) |
| T13 | Prompt injection from pages/answers | Untrusted text passed as delimited data; schema-validated outputs; no tool access for extraction models; outputs cannot trigger actions; injection test corpus | (P4) |
| T14 | Autonomous harmful actions | No production write integrations in MVP; all consequential actions require recorded Approval | (P5) |
| T15 | Fabricated / misleading metrics | Provenance required by type system; null-not-zero; denominators shown; report snapshot matches dashboard query services | (P2–P5) |
| T16 | Cost abuse of providers | Per-tenant budgets, rate limits, idempotency keys, admin enablement | (P4) |
| T17 | Report/export leakage | Signed short-lived URLs post-authorization; tenant-prefixed keys; export audit events | (P5) |
| T18 | Audit log tampering | Append-only table (no UPDATE/DELETE grants); hash chaining optional | (P1) |
| T19 | Super-admin overreach | Break-glass access with reason + audit event + tenant-visible notice | (P1) |
| T20 | Supply chain | Lockfiles, pinned versions, dependency audit (`pip-audit`, `npm audit`) in CI | (P1) |

## Security headers (baseline)
`Content-Security-Policy` (nonce-based, `frame-ancestors 'none'`), `Strict-Transport-Security`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Permissions-Policy` minimal.
