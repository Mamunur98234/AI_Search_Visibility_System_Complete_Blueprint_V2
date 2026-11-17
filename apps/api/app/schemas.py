import ipaddress
import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.permissions import ROLE_KEYS
from app.core.security import MIN_PASSWORD_LENGTH

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
Password = Annotated[str, StringConstraints(min_length=MIN_PASSWORD_LENGTH, max_length=256)]
RoleKey = Literal[
    "agency_owner", "agency_admin", "account_manager", "seo_analyst", "content_editor",
    "technical_implementer", "client_admin", "client_viewer", "auditor",
]
assert set(RoleKey.__args__) == set(ROLE_KEYS)  # type: ignore[attr-defined]

_HOST_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def normalize_hostname(value: str) -> str:
    """Bare hostname only: no scheme, path, port, credentials or IP literals."""
    v = value.strip().lower().rstrip(".")
    if not v or any(c in v for c in "/:@?#[] \\"):
        raise ValueError("Enter a bare hostname such as example.com (no scheme, path or port)")
    try:
        ipaddress.ip_address(v)
    except ValueError:
        pass
    else:
        raise ValueError("IP addresses are not allowed; use a hostname")
    try:
        v = v.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Invalid internationalized hostname") from exc
    labels = v.split(".")
    if len(v) > 253 or len(labels) < 2 or not all(_HOST_LABEL.match(lbl) for lbl in labels):
        raise ValueError("Invalid hostname")
    if labels[-1].isdigit():
        raise ValueError("Invalid top-level domain")
    return v


Hostname = Annotated[str, AfterValidator(normalize_hostname)]


def _clean_list(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        v = v.strip()
        if v and v not in out:
            out.append(v)
    return out


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class SignupIn(BaseModel):
    email: EmailStr
    name: Name
    password: Password
    agency_name: Name


class LoginIn(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(max_length=256)]


class MfaCodeIn(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=32)]


class SwitchTenantIn(BaseModel):
    tenant_id: uuid.UUID


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: Annotated[str, StringConstraints(min_length=20, max_length=200)]
    password: Password


class ChangePasswordIn(BaseModel):
    current_password: Annotated[str, StringConstraints(max_length=256)]
    new_password: Password


class TenantSummary(BaseModel):
    id: uuid.UUID
    name: str
    role: str


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    mfa_enabled: bool
    active_tenant: TenantSummary | None
    tenants: list[TenantSummary]
    permissions: list[str]
    scope: str | None


class LoginOut(BaseModel):
    mfa_required: bool


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


# ---------- tenancy ----------
class TenantOut(Out):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime


class TenantUpdate(BaseModel):
    name: Name


class RoleOut(BaseModel):
    key: str
    name: str
    scope: str
    permissions: list[str]


class PermissionOut(BaseModel):
    key: str
    description: str


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    name: str
    role: str
    status: str
    mfa_enabled: bool
    client_ids: list[uuid.UUID]
    created_at: datetime


class InviteIn(BaseModel):
    email: EmailStr
    role: RoleKey
    client_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class InvitationOut(Out):
    id: uuid.UUID
    email: str
    role: str
    client_ids: list[uuid.UUID]
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class InvitationPublicOut(BaseModel):
    tenant_name: str
    email: str
    role: str
    account_exists: bool


class AcceptInviteIn(BaseModel):
    name: Name | None = None
    password: Password | None = None


class MemberUpdate(BaseModel):
    role: RoleKey | None = None
    status: Literal["active", "disabled"] | None = None
    client_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)


class AuditLogOut(Out):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_name: str | None = None
    action: str
    object_type: str
    object_id: uuid.UUID | None
    client_id: uuid.UUID | None
    changes: dict[str, object] | None
    ip: str | None
    request_id: str | None
    created_at: datetime

    @field_validator("ip", mode="before")
    @classmethod
    def _ip(cls, v: object) -> str | None:
        return None if v is None else str(v)


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


# ---------- reference ----------
class MarketOut(Out):
    code: str
    name: str


class LanguageOut(Out):
    code: str
    name: str


# ---------- CRM ----------
ClientStatus = Literal["onboarding", "active", "paused", "archived"]


class ClientIn(BaseModel):
    name: Name
    industry: ShortText | None = None
    website: ShortText | None = None
    status: ClientStatus = "onboarding"
    owner_membership_id: uuid.UUID | None = None
    renewal_date: date | None = None
    business_goals: LongText | None = None


class ClientUpdate(BaseModel):
    name: Name | None = None
    industry: ShortText | None = None
    website: ShortText | None = None
    status: ClientStatus | None = None
    owner_membership_id: uuid.UUID | None = None
    renewal_date: date | None = None
    business_goals: LongText | None = None


class ClientOut(Out):
    id: uuid.UUID
    name: str
    industry: str | None
    website: str | None
    status: str
    owner_membership_id: uuid.UUID | None
    renewal_date: date | None
    business_goals: str | None
    created_at: datetime
    updated_at: datetime


class ContactIn(BaseModel):
    name: Name
    email: EmailStr | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    job_title: ShortText | None = None
    is_approver: bool = False


class ContactUpdate(BaseModel):
    name: Name | None = None
    email: EmailStr | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    job_title: ShortText | None = None
    is_approver: bool | None = None


class ContactOut(Out):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    job_title: str | None
    is_approver: bool
    created_at: datetime


AliasList = Annotated[list[ShortText], AfterValidator(_clean_list), Field(max_length=50)]


class BrandIn(BaseModel):
    name: Name
    aliases: AliasList = Field(default_factory=list)
    description: LongText | None = None


class BrandUpdate(BaseModel):
    name: Name | None = None
    aliases: AliasList | None = None
    description: LongText | None = None


class BrandOut(Out):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    aliases: list[str]
    description: str | None
    created_at: datetime


class DomainIn(BaseModel):
    hostname: Hostname
    is_primary: bool = False


class DomainUpdate(BaseModel):
    is_primary: bool | None = None


class DomainOut(Out):
    id: uuid.UUID
    client_id: uuid.UUID
    hostname: str
    is_primary: bool
    verification_status: str
    verified_at: datetime | None
    created_at: datetime


ProjectStatus = Literal["active", "paused", "completed"]


class ProjectIn(BaseModel):
    name: Name
    goals: LongText | None = None
    status: ProjectStatus = "active"
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _dates(self) -> "ProjectIn":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date")
        return self


class ProjectUpdate(BaseModel):
    name: Name | None = None
    goals: LongText | None = None
    status: ProjectStatus | None = None
    start_date: date | None = None
    end_date: date | None = None


class ProjectOut(Out):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    goals: str | None
    status: str
    start_date: date | None
    end_date: date | None
    created_at: datetime


class ProjectMarketIn(BaseModel):
    market_code: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=2, max_length=2)]
    language_code: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=2,
                                                    max_length=16)]


class ProjectMarketOut(Out):
    id: uuid.UUID
    project_id: uuid.UUID
    market_code: str
    language_code: str


HostList = Annotated[list[Hostname], AfterValidator(_clean_list), Field(max_length=20)]


class CompetitorIn(BaseModel):
    name: Name
    domains: HostList = Field(default_factory=list)
    aliases: AliasList = Field(default_factory=list)


class CompetitorUpdate(BaseModel):
    name: Name | None = None
    domains: HostList | None = None
    aliases: AliasList | None = None


class CompetitorOut(Out):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    domains: list[str]
    aliases: list[str]
    created_at: datetime


class NoteIn(BaseModel):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class NoteOut(Out):
    id: uuid.UUID
    client_id: uuid.UUID
    author_user_id: uuid.UUID | None
    body: str
    created_at: datetime


# ---------- Phase 2: verification, crawls, audits ----------
VerificationMethod = Literal["dns_txt", "meta_tag", "well_known"]


class VerificationStartIn(BaseModel):
    method: VerificationMethod


class VerificationOut(BaseModel):
    domain_id: uuid.UUID
    hostname: str
    status: str
    method: str | None
    instructions: dict[str, str] | None
    checked_at: datetime | None
    verified_at: datetime | None
    error: str | None


class DomainListOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    hostname: str
    is_primary: bool
    verification_status: str
    verified_at: datetime | None
    last_crawl_id: uuid.UUID | None
    last_crawl_status: str | None
    last_crawl_at: datetime | None


class CrawlIn(BaseModel):
    max_pages: int = Field(200, ge=1, le=5000)
    max_depth: int = Field(5, ge=0, le=20)
    delay_ms: int = Field(1000, ge=0, le=10000)


class CrawlOut(Out):
    id: uuid.UUID
    client_id: uuid.UUID
    domain_id: uuid.UUID
    hostname: str
    status: str
    requested_action: str | None
    max_pages: int
    max_depth: int
    delay_ms: int
    base_url: str | None
    user_agent: str
    robots_outcome: str | None
    robots_status: int | None
    crawl_delay_s: float | None
    sitemap_urls_found: int
    pages_fetched: int
    pages_skipped: int
    pages_errored: int
    urls_discovered: int
    urls_dropped: int
    note: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class CrawlDetailOut(CrawlOut):
    state_counts: dict[str, int] = Field(default_factory=dict)
    robots_txt: str | None = None


class CrawlPageOut(Out):
    id: uuid.UUID
    url: str
    depth: int
    source: str
    state: str
    skip_reason: str | None
    error_detail: str | None
    status_code: int | None
    final_url: str | None
    redirect_chain: list[dict[str, object]] | None
    content_type: str | None
    bytes: int | None
    fetch_ms: int | None
    fetched_at: datetime | None
    title: str | None
    meta_description: str | None
    meta_robots: str | None
    x_robots_tag: str | None
    canonical: str | None
    h1: list[str] | None
    h2_count: int | None
    lang: str | None
    word_count: int | None
    jsonld: list[dict[str, object]] | None
    is_indexable: bool | None


class RuleOut(BaseModel):
    key: str
    title: str
    severity: str
    eligible_definition: str
    why: str


class RuleResultOut(RuleOut):
    eligible_count: int
    affected_count: int
    rate: float | None  # null when eligible_count == 0 ("no data"), never 0


class Provenance(BaseModel):
    source: str
    method: str
    scope: str
    collected_from: datetime | None
    collected_to: datetime | None
    confidence_label: str
    sample_size: int
    limitations: list[str]


class AuditSummaryOut(BaseModel):
    audit_run_id: uuid.UUID
    crawl_id: uuid.UUID
    ruleset_version: str
    pages_fetched: int
    created_at: datetime
    rules: list[RuleResultOut]
    provenance: Provenance


class IssueOut(Out):
    id: uuid.UUID
    rule_key: str
    severity: str
    url: str
    crawl_page_id: uuid.UUID | None
    evidence: dict[str, object]
    status: str
    status_note: str | None


class IssueUpdate(BaseModel):
    status: Literal["open", "accepted", "wont_fix"]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
