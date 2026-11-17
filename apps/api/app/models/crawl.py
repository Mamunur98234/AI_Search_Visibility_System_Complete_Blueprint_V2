"""Crawl, page evidence and technical-audit entities (Phase 2). All tenant-owned with RLS."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin


def _fk(col: str, table: str, ondelete: str = "CASCADE") -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", col], [f"{table}.tenant_id", f"{table}.id"], ondelete=ondelete)


JOB_STATUSES = ("queued", "running", "paused", "completed", "cancelled", "failed")


class CrawlJob(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "crawl_jobs"
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    hostname: Mapped[str] = mapped_column(String(253), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    requested_action: Mapped[str | None] = mapped_column(String(10))  # 'pause' | 'cancel'
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    delay_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(300))
    user_agent: Mapped[str] = mapped_column(String(200), nullable=False)
    robots_outcome: Mapped[str | None] = mapped_column(String(30))
    robots_status: Mapped[int | None] = mapped_column(Integer)
    robots_txt: Mapped[str | None] = mapped_column(Text)
    crawl_delay_s: Mapped[float | None] = mapped_column(Float)
    sitemap_urls_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_errored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urls_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urls_dropped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(String(1000))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crawl_jobs_tenant_id_id"),
        _fk("client_id", "clients"),
        _fk("domain_id", "domains"),
        CheckConstraint("status IN ('queued','running','paused','completed','cancelled','failed')", name="status"),
        CheckConstraint("requested_action IS NULL OR requested_action IN ('pause','cancel')", name="requested_action"),
        CheckConstraint("max_pages BETWEEN 1 AND 5000 AND max_depth BETWEEN 0 AND 20 AND delay_ms >= 0",
                        name="limits"),
        Index("ix_crawl_jobs_tenant_domain_created", "tenant_id", "domain_id", "created_at"),
    )


class CrawlPage(IdMixin, TenantMixin, Base):
    """One URL in a crawl: queued, fetched, skipped (with reason) or errored. Fetched rows hold evidence."""

    __tablename__ = "crawl_pages"
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # seed | link | sitemap
    state: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")
    skip_reason: Mapped[str | None] = mapped_column(String(40))
    error_detail: Mapped[str | None] = mapped_column(String(500))
    status_code: Mapped[int | None] = mapped_column(Integer)
    final_url: Mapped[str | None] = mapped_column(Text)
    redirect_chain: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    content_type: Mapped[str | None] = mapped_column(String(120))
    bytes: Mapped[int | None] = mapped_column(Integer)
    fetch_ms: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str | None] = mapped_column(Text)
    meta_description: Mapped[str | None] = mapped_column(Text)
    meta_robots: Mapped[str | None] = mapped_column(String(300))
    x_robots_tag: Mapped[str | None] = mapped_column(String(300))
    canonical: Mapped[str | None] = mapped_column(Text)
    h1: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    h2_count: Mapped[int | None] = mapped_column(Integer)
    lang: Mapped[str | None] = mapped_column(String(40))
    word_count: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    jsonld: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    is_indexable: Mapped[bool | None] = mapped_column(Boolean)
    in_sitemap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crawl_pages_tenant_id_id"),
        UniqueConstraint("tenant_id", "crawl_job_id", "url_hash"),
        _fk("crawl_job_id", "crawl_jobs"),
        CheckConstraint("state IN ('queued','fetched','skipped','error')", name="state"),
        CheckConstraint("source IN ('seed','link','sitemap')", name="source"),
        Index("ix_crawl_pages_queue", "tenant_id", "crawl_job_id", "state", "depth"),
    )


class CrawlLink(IdMixin, TenantMixin, Base):
    __tablename__ = "crawl_links"
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    to_url: Mapped[str] = mapped_column(Text, nullable=False)
    to_url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    nofollow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    anchor_text: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (
        _fk("crawl_job_id", "crawl_jobs"),
        _fk("from_page_id", "crawl_pages"),
        Index("ix_crawl_links_target", "tenant_id", "crawl_job_id", "to_url_hash"),
    )


class SitemapEntry(IdMixin, TenantMixin, Base):
    __tablename__ = "sitemap_entries"
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sitemap_url: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lastmod: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (
        _fk("crawl_job_id", "crawl_jobs"),
        Index("ix_sitemap_entries_job_hash", "tenant_id", "crawl_job_id", "url_hash"),
    )


class AuditRun(IdMixin, TenantMixin, Base):
    __tablename__ = "audit_runs"
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(40), nullable=False)
    pages_fetched: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_audit_runs_tenant_id_id"),
        UniqueConstraint("tenant_id", "crawl_job_id"),
        _fk("crawl_job_id", "crawl_jobs"),
        _fk("client_id", "clients"),
    )


class AuditRuleResult(IdMixin, TenantMixin, Base):
    """Per-rule denominator and numerator. eligible_count = 0 means 'no data', never a 0% rate."""

    __tablename__ = "audit_rule_results"
    audit_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rule_key: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    eligible_count: Mapped[int] = mapped_column(Integer, nullable=False)
    affected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "audit_run_id", "rule_key"),
        _fk("audit_run_id", "audit_runs"),
        CheckConstraint("affected_count <= eligible_count AND affected_count >= 0", name="counts"),
    )


class CrawlIssue(IdMixin, TenantMixin, Base):
    __tablename__ = "crawl_issues"
    audit_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rule_key: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    crawl_page_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open")
    status_note: Mapped[str | None] = mapped_column(String(1000))
    status_changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    __table_args__ = (
        _fk("audit_run_id", "audit_runs"),
        _fk("client_id", "clients"),
        _fk("crawl_page_id", "crawl_pages", ondelete="NO ACTION"),
        CheckConstraint("status IN ('open','accepted','wont_fix')", name="status"),
        CheckConstraint("severity IN ('high','medium','low','info')", name="severity"),
        Index("ix_crawl_issues_run_rule", "tenant_id", "audit_run_id", "rule_key"),
    )
