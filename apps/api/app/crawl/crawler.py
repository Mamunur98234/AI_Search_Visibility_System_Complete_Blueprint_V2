"""Crawl job execution. Runs inside the worker (or in-process for dev/tests).

Every URL ends in exactly one recorded state: fetched, skipped (with reason) or error (with reason).
Pause/cancel are honoured between requests. All DB access is tenant-scoped (RLS context per transaction).
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.db import session_factory, set_db_context
from app.crawl import hostlock
from app.crawl.audit import run_audit
from app.crawl.fetcher import FetchError, FetchResult, SafeFetcher
from app.crawl.parse import normalize_url, parse_html, url_hash
from app.crawl.robots import RobotsPolicy, build_policy, parse_sitemap
from app.models import CrawlJob, CrawlLink, CrawlPage, Domain, SitemapEntry
from app.models.base import utcnow

log = logging.getLogger("aisv.crawler")

HTML_TYPES = ("text/html", "application/xhtml+xml")
SKIP_REASONS = {"out_of_scope", "redirect_out_of_scope", "blocked_ip", "blocked_port", "blocked_scheme",
                "invalid_url"}
MAX_SITEMAP_FILES = 10
MAX_ROBOTS_DELAY_S = 30.0
DISCOVERY_FACTOR = 5  # cap on URLs recorded per crawl = max_pages * factor


def make_fetcher(user_agent: str) -> SafeFetcher:
    """Factory (tests replace it to reach a local test site through the same SafeFetcher code)."""
    return SafeFetcher(user_agent)


class _Ctx:
    def __init__(self, db: Session, tenant_id: uuid.UUID) -> None:
        self.db, self.tenant_id = db, tenant_id
        set_db_context(db, tenant_id=tenant_id, user_id=None)

    def commit(self) -> None:
        self.db.commit()
        set_db_context(self.db, tenant_id=self.tenant_id, user_id=None)  # SET LOCAL ends with the transaction


def run_crawl(tenant_id: uuid.UUID, job_id: uuid.UUID,
              fetcher_factory: Callable[[str], SafeFetcher] | None = None,
              sleep: Callable[[float], None] = time.sleep) -> str:
    """Returns the job's resulting status, 'deferred' (host busy) or 'ignored'."""
    db = session_factory()()
    ctx = _Ctx(db, tenant_id)
    owner = str(job_id)
    job: CrawlJob | None = None
    try:
        job = db.scalar(select(CrawlJob).where(CrawlJob.tenant_id == tenant_id, CrawlJob.id == job_id))
        if job is None or job.status not in ("queued", "running"):
            return "ignored"
        domain = db.scalar(select(Domain).where(Domain.tenant_id == tenant_id, Domain.id == job.domain_id))
        if domain is None or domain.verification_status != "verified" or domain.hostname != job.hostname:
            _finish(ctx, job, "failed", error="Domain is not verified; crawling is not permitted.")
            return "failed"
        if not hostlock.acquire(job.hostname, owner):
            job.note = "Waiting: another crawl of this host is in progress."
            ctx.commit()
            return "deferred"
        try:
            return _execute(ctx, job, (fetcher_factory or make_fetcher)(job.user_agent), owner, sleep)
        finally:
            hostlock.release(job.hostname, owner)
    except Exception as exc:
        log.exception("crawl failed", extra={"job_id": str(job_id)})
        db.rollback()
        set_db_context(db, tenant_id=tenant_id, user_id=None)
        failed = db.scalar(select(CrawlJob).where(CrawlJob.tenant_id == tenant_id, CrawlJob.id == job_id))
        if failed is not None:
            _finish(ctx, failed, "failed", error=f"Internal error: {type(exc).__name__}")
        return "failed"
    finally:
        db.close()


def _finish(ctx: _Ctx, job: CrawlJob, status: str, error: str | None = None) -> None:
    job.status = status
    job.requested_action = None
    job.finished_at = utcnow() if status in ("completed", "cancelled", "failed") else None
    if error:
        job.error = error[:1000]
    ctx.commit()


def _in_scope(job: CrawlJob) -> Callable[[str], bool]:
    def check(url: str) -> bool:
        n = normalize_url(url)
        if n is None:
            return False
        rest = n.split("://", 1)[1]
        return rest.split("/", 1)[0] == job.hostname

    return check


def _execute(ctx: _Ctx, job: CrawlJob, fetcher: SafeFetcher, owner: str, sleep: Callable[[float], None]) -> str:
    db = ctx.db
    job.status = "running"
    job.note = None
    job.started_at = job.started_at or utcnow()
    ctx.commit()
    in_scope = _in_scope(job)

    if job.robots_outcome is None and not _bootstrap(ctx, job, fetcher, in_scope, sleep):
        return job.status
    policy = build_policy(job.robots_status, job.robots_txt)
    delay = max(job.delay_ms / 1000.0, min(job.crawl_delay_s or 0.0, MAX_ROBOTS_DELAY_S))
    last_request = time.monotonic()

    while True:
        db.refresh(job)
        if job.requested_action == "cancel":
            _skip_remaining(ctx, job, "cancelled")
            _finish(ctx, job, "cancelled")
            return "cancelled"
        if job.requested_action == "pause":
            _finish(ctx, job, "paused")
            return "paused"
        if job.pages_fetched + job.pages_errored >= job.max_pages:
            _skip_remaining(ctx, job, "page_cap_reached")
            break
        page = db.scalar(select(CrawlPage).where(
            CrawlPage.tenant_id == job.tenant_id, CrawlPage.crawl_job_id == job.id, CrawlPage.state == "queued",
        ).order_by(CrawlPage.depth, CrawlPage.id).limit(1))
        if page is None:
            break
        if not policy.allowed(page.url):
            _mark(page, "skipped", "robots_disallowed", f"robots.txt ({policy.outcome})")
            job.pages_skipped += 1
            ctx.commit()
            continue
        wait = delay - (time.monotonic() - last_request)
        if wait > 0:
            sleep(wait)
        hostlock.refresh(job.hostname, owner)
        try:
            res = fetcher.fetch(page.url, in_scope=in_scope)
        except FetchError as exc:
            state = "skipped" if exc.reason in SKIP_REASONS else "error"
            _mark(page, state, exc.reason, exc.detail)
            if state == "skipped":
                job.pages_skipped += 1
            else:
                job.pages_errored += 1
        else:
            _record(ctx, job, page, res, in_scope)
            job.pages_fetched += 1
        last_request = time.monotonic()
        ctx.commit()

    run_audit(db, job)
    _finish(ctx, job, "completed")
    return "completed"


def _mark(page: CrawlPage, state: str, reason: str | None, detail: str | None = None) -> None:
    page.state = state
    page.skip_reason = reason
    page.error_detail = (detail or None) and detail[:500]
    page.fetched_at = utcnow()


def _skip_remaining(ctx: _Ctx, job: CrawlJob, reason: str) -> None:
    result = ctx.db.execute(update(CrawlPage).where(
        CrawlPage.tenant_id == job.tenant_id, CrawlPage.crawl_job_id == job.id, CrawlPage.state == "queued",
    ).values(state="skipped", skip_reason=reason))
    job.pages_skipped += int(getattr(result, "rowcount", 0) or 0)
    ctx.commit()


def _enqueue(ctx: _Ctx, job: CrawlJob, url: str, depth: int, source: str) -> bool:
    h = url_hash(url)
    if ctx.db.scalar(select(CrawlPage.id).where(CrawlPage.tenant_id == job.tenant_id,
                                                CrawlPage.crawl_job_id == job.id, CrawlPage.url_hash == h)):
        return False
    if job.urls_discovered >= job.max_pages * DISCOVERY_FACTOR:
        job.urls_dropped += 1
        return False
    if depth > job.max_depth:
        ctx.db.add(CrawlPage(tenant_id=job.tenant_id, crawl_job_id=job.id, url=url, url_hash=h, depth=depth,
                             source=source, state="skipped", skip_reason="depth_limit"))
        job.pages_skipped += 1
    else:
        ctx.db.add(CrawlPage(tenant_id=job.tenant_id, crawl_job_id=job.id, url=url, url_hash=h, depth=depth,
                             source=source, state="queued"))
    job.urls_discovered += 1
    ctx.db.flush()
    return True


def _bootstrap(ctx: _Ctx, job: CrawlJob, fetcher: SafeFetcher, in_scope: Callable[[str], bool],
               sleep: Callable[[float], None]) -> bool:
    """robots.txt (scheme negotiation), sitemaps, seed URLs. Returns False if the job ended."""
    result: FetchResult | None = None
    base = None
    last_error = ""
    for scheme in ("https", "http"):
        candidate = f"{scheme}://{job.hostname}/"
        try:
            result = fetcher.fetch(candidate + "robots.txt", in_scope=in_scope, accept="text/plain,*/*;q=0.5")
            base = candidate
            break
        except FetchError as exc:
            last_error = f"{exc.reason} {exc.detail}".strip()
            if exc.reason == "redirect_out_of_scope":
                base = candidate
                break
            if exc.reason in ("connection_error", "tls_error", "timeout"):
                continue
            _finish(ctx, job, "failed", error=f"Cannot crawl this host: {last_error}")
            return False
    if base is None:
        _finish(ctx, job, "failed", error=f"Could not connect over HTTPS or HTTP ({last_error})")
        return False

    job.base_url = base
    if result is None:
        policy = RobotsPolicy("unreachable_disallow_all", None, None)
        job.note = "robots.txt redirects to another host; verify and crawl that host instead."
    else:
        text = result.text(limit=500 * 1024) if result.status < 300 else None
        policy = build_policy(result.status, text)
    job.robots_outcome = policy.outcome
    job.robots_status = policy.status
    job.robots_txt = policy.text
    job.crawl_delay_s = policy.crawl_delay
    _enqueue(ctx, job, base, 0, "seed")
    ctx.commit()  # never hold row locks across network I/O (pause/cancel requests must not wait)

    sitemap_queue = [s for s in policy.sitemaps if in_scope(s)] or [base + "sitemap.xml"]
    seen: set[str] = set()
    fetched_files = 0
    entries = 0
    while sitemap_queue and fetched_files < MAX_SITEMAP_FILES and policy.outcome != "unreachable_disallow_all":
        sm = sitemap_queue.pop(0)
        if sm in seen or not policy.allowed(sm):
            continue
        seen.add(sm)
        fetched_files += 1
        sleep(job.delay_ms / 1000.0)
        try:
            r = fetcher.fetch(sm, in_scope=in_scope, accept="application/xml,text/xml;q=0.9,*/*;q=0.5")
        except FetchError:
            continue
        if r.status != 200:
            continue
        doc = parse_sitemap(r.body)
        sitemap_queue.extend(c for c in doc.child_sitemaps if in_scope(c))
        for loc, lastmod in doc.urls:
            n = normalize_url(loc)
            if n is None or entries >= 50_000:
                continue
            entries += 1
            ctx.db.add(SitemapEntry(tenant_id=job.tenant_id, crawl_job_id=job.id, sitemap_url=sm[:2000], url=n,
                                    url_hash=url_hash(n), lastmod=lastmod))
            if in_scope(n):
                _enqueue(ctx, job, n, 1, "sitemap")
        job.sitemap_urls_found = entries
        ctx.commit()
    job.sitemap_urls_found = entries
    ctx.commit()
    if policy.outcome in ("unreachable_disallow_all", "auth_disallow_all"):
        _skip_remaining(ctx, job, "robots_disallowed")
        run_audit(ctx.db, job)
        _finish(ctx, job, "completed")
        return False
    return True


def _record(ctx: _Ctx, job: CrawlJob, page: CrawlPage, res: FetchResult, in_scope: Callable[[str], bool]) -> None:
    page.state = "fetched"
    # A redirecting URL records ITS OWN response status; its destination is evaluated once, as its own URL.
    page.status_code = int(str(res.redirect_chain[0]["status"])) if res.redirect_chain else res.status
    page.final_url = res.final_url
    page.redirect_chain = res.redirect_chain or None
    page.content_type = res.content_type[:120] or None
    page.bytes = len(res.body)
    page.fetch_ms = res.elapsed_ms
    page.fetched_at = utcnow()
    page.x_robots_tag = (res.headers.get("x-robots-tag") or "")[:300] or None
    final = normalize_url(res.final_url)
    if final and final != page.url and in_scope(final):
        _enqueue(ctx, job, final, page.depth, "link")
    if res.redirect_chain or res.status != 200 or res.content_type not in HTML_TYPES:
        return
    parsed = parse_html(res.text(), res.final_url)
    page.title = parsed.title
    page.meta_description = parsed.meta_description
    page.meta_robots = parsed.meta_robots
    page.canonical = parsed.canonical
    page.h1 = parsed.h1
    page.h2_count = parsed.h2_count
    page.lang = parsed.lang
    page.word_count = parsed.word_count
    page.content_hash = parsed.content_hash
    page.jsonld = parsed.jsonld or None
    directives = f"{parsed.meta_robots or ''},{page.x_robots_tag or ''}".lower()
    page.is_indexable = "noindex" not in directives and "none" not in [d.strip() for d in directives.split(",")]
    for link in parsed.links:
        internal = in_scope(link.url)
        ctx.db.add(CrawlLink(tenant_id=job.tenant_id, crawl_job_id=job.id, from_page_id=page.id, to_url=link.url,
                             to_url_hash=url_hash(link.url), is_internal=internal, nofollow=link.nofollow,
                             anchor_text=link.anchor or None))
        if internal:
            _enqueue(ctx, job, link.url, page.depth + 1, "link")


def count_by_state(db: Session, job: CrawlJob) -> dict[str, int]:
    rows = db.execute(select(CrawlPage.state, func.count()).where(
        CrawlPage.tenant_id == job.tenant_id, CrawlPage.crawl_job_id == job.id).group_by(CrawlPage.state)).all()
    return {state: int(n) for state, n in rows}
