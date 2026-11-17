"""Authentication and authorization dependencies.

Every /api/v1 route must depend on exactly one of: `public`, `authenticated`, `require(perm)`.
tests/test_route_permissions.py fails the build if a route declares none.
"""
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import ColumnElement, select, true
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db, set_db_context
from app.core.permissions import Perm, Scope, role_perms, role_scope
from app.core.security import token_hash
from app.models import AccessGrant, AuthSession, Membership, Tenant, User
from app.models.base import utcnow


@dataclass
class Principal:
    session: AuthSession
    user: User


@dataclass
class TenantContext:
    principal: Principal
    tenant: Tenant
    membership: Membership
    role: str
    perms: frozenset[Perm]
    scope: Scope
    granted_client_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.tenant.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.principal.user.id

    def has(self, perm: Perm) -> bool:
        return perm in self.perms

    def can_access_client(self, client_id: uuid.UUID) -> bool:
        return self.scope == "tenant" or client_id in self.granted_client_ids

    def client_filter(self, column: Any) -> ColumnElement[bool]:
        if self.scope == "tenant":
            return true()
        return column.in_(self.granted_client_ids)  # type: ignore[no-any-return]


def _load_session(request: Request, db: Session) -> Principal | None:
    s = get_settings()
    raw = request.cookies.get(s.session_cookie_name)
    if not raw:
        return None
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(raw)))
    now = utcnow()
    if (sess is None or sess.revoked_at is not None or sess.expires_at <= now
            or sess.last_seen_at + timedelta(minutes=s.session_idle_minutes) <= now):
        return None
    user = db.get(User, sess.user_id)
    if user is None or user.status != "active":
        return None
    if now - sess.last_seen_at > timedelta(minutes=1):
        sess.last_seen_at = now
    set_db_context(db, tenant_id=None, user_id=user.id)
    return Principal(session=sess, user=user)


def _principal(request: Request, db: Session, *, allow_mfa_pending: bool) -> Principal:
    p = _load_session(request, db)
    if p is None:
        raise HTTPException(401, "Authentication required")
    if p.session.mfa_pending and not allow_mfa_pending:
        raise HTTPException(401, "MFA verification required", headers={"X-MFA-Required": "1"})
    request.state.user_id = p.user.id
    return p


def public(request: Request) -> None:
    """Marker: route intentionally requires no authentication."""
    return None


public.access_marker = "public"  # type: ignore[attr-defined]


def authenticated(request: Request, db: Session = Depends(get_db)) -> Principal:
    return _principal(request, db, allow_mfa_pending=False)


authenticated.access_marker = "authenticated"  # type: ignore[attr-defined]


def mfa_pending_ok(request: Request, db: Session = Depends(get_db)) -> Principal:
    return _principal(request, db, allow_mfa_pending=True)


mfa_pending_ok.access_marker = "authenticated"  # type: ignore[attr-defined]


def tenant_context(request: Request, db: Session = Depends(get_db),
                   principal: Principal = Depends(authenticated)) -> TenantContext:
    tid = principal.session.active_tenant_id
    if tid is None:
        raise HTTPException(403, "No active workspace selected")
    set_db_context(db, tenant_id=tid, user_id=principal.user.id)
    tenant = db.scalar(select(Tenant).where(Tenant.id == tid))
    membership = db.scalar(
        select(Membership).where(Membership.tenant_id == tid, Membership.user_id == principal.user.id)
    )
    if tenant is None or membership is None or membership.status != "active" or tenant.status != "active":
        raise HTTPException(403, "No access to this workspace")
    scope = role_scope(membership.role)
    grants: frozenset[uuid.UUID] = frozenset()
    if scope == "granted":
        grants = frozenset(db.scalars(
            select(AccessGrant.client_id).where(AccessGrant.tenant_id == tid,
                                                AccessGrant.membership_id == membership.id)
        ))
    return TenantContext(principal=principal, tenant=tenant, membership=membership, role=membership.role,
                         perms=role_perms(membership.role), scope=scope, granted_client_ids=grants)


def require(perm: Perm) -> Callable[..., TenantContext]:
    def dep(ctx: TenantContext = Depends(tenant_context)) -> TenantContext:
        if not ctx.has(perm):
            raise HTTPException(403, f"Your role does not include the '{perm.value}' permission")
        return ctx

    dep.required_permission = perm  # type: ignore[attr-defined]
    dep.__name__ = f"require_{perm.value.replace('.', '_')}"
    return dep
