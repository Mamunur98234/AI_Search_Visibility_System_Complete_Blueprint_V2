# Crawler & Technical Audit Methodology

Ruleset version: **2026.11-1** (`apps/api/app/crawl/audit.py`). Shown on every audit as provenance.

## Who we crawl
Only hostnames whose ownership a workspace has verified (DNS TXT at `_aisv-challenge.<host>`, HTML meta tag on
`https://<host>/`, or `https://<host>/.well-known/aisv-verification.txt`). Tokens are per workspace: another
agency verifying the same hostname needs its own proof. The crawl is limited to that **exact host**.

## How we crawl
- User agent `Mozilla/5.0 (compatible; AISVBot/0.2; +<your-site>/bot)`; public explanation at `/bot`.
- robots.txt (RFC 9309): 2xx parsed (an `AISVBot` group overrides `*`); 404/410 and other 4xx (except 401/403)
  allow all; **401/403 and 5xx/unreachable disallow all** (conservative); `Crawl-delay` honoured up to 30 s.
- Seeds: homepage plus in-scope sitemap URLs (sitemap index followed; max 10 sitemap files, 50,000 entries).
- One request at a time per host (a cross-tenant host lock), configurable delay (default 1 s, minimum enforced
  by the deployment), page cap (≤ deployment limit), depth cap, discovery cap (5 × page cap).
- No JavaScript execution, no forms, no logins, no cookies. HTML parsed with a non-executing parser.
- HTTPS first, HTTP fallback only if HTTPS cannot connect.
- Every URL ends as **fetched**, **skipped** (reason) or **error** (reason). Nothing is silently dropped;
  URLs beyond the discovery cap are counted (`urls_dropped`) and disclosed in the audit limitations.

## SSRF and safety controls
See `docs/threat-model.md` T6–T8 and `apps/api/app/crawl/fetcher.py`. Every hop is re-validated; any address that
is not globally routable (incl. cloud metadata, CGNAT, IPv4-mapped / 6to4 / NAT64 / Teredo forms) is refused
before connecting; the socket connects to the validated IP; 5 MB decoded-body cap; connect/read/total timeouts;
environment proxies ignored; sitemaps parsed with defusedxml (no entity expansion, no DTDs, no external entities).

## How redirects are evaluated
A URL that redirects records **its own** status (e.g. 301) and hop chain; its destination is evaluated once as
its own URL. This prevents double-counting the destination's content.

## Rules, denominators, severity
Rate = affected ÷ eligible for that rule. If eligible = 0 the rate is **null ("No data")**, never 0%.

| Rule | Eligible (denominator) | Affected | Severity |
|---|---|---|---|
| http_4xx / http_5xx | all fetched URLs | status 4xx / 5xx | high |
| redirect_chain | all fetched URLs | ≥ 2 hops | medium |
| title_missing | HTML 200 pages | no/empty `<title>` | high |
| title_length | HTML 200 pages with a title | < 10 or > 60 chars (guideline) | low |
| title_duplicate | indexable HTML 200 with title | title shared (case-insensitive) | medium |
| meta_description_missing | indexable HTML 200 | none | low |
| meta_description_duplicate | indexable HTML 200 with description | shared | low |
| h1_missing / h1_multiple | HTML 200 pages | 0 / > 1 H1 | medium / low |
| canonical_missing | indexable HTML 200 | no canonical link | low |
| canonical_target_not_200 | HTML 200 whose canonical target was crawled | target not 200 or redirects | high |
| noindex | HTML 200 pages | meta robots / X-Robots-Tag noindex or none | info |
| lang_missing | HTML 200 pages | no `<html lang>` | low |
| broken_internal_link | HTML 200 pages with ≥ 1 internal link to a crawled URL | ≥ 1 link to 4xx/5xx | high |
| jsonld_invalid | HTML pages containing JSON-LD | syntax error, missing @context or @type | medium |
| sitemap_url_not_200 | in-scope sitemap URLs that were crawled | not 200 or redirects | medium |
| indexable_not_in_sitemap | indexable HTML 200 (only if a sitemap exists) | not listed | info |
| slow_fetch | all fetched URLs | > 3 s crawler fetch time | info |

"Indexable" = no `noindex`/`none` directive in meta robots or X-Robots-Tag. Canonicalisation is reported, not
used to exclude pages.

## What audits do NOT claim
No ranking, traffic, rich-result or AI-citation outcome is implied. Fetch time is measured from the crawler's
location and is not Core Web Vitals. JavaScript-rendered content is not evaluated. Pages not crawled (robots,
caps, errors) are not evaluated and are listed with reasons.

## Confidence label
`first_party_verified` — our own crawl of a domain whose ownership was verified in this workspace.
