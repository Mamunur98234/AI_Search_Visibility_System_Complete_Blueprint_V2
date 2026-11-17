# Phase 2 Report — Domain verification, safe crawler, technical SEO MVP

Date: 2026-11-17 · Status: **complete, awaiting approval for Phase 3**

## Delivered
| Area | What works |
|---|---|
| Domain verification | DNS TXT (`_aisv-challenge.<host>`), HTML meta tag and `/.well-known/` file (HTTPS only); per-workspace tokens; rate-limited checks; failures explained; every attempt audit-logged; domains with crawl history cannot be deleted (evidence retained) |
| SafeFetcher | SSRF-safe HTTP client: scheme/port/credential checks, DNS resolution with deadline, refusal of any non-public address (incl. metadata, CGNAT, mapped/6to4/NAT64/Teredo), DNS pinning, per-hop redirect re-validation and scope checks, 5 MB decoded cap (compression bombs), timeouts, proxies ignored |
| Crawler | robots.txt (RFC 9309, conservative on 401/403/5xx), Crawl-delay, sitemaps (defusedxml), homepage + sitemap seeds, exact-host scope, page/depth/discovery caps, cross-tenant per-host lock, pause / resume (from persisted queue) / cancel, every URL fetched/skipped/error with reason, crash-safe re-delivery (acks_late) |
| Worker | Celery + Redis (`aisv.crawl` task on queue `crawl`); in-process thread mode for local dev; sync mode for tests; production config requires Celery |
| Technical audit | 19 rules with explicit denominators, severity, rationale; null-not-zero rates; evidence per affected URL (status, redirect hops, duplicates, broken targets, canonical target, JSON-LD errors); triage (open / accepted / won't fix + note), audit-logged |
| Provenance | Audit summary carries source, method + ruleset version, scope, collection window, sample size, confidence label and limitations |
| UI | Domains & audits list; domain page (verification wizard, crawl settings, history); crawl page (live progress, pause/resume/cancel, provenance, findings table with affected/eligible/rate, evidence drawer, triage, page log with skip reasons, robots.txt); public `/bot` page |
| Permissions | `domain.verify`, `crawl.run`, `issue.manage` added; client roles can read audits but not run or triage |
| Deployment | Compose `worker` service; `egress` network for api/worker only; Postgres/Redis remain internal |

## Test results (run 2026-11-17 in this environment)
| Command | Result |
|---|---|
| `ruff check app tests scripts` | All checks passed |
| `mypy app` (strict) | No issues in 38 files |
| `pytest -q` (PostgreSQL 16 + RLS, local test website) | **154 passed** |
| `eslint . --max-warnings=0` · `tsc --noEmit` · `next build` | Passed |
| `playwright test` (real stack, local demo website) | **6 passed** |
| `pip-audit` · `npm audit --omit=dev` | No known vulnerabilities · 0 vulnerabilities |
| Celery path (API → Redis → `celery -A app.worker` → DB) | Verified manually: task received, executed, outcome recorded |
| `docker compose config -q` | Valid (image build still not verifiable in this sandbox) |

New test highlights:
- **SSRF suite (63 tests):** 30+ address classes refused; hostnames resolving to internal IPs refused *before any socket opens*; mixed answer sets refused; redirect to `169.254.169.254` and to internal hostnames blocked; DNS-rebinding simulation (public then loopback) blocked with one resolution per hop; scheme/port/credential/`0x7f000001` rejections; redirect loops, oversized bodies, 20 MB gzip bomb and slow responses aborted; environment proxies ignored; correct Host/User-Agent.
- **Crawl integration:** a deterministic demo site with known defects; all 19 rules asserted to exact (eligible, affected) pairs; robots-disallowed URL never requested; out-of-scope / other-port links never fetched; inline script never executed; pause → resume yields results identical to an uninterrupted crawl; cancel records remaining URLs; robots 503/403/404 semantics; Crawl-delay honoured; host lock defers concurrent crawls.
- **Verification:** file, meta tag and DNS flows; another workspace's token does not verify; rate limit.
- **Tenant isolation / role matrix:** automatically extended to all 15 new routes (foreign IDs → 404; permissions exactly enforced).
- **E2E:** verify → crawl (observed live while running) → findings with denominators → evidence → triage → page log → robots tab → audit log; axe has no serious/critical violations on the domain and crawl pages.

## Bugs found and fixed during the phase
- Redirecting URLs were initially evaluated with their destination's content, double-counting duplicates/H1/lang findings. Now each URL records its own status; destinations are evaluated once.
- The crawler held a row lock on the job across sitemap fetches, so a pause/cancel request could wait for network I/O. It now commits before any network call.
- `useApi` could report "not loading, no data" for one render after its path changed, crashing the findings panel when a live crawl completed. Fixed in the hook and covered by the e2e test.

- dnspython 2.9.0 had CVE-2026-128089 (zone-file WKS parsing; not used by this app). Pinned the fixed 2.9.2.
- Dependency pins: Celery 5.6.3 / kombu 5.6.2 / redis-py 6.4.0 chosen over releases younger than two weeks.

## Known limitations / deferred
- No JavaScript rendering; content injected client-side is not audited.
- Only the exact verified host (no subdomain wildcard); `www` and apex must each be verified.
- Core Web Vitals / real-user performance: not available from a crawler; needs a sourced integration (later).
- Audit history comparison (before/after) is Phase 6 (verification). Issue triage is per crawl run.
- Retention of crawl data: no automatic purge yet (retention policies are a later phase).
- Real-internet crawling could not be exercised in this sandbox (no direct outbound DNS/HTTP); all crawler tests use a local site through the production SafeFetcher code path.
- Object storage (raw HTML snapshots) not added; evidence is stored as structured fields. MinIO moves to Phase 5 (reports/PDF).

## Next: Phase 3 plan (awaiting approval)
Google Search Console + GA4 via official OAuth (encrypted refresh tokens, key rotation job), CSV import with validation report, provenance on every imported number, page-to-topic mapping. Requires a Google Cloud OAuth client (see open questions).
