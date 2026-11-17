"""Technical SEO rules. Each rule declares WHICH pages are eligible (its denominator) and which are affected.

A rule with zero eligible pages reports 'no data' (null rate), never 0%. Findings describe observed facts
from this crawl; they are not guarantees about rankings, rich results or AI visibility.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.crawl.parse import normalize_url, url_hash
from app.models import AuditRuleResult, AuditRun, CrawlIssue, CrawlJob, CrawlLink, CrawlPage, SitemapEntry

RULESET_VERSION = "2026.11-1"
MAX_ISSUES_PER_RULE = 5000
HTML_TYPES = ("text/html", "application/xhtml+xml")


@dataclass(frozen=True)
class Rule:
    key: str
    title: str
    severity: str  # high | medium | low | info
    eligible: str  # human description of the denominator
    why: str


RULES: dict[str, Rule] = {r.key: r for r in [
    Rule("http_4xx", "Client error responses (4xx)", "high", "All fetched URLs",
         "Visitors and crawlers reaching these URLs get an error instead of content."),
    Rule("http_5xx", "Server error responses (5xx)", "high", "All fetched URLs",
         "Server errors can stop pages being crawled and indexed."),
    Rule("redirect_chain", "Redirect chains (2+ hops)", "medium", "All fetched URLs",
         "Each extra hop adds latency and can lose crawl budget; link directly to the final URL."),
    Rule("title_missing", "Missing <title>", "high", "HTML pages returning 200",
         "The title is a primary relevance and display signal in search results."),
    Rule("title_length", "Title shorter than 10 or longer than 60 characters", "low",
         "HTML pages returning 200 with a title", "A guideline only: very short or long titles are often truncated."),
    Rule("title_duplicate", "Duplicate titles", "medium", "Indexable HTML pages returning 200 with a title",
         "Identical titles make pages hard to distinguish."),
    Rule("meta_description_missing", "Missing meta description", "low", "Indexable HTML pages returning 200",
         "Search engines may generate a snippet instead; a written description gives you control."),
    Rule("meta_description_duplicate", "Duplicate meta descriptions", "low",
         "Indexable HTML pages returning 200 with a meta description", "Duplicated descriptions add no information."),
    Rule("h1_missing", "Missing H1 heading", "medium", "HTML pages returning 200",
         "A clear main heading helps users and machines understand the page topic."),
    Rule("h1_multiple", "Multiple H1 headings", "low", "HTML pages returning 200",
         "Not an error in HTML5, but a single main heading is usually clearer."),
    Rule("canonical_missing", "No canonical link", "low", "Indexable HTML pages returning 200",
         "A self-referencing canonical reduces duplicate-URL ambiguity."),
    Rule("canonical_target_not_200", "Canonical points to a non-200 or redirecting URL", "high",
         "HTML pages whose canonical target was crawled", "Canonicals should point at the final, working URL."),
    Rule("noindex", "Pages marked noindex", "info", "HTML pages returning 200",
         "Informational: confirm these pages are intentionally excluded from indexing."),
    Rule("lang_missing", "Missing <html lang>", "low", "HTML pages returning 200",
         "Declaring the language helps accessibility tools and language targeting."),
    Rule("broken_internal_link", "Pages linking to broken internal URLs", "high",
         "HTML pages with at least one internal link to a crawled URL",
         "Links to error pages waste crawl budget and frustrate visitors."),
    Rule("jsonld_invalid", "Invalid JSON-LD structured data", "medium", "HTML pages containing JSON-LD",
         "Syntax/structure errors prevent the markup from being read. Valid markup does not guarantee rich "
         "results or AI inclusion."),
    Rule("sitemap_url_not_200", "Sitemap URLs that are not 200", "medium",
         "In-scope sitemap URLs that were crawled", "Sitemaps should list final, working, indexable URLs."),
    Rule("indexable_not_in_sitemap", "Indexable pages missing from the sitemap", "info",
         "Indexable HTML pages returning 200 (only when a sitemap was found)",
         "Informational: sitemaps help discovery of important pages."),
    Rule("slow_fetch", "Slow responses (> 3 s to fetch)", "info", "All fetched URLs",
         "Crawler-observed fetch time from our server's location. Not Core Web Vitals or real-user data."),
]}


Finding = tuple[CrawlPage | None, str, dict[str, Any]]


def run_audit(db: Session, job: CrawlJob) -> AuditRun:
    tid = job.tenant_id
    existing = db.scalar(select(AuditRun).where(AuditRun.tenant_id == tid, AuditRun.crawl_job_id == job.id))
    if existing is not None:  # idempotent re-run
        db.execute(delete(CrawlIssue).where(CrawlIssue.tenant_id == tid, CrawlIssue.audit_run_id == existing.id))
        db.execute(delete(AuditRuleResult).where(AuditRuleResult.tenant_id == tid,
                                                 AuditRuleResult.audit_run_id == existing.id))
        db.delete(existing)
        db.flush()
    pages = list(db.scalars(select(CrawlPage).where(CrawlPage.tenant_id == tid, CrawlPage.crawl_job_id == job.id,
                                                    CrawlPage.state == "fetched")))
    run = AuditRun(tenant_id=tid, crawl_job_id=job.id, client_id=job.client_id, ruleset_version=RULESET_VERSION,
                   pages_fetched=len(pages))
    db.add(run)
    db.flush()

    by_hash = {p.url_hash: p for p in pages}
    html_ok = [p for p in pages if p.status_code == 200 and (p.content_type or "") in HTML_TYPES]
    indexable = [p for p in html_ok if p.is_indexable]
    sitemap_hashes = set(db.scalars(select(SitemapEntry.url_hash).where(
        SitemapEntry.tenant_id == tid, SitemapEntry.crawl_job_id == job.id)))

    def simple(eligible: list[CrawlPage], pred: Callable[[CrawlPage], bool],
               ev: Callable[[CrawlPage], dict[str, Any]]) -> tuple[int, list[Finding]]:
        return len(eligible), [(p, p.url, ev(p)) for p in eligible if pred(p)]

    def duplicates(eligible: list[CrawlPage], key: Callable[[CrawlPage], str | None], label: str
                   ) -> tuple[int, list[Finding]]:
        groups: dict[str, list[CrawlPage]] = defaultdict(list)
        elig = [p for p in eligible if key(p)]
        for p in elig:
            groups[(key(p) or "").strip().lower()].append(p)
        out: list[Finding] = []
        for g in groups.values():
            if len(g) > 1:
                for p in g:
                    out.append((p, p.url, {label: key(p), "shared_with": [o.url for o in g if o is not p][:10],
                                           "group_size": len(g)}))
        return len(elig), out

    results: dict[str, tuple[int, list[Finding]]] = {}
    results["http_4xx"] = simple(pages, lambda p: 400 <= (p.status_code or 0) < 500,
                                 lambda p: {"status": p.status_code})
    results["http_5xx"] = simple(pages, lambda p: (p.status_code or 0) >= 500, lambda p: {"status": p.status_code})
    results["redirect_chain"] = simple(pages, lambda p: len(p.redirect_chain or []) >= 2,
                                       lambda p: {"hops": p.redirect_chain, "final_url": p.final_url})
    results["title_missing"] = simple(html_ok, lambda p: not p.title, lambda p: {})
    titled = [p for p in html_ok if p.title]
    results["title_length"] = simple(titled, lambda p: not 10 <= len(p.title or "") <= 60,
                                     lambda p: {"title": p.title, "length": len(p.title or "")})
    results["title_duplicate"] = duplicates(indexable, lambda p: p.title, "title")
    results["meta_description_missing"] = simple(indexable, lambda p: not p.meta_description, lambda p: {})
    results["meta_description_duplicate"] = duplicates(indexable, lambda p: p.meta_description, "meta_description")
    results["h1_missing"] = simple(html_ok, lambda p: not p.h1, lambda p: {})
    results["h1_multiple"] = simple(html_ok, lambda p: len(p.h1 or []) > 1, lambda p: {"h1": (p.h1 or [])[:5]})
    results["canonical_missing"] = simple(indexable, lambda p: not p.canonical, lambda p: {})

    canon_elig: list[tuple[CrawlPage, CrawlPage]] = []
    for p in html_ok:
        target = normalize_url(p.canonical) if p.canonical else None
        if target and url_hash(target) in by_hash:
            canon_elig.append((p, by_hash[url_hash(target)]))
    results["canonical_target_not_200"] = (len(canon_elig), [
        (p, p.url, {"canonical": t.url, "target_status": t.status_code, "target_final_url": t.final_url})
        for p, t in canon_elig if t.status_code != 200 or (t.final_url and normalize_url(t.final_url) != t.url)])
    results["noindex"] = simple(html_ok, lambda p: p.is_indexable is False,
                                lambda p: {"meta_robots": p.meta_robots, "x_robots_tag": p.x_robots_tag})
    results["lang_missing"] = simple(html_ok, lambda p: not p.lang, lambda p: {})

    links = db.execute(select(CrawlLink.from_page_id, CrawlLink.to_url, CrawlLink.to_url_hash).where(
        CrawlLink.tenant_id == tid, CrawlLink.crawl_job_id == job.id, CrawlLink.is_internal.is_(True))).all()
    page_by_id = {p.id: p for p in html_ok}
    targets: dict[Any, list[tuple[str, int | None]]] = defaultdict(list)
    for from_id, to_url, h in links:
        if from_id in page_by_id and h in by_hash:
            targets[from_id].append((to_url, by_hash[h].status_code))
    broken: list[Finding] = []
    for from_id, outs in targets.items():
        bad = sorted({(u, s) for u, s in outs if (s or 0) >= 400}, key=lambda x: x[0])
        if bad:
            p = page_by_id[from_id]
            broken.append((p, p.url, {"broken_targets": [{"url": u, "status": s} for u, s in bad[:20]],
                                      "broken_count": len(bad)}))
    results["broken_internal_link"] = (len(targets), broken)

    with_ld = [p for p in html_ok if p.jsonld]
    results["jsonld_invalid"] = simple(with_ld, lambda p: any(not b.get("valid") for b in p.jsonld or []),
                                       lambda p: {"blocks": [b for b in p.jsonld or [] if not b.get("valid")][:5]})
    in_map = [p for p in pages if p.url_hash in sitemap_hashes]
    results["sitemap_url_not_200"] = simple(
        in_map, lambda p: p.status_code != 200 or bool(p.redirect_chain),
        lambda p: {"status": p.status_code, "final_url": p.final_url})
    if sitemap_hashes:
        results["indexable_not_in_sitemap"] = simple(indexable, lambda p: p.url_hash not in sitemap_hashes,
                                                     lambda p: {})
    else:
        results["indexable_not_in_sitemap"] = (0, [])
    results["slow_fetch"] = simple(pages, lambda p: (p.fetch_ms or 0) > 3000, lambda p: {"fetch_ms": p.fetch_ms})

    for key, (eligible, found) in results.items():
        rule = RULES[key]
        db.add(AuditRuleResult(tenant_id=tid, audit_run_id=run.id, rule_key=key, severity=rule.severity,
                               eligible_count=eligible, affected_count=len(found)))
        for page, url, evidence in found[:MAX_ISSUES_PER_RULE]:
            db.add(CrawlIssue(tenant_id=tid, audit_run_id=run.id, client_id=job.client_id, rule_key=key,
                              severity=rule.severity, crawl_page_id=page.id if page else None, url=url,
                              evidence=evidence))
    db.flush()
    return run
