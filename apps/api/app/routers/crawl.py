"""Domain verification, crawl control, page evidence and technical-audit findings."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import get_db, set_db_context
from app.core.deps import Principal, TenantContext, authenticated, require
from app.core.errors import not_found
from app.core.permissions import Perm
from app.crawl import verification
from app.crawl.audit import RULES
from app.crawl.crawler import count_by_state, make_fetcher
from app.crawl.dispatch import dispatch_crawl
from app.models import AuditRuleResult, AuditRun, Client, CrawlIssue, CrawlJob, CrawlPage, Domain
from app.models.base import utcnow
from app.routers.crm import get_client
from app.schemas import (
    AuditSummaryOut,
    CrawlDetailOut,
    CrawlIn,
    CrawlOut,
    CrawlPageOut,
    DomainListOut,
    IssueOut,
    IssueUpdate,
    Page,
    Provenance,
    RuleOut,
    RuleResultOut,
    VerificationOut,
    VerificationStartIn,
)
from app.services import audit

router = APIRouter(tags=["crawl"])
ACTIVE = ("queued", "running", "paused")


def _domain(db: Session, ctx: TenantContext, domain_id: uuid.UUID) -> Domain:
    d = db.scalar(select(Domain).where(Domain.tenant_id == ctx.tenant_id, Domain.id == domain_id))
    if d is None or not ctx.can_access_client(d.client_id):
        raise not_found("Domain")
    return d


def _crawl(db: Session, ctx: TenantContext, crawl_id: uuid.UUID) -> CrawlJob:
    j = db.scalar(select(CrawlJob).where(CrawlJob.tenant_id == ctx.tenant_id, CrawlJob.id == crawl_id))
    if j is None or not ctx.can_access_client(j.client_id):
        raise not_found("Crawl")
    return j


def _verification_out(d: Domain) -> VerificationOut:
    instr = (verification.instructions(d.verification_method, d.hostname, d.verification_token)
             if d.verification_method and d.verification_token else None)
    return VerificationOut(domain_id=d.id, hostname=d.hostname, status=d.verification_status,
                           method=d.verification_method, instructions=instr, checked_at=d.verification_checked_at,
                           verified_at=d.verified_at, error=d.verification_error)


# ---------------- domains & verification ----------------
@router.get("/domains", response_model=list[DomainListOut])
def list_domains(db: Session = Depends(get_db), ctx: TenantContext = Depends(require(Perm.CLIENT_READ)),
                 status: str | None = Query(None, pattern="^(unverified|pending|verified|failed)$")
                 ) -> list[DomainListOut]:
    same_client = (Client.tenant_id == Domain.tenant_id) & (Client.id == Domain.client_id)
    q = (select(Domain, Client.name).join(Client, same_client)
         .where(Domain.tenant_id == ctx.tenant_id, ctx.client_filter(Domain.client_id), Client.status != "archived"))
    if status:
        q = q.where(Domain.verification_status == status)
    rows = db.execute(q.order_by(Client.name, Domain.hostname).limit(1000)).all()
    out = []
    for d, cname in rows:
        last = db.scalar(select(CrawlJob).where(CrawlJob.tenant_id == ctx.tenant_id, CrawlJob.domain_id == d.id)
                         .order_by(CrawlJob.created_at.desc()).limit(1))
        out.append(DomainListOut(id=d.id, client_id=d.client_id, client_name=cname, hostname=d.hostname,
                                 is_primary=d.is_primary, verification_status=d.verification_status,
                                 verified_at=d.verified_at, last_crawl_id=last.id if last else None,
                                 last_crawl_status=last.status if last else None,
                                 last_crawl_at=last.created_at if last else None))
    return out


@router.get("/domains/{domain_id}/verification", response_model=VerificationOut)
def get_verification(domain_id: uuid.UUID, db: Session = Depends(get_db),
                     ctx: TenantContext = Depends(require(Perm.CLIENT_READ))) -> VerificationOut:
    return _verification_out(_domain(db, ctx, domain_id))


@router.post("/domains/{domain_id}/verification", response_model=VerificationOut)
def start_verification(domain_id: uuid.UUID, body: VerificationStartIn, request: Request,
                       db: Session = Depends(get_db),
                       ctx: TenantContext = Depends(require(Perm.DOMAIN_VERIFY))) -> VerificationOut:
    d = _domain(db, ctx, domain_id)
    if d.verification_status == "verified":
        raise HTTPException(409, "This domain is already verified")
    d.verification_token = d.verification_token or verification.new_token()
    d.verification_method = body.method
    d.verification_status = "pending"
    d.verification_error = None
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="domain.verification_started",
                 object_type="domain", object_id=d.id, client_id=d.client_id, changes={"method": body.method},
                 request=request)
    return _verification_out(d)


@router.post("/domains/{domain_id}/verification/check", response_model=VerificationOut)
def check_verification(domain_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                       ctx: TenantContext = Depends(require(Perm.DOMAIN_VERIFY))) -> VerificationOut:
    d = _domain(db, ctx, domain_id)
    if d.verification_status == "verified":
        return _verification_out(d)
    if not d.verification_method or not d.verification_token:
        raise HTTPException(409, "Choose a verification method first")
    allowed, _ = ratelimit.hit(f"verify:{d.id}", 10, 600)
    if not allowed:
        raise HTTPException(429, "Too many verification checks. Wait a few minutes.", headers={"Retry-After": "600"})
    ok, reason = verification.check(d.verification_method, d.hostname, d.verification_token,
                                    fetcher=make_fetcher(get_settings().crawler_user_agent))
    d.verification_checked_at = utcnow()
    if ok:
        d.verification_status, d.verified_at, d.verification_error = "verified", utcnow(), None
    else:
        d.verification_status, d.verification_error = "pending", (reason or "Not verified")[:500]
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id,
                 action="domain.verified" if ok else "domain.verification_failed", object_type="domain",
                 object_id=d.id, client_id=d.client_id,
                 changes={"method": d.verification_method, "result": "verified" if ok else reason}, request=request)
    return _verification_out(d)


# ---------------- crawls ----------------
@router.post("/domains/{domain_id}/crawls", status_code=201, response_model=CrawlOut)
def start_crawl(domain_id: uuid.UUID, body: CrawlIn, request: Request, db: Session = Depends(get_db),
                ctx: TenantContext = Depends(require(Perm.CRAWL_RUN))) -> CrawlJob:
    s = get_settings()
    d = _domain(db, ctx, domain_id)
    if d.verification_status != "verified":
        raise HTTPException(409, "Verify ownership of this domain before crawling it")
    if body.max_pages > s.crawl_max_pages_limit:
        raise HTTPException(422, f"max_pages cannot exceed {s.crawl_max_pages_limit} on this deployment")
    if body.delay_ms < s.crawl_min_delay_ms:
        raise HTTPException(422, f"delay_ms must be at least {s.crawl_min_delay_ms}")
    if db.scalar(select(CrawlJob.id).where(CrawlJob.tenant_id == ctx.tenant_id, CrawlJob.domain_id == d.id,
                                           CrawlJob.status.in_(ACTIVE))):
        raise HTTPException(409, "A crawl of this domain is already queued, running or paused")
    allowed, _ = ratelimit.hit(f"crawl:tenant:{ctx.tenant_id}", 30, 86400)
    if not allowed:
        raise HTTPException(429, "Daily crawl limit for this workspace reached")
    job = CrawlJob(tenant_id=ctx.tenant_id, client_id=d.client_id, domain_id=d.id, hostname=d.hostname,
                   status="queued", max_pages=body.max_pages, max_depth=body.max_depth, delay_ms=body.delay_ms,
                   user_agent=s.crawler_user_agent, created_by_user_id=ctx.user_id)
    db.add(job)
    db.flush()
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="crawl.started", object_type="crawl",
                 object_id=job.id, client_id=d.client_id, changes=body.model_dump() | {"hostname": d.hostname},
                 request=request)
    db.commit()  # the executor reads the job in its own transaction
    set_db_context(db, tenant_id=ctx.tenant_id, user_id=ctx.user_id)  # SET LOCAL ended with the commit
    dispatch_crawl(ctx.tenant_id, job.id)
    db.refresh(job)
    return job


@router.get("/clients/{client_id}/crawls", response_model=list[CrawlOut])
def list_crawls(client_id: uuid.UUID, db: Session = Depends(get_db),
                ctx: TenantContext = Depends(require(Perm.CLIENT_READ))) -> list[CrawlJob]:
    get_client(db, ctx, client_id)
    return list(db.scalars(select(CrawlJob).where(CrawlJob.tenant_id == ctx.tenant_id, CrawlJob.client_id == client_id)
                           .order_by(CrawlJob.created_at.desc()).limit(100)))


@router.get("/crawls/{crawl_id}", response_model=CrawlDetailOut)
def read_crawl(crawl_id: uuid.UUID, db: Session = Depends(get_db),
               ctx: TenantContext = Depends(require(Perm.CLIENT_READ))) -> CrawlDetailOut:
    j = _crawl(db, ctx, crawl_id)
    out = CrawlDetailOut.model_validate(j)
    out.state_counts = count_by_state(db, j)
    out.robots_txt = j.robots_txt
    return out


def _control(db: Session, ctx: TenantContext, request: Request, crawl_id: uuid.UUID, action: str) -> CrawlJob:
    j = _crawl(db, ctx, crawl_id)
    before = j.status
    if action == "pause":
        if j.status == "running":
            j.requested_action = "pause"
        elif j.status == "queued":
            j.status = "paused"
        else:
            raise HTTPException(409, f"Cannot pause a {j.status} crawl")
    elif action == "resume":
        if j.status != "paused":
            raise HTTPException(409, f"Cannot resume a {j.status} crawl")
        j.status, j.requested_action = "queued", None
    elif action == "cancel":
        if j.status == "running":
            j.requested_action = "cancel"
        elif j.status in ("queued", "paused"):
            j.status, j.requested_action, j.finished_at = "cancelled", None, utcnow()
        else:
            raise HTTPException(409, f"Cannot cancel a {j.status} crawl")
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action=f"crawl.{action}",
                 object_type="crawl", object_id=j.id, client_id=j.client_id,
                 changes={"status_before": before, "status_after": j.status, "requested": j.requested_action},
                 request=request)
    db.commit()
    set_db_context(db, tenant_id=ctx.tenant_id, user_id=ctx.user_id)
    if action == "resume":
        dispatch_crawl(ctx.tenant_id, j.id)
    db.refresh(j)
    return j


@router.post("/crawls/{crawl_id}/pause", response_model=CrawlOut)
def pause_crawl(crawl_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                ctx: TenantContext = Depends(require(Perm.CRAWL_RUN))) -> CrawlJob:
    return _control(db, ctx, request, crawl_id, "pause")


@router.post("/crawls/{crawl_id}/resume", response_model=CrawlOut)
def resume_crawl(crawl_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                 ctx: TenantContext = Depends(require(Perm.CRAWL_RUN))) -> CrawlJob:
    return _control(db, ctx, request, crawl_id, "resume")


@router.post("/crawls/{crawl_id}/cancel", response_model=CrawlOut)
def cancel_crawl(crawl_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                 ctx: TenantContext = Depends(require(Perm.CRAWL_RUN))) -> CrawlJob:
    return _control(db, ctx, request, crawl_id, "cancel")


@router.get("/crawls/{crawl_id}/pages", response_model=Page[CrawlPageOut])
def crawl_pages(crawl_id: uuid.UUID, db: Session = Depends(get_db),
                ctx: TenantContext = Depends(require(Perm.CLIENT_READ)),
                state: str | None = Query(None, pattern="^(queued|fetched|skipped|error)$"),
                q: str | None = Query(None, max_length=200),
                cursor: uuid.UUID | None = None, limit: int = Query(50, ge=1, le=200)) -> Page[CrawlPageOut]:
    j = _crawl(db, ctx, crawl_id)
    stmt = select(CrawlPage).where(CrawlPage.tenant_id == ctx.tenant_id, CrawlPage.crawl_job_id == j.id)
    if state:
        stmt = stmt.where(CrawlPage.state == state)
    if q:
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(CrawlPage.url.ilike(f"%{esc}%", escape="\\"))
    if cursor:
        stmt = stmt.where(CrawlPage.id > cursor)
    rows = list(db.scalars(stmt.order_by(CrawlPage.id).limit(limit + 1)))
    return Page[CrawlPageOut](items=[CrawlPageOut.model_validate(p) for p in rows[:limit]],
                              next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None)


# ---------------- audit ----------------
def _run_for(db: Session, ctx: TenantContext, j: CrawlJob) -> AuditRun:
    run = db.scalar(select(AuditRun).where(AuditRun.tenant_id == ctx.tenant_id, AuditRun.crawl_job_id == j.id))
    if run is None:
        raise HTTPException(404, "No audit results yet (the crawl has not completed)")
    return run


@router.get("/crawls/{crawl_id}/audit", response_model=AuditSummaryOut)
def audit_summary(crawl_id: uuid.UUID, db: Session = Depends(get_db),
                  ctx: TenantContext = Depends(require(Perm.CLIENT_READ))) -> AuditSummaryOut:
    j = _crawl(db, ctx, crawl_id)
    run = _run_for(db, ctx, j)
    results = {r.rule_key: r for r in db.scalars(select(AuditRuleResult).where(
        AuditRuleResult.tenant_id == ctx.tenant_id, AuditRuleResult.audit_run_id == run.id))}
    rules = []
    for key, rule in RULES.items():
        r = results.get(key)
        if r is None:
            continue
        rules.append(RuleResultOut(key=key, title=rule.title, severity=rule.severity,
                                   eligible_definition=rule.eligible, why=rule.why, eligible_count=r.eligible_count,
                                   affected_count=r.affected_count,
                                   rate=(r.affected_count / r.eligible_count) if r.eligible_count else None))
    limitations = [
        f"Covers only URLs reachable from the homepage and sitemap within the limits of this crawl "
        f"(max {j.max_pages} pages, depth {j.max_depth}); pages not crawled were not evaluated.",
        "URLs disallowed by robots.txt were not fetched.",
        "JavaScript is not executed; content rendered only by scripts is not seen.",
        "Fetch times are measured from the crawler's location and are not Core Web Vitals.",
    ]
    if j.urls_dropped:
        limitations.append(f"{j.urls_dropped} discovered URLs were not recorded because the discovery cap was reached.")
    return AuditSummaryOut(
        audit_run_id=run.id, crawl_id=j.id, ruleset_version=run.ruleset_version, pages_fetched=run.pages_fetched,
        created_at=run.created_at, rules=rules,
        provenance=Provenance(source="First-party crawl of a verified domain", method=f"AISVBot crawl, ruleset "
                              f"{run.ruleset_version}", scope=f"{j.base_url or j.hostname} (host only)",
                              collected_from=j.started_at, collected_to=j.finished_at,
                              confidence_label="first_party_verified", sample_size=run.pages_fetched,
                              limitations=limitations))


@router.get("/crawls/{crawl_id}/issues", response_model=Page[IssueOut])
def crawl_issues(crawl_id: uuid.UUID, db: Session = Depends(get_db),
                 ctx: TenantContext = Depends(require(Perm.CLIENT_READ)),
                 rule: str | None = Query(None, max_length=60),
                 status: str | None = Query(None, pattern="^(open|accepted|wont_fix)$"),
                 cursor: uuid.UUID | None = None, limit: int = Query(50, ge=1, le=200)) -> Page[IssueOut]:
    j = _crawl(db, ctx, crawl_id)
    run = _run_for(db, ctx, j)
    stmt = select(CrawlIssue).where(CrawlIssue.tenant_id == ctx.tenant_id, CrawlIssue.audit_run_id == run.id)
    if rule:
        stmt = stmt.where(CrawlIssue.rule_key == rule)
    if status:
        stmt = stmt.where(CrawlIssue.status == status)
    if cursor:
        stmt = stmt.where(CrawlIssue.id > cursor)
    rows = list(db.scalars(stmt.order_by(CrawlIssue.id).limit(limit + 1)))
    return Page[IssueOut](items=[IssueOut.model_validate(i) for i in rows[:limit]],
                          next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None)


@router.patch("/issues/{issue_id}", response_model=IssueOut)
def update_issue(issue_id: uuid.UUID, body: IssueUpdate, request: Request, db: Session = Depends(get_db),
                 ctx: TenantContext = Depends(require(Perm.ISSUE_MANAGE))) -> CrawlIssue:
    i = db.scalar(select(CrawlIssue).where(CrawlIssue.tenant_id == ctx.tenant_id, CrawlIssue.id == issue_id))
    if i is None or not ctx.can_access_client(i.client_id):
        raise not_found("Issue")
    before = {"status": i.status, "note": i.status_note}
    i.status, i.status_note, i.status_changed_by_user_id = body.status, body.note, ctx.user_id
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="issue.updated", object_type="issue",
                 object_id=i.id, client_id=i.client_id,
                 changes=audit.diff(before, {"status": i.status, "note": i.status_note}), request=request)
    return i


@router.get("/audit-rules", response_model=list[RuleOut])
def audit_rules(p: Principal = Depends(authenticated)) -> list[RuleOut]:
    """Methodology: every rule, its denominator and rationale (ruleset version in the header)."""
    return [RuleOut(key=r.key, title=r.title, severity=r.severity, eligible_definition=r.eligible, why=r.why)
            for r in RULES.values()]


