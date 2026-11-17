import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin


def _parent_fk(col: str, table: str) -> ForeignKeyConstraint:
    """Composite FK guarantees a child row can never reference another tenant's parent."""
    return ForeignKeyConstraint(["tenant_id", col], [f"{table}.tenant_id", f"{table}.id"], ondelete="CASCADE")


class Market(Base):
    """Global reference data (ISO 3166-1 alpha-2)."""

    __tablename__ = "markets"
    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Language(Base):
    """Global reference data (BCP 47 primary tags used by the product)."""

    __tablename__ = "languages"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Client(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "clients"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120))
    website: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="onboarding")
    owner_membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    renewal_date: Mapped[date | None] = mapped_column(Date)
    business_goals: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_clients_tenant_id_id"),
        CheckConstraint("status IN ('onboarding','active','paused','archived')", name="status"),
        ForeignKeyConstraint(["tenant_id", "owner_membership_id"], ["memberships.tenant_id", "memberships.id"],
                             name="fk_clients_owner_membership"),
        Index("ix_clients_tenant_name", "tenant_id", "name"),
    )


class Contact(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contacts"
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    job_title: Mapped[str | None] = mapped_column(String(120))
    is_approver: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (_parent_fk("client_id", "clients"), Index("ix_contacts_tenant_client", "tenant_id", "client_id"))


class Brand(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "brands"
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (_parent_fk("client_id", "clients"), Index("ix_brands_tenant_client", "tenant_id", "client_id"))


class Domain(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "domains"
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    hostname: Mapped[str] = mapped_column(String(253), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Verification workflow arrives in Phase 2; until then every domain is 'unverified'.
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unverified")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        _parent_fk("client_id", "clients"),
        UniqueConstraint("tenant_id", "hostname"),
        CheckConstraint("verification_status IN ('unverified','pending','verified','failed')",
                        name="verification_status"),
        Index("ix_domains_tenant_client", "tenant_id", "client_id"),
    )


class Project(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "projects"
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goals: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_projects_tenant_id_id"),
        _parent_fk("client_id", "clients"),
        CheckConstraint("status IN ('active','paused','completed')", name="status"),
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="dates"),
        Index("ix_projects_tenant_client", "tenant_id", "client_id"),
    )


class ProjectMarket(IdMixin, TenantMixin, Base):
    __tablename__ = "project_markets"
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    market_code: Mapped[str] = mapped_column(String(2), ForeignKey("markets.code"), nullable=False)
    language_code: Mapped[str] = mapped_column(String(16), ForeignKey("languages.code"), nullable=False)
    __table_args__ = (
        _parent_fk("project_id", "projects"),
        UniqueConstraint("tenant_id", "project_id", "market_code", "language_code"),
    )


class Competitor(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "competitors"
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domains: Mapped[list[str]] = mapped_column(ARRAY(String(253)), nullable=False, default=list)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    __table_args__ = (_parent_fk("project_id", "projects"),
                      Index("ix_competitors_tenant_project", "tenant_id", "project_id"))


class Note(IdMixin, TenantMixin, Base):
    """Internal agency note on a client. Not visible to client roles."""

    __tablename__ = "notes"
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (_parent_fk("client_id", "clients"), Index("ix_notes_tenant_client", "tenant_id", "client_id"))
