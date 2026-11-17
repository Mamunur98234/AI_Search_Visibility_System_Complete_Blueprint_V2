import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db, set_db_context
from app.core.deps import Principal, TenantContext, _load_session, public, require
from app.core.errors import not_found
from app.core.permissions import OWNER_ROLE, PERMISSION_DESCRIPTIONS, ROLES, Perm, role_perms, role_scope
from app.core.security import hash_password, new_token, token_hash
from app.models import AccessGrant, AuditLog, Client, Invitation, Membership, Tenant, User
from app.models.base import utcnow
from app.schemas import (
    AcceptInviteIn,
    AuditLogOut,
    InvitationOut,
    InvitationPublicOut,
    InviteIn,
    MemberOut,
    MemberUpdate,
    Page,
    PermissionOut,
    RoleOut,
    TenantOut,
    TenantUpdate,
)
from app.services import audit, sessions
from app.services.email import OutgoingEmail, send_email

router = APIRouter(tags=["tenancy"])


# ---------------- tenant ----------------
@router.get("/tenant", response_model=TenantOut)
def get_tenant(ctx: TenantContext = Depends(require(Perm.TENANT_READ))) -> Tenant:
    return ctx.tenant


@router.patch("/tenant", response_model=TenantOut)
def update_tenant(body: TenantUpdate, request: Request, db: Session = Depends(get_db),
                  ctx: TenantContext = Depends(require(Perm.TENANT_UPDATE))) -> Tenant:
    before = {"name": ctx.tenant.name}
    ctx.tenant.name = body.name
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="tenant.updated",
                 object_type="tenant", object_id=ctx.tenant_id, changes=audit.diff(before, {"name": body.name}),
                 request=request)
    return ctx.tenant


# ---------------- roles ----------------
@router.get("/roles", response_model=list[RoleOut])
def list_roles(ctx: TenantContext = Depends(require(Perm.MEMBER_READ))) -> list[RoleOut]:
    return [RoleOut(key=k, name=str(v["name"]), scope=role_scope(k), permissions=sorted(p.value for p in role_perms(k)))
            for k, v in ROLES.items()]


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(ctx: TenantContext = Depends(require(Perm.MEMBER_READ))) -> list[PermissionOut]:
    return [PermissionOut(key=p.value, description=d) for p, d in PERMISSION_DESCRIPTIONS.items()]


# ---------------- members ----------------
def _member_out(db: Session, ctx: TenantContext, m: Membership, u: User) -> MemberOut:
    grants = list(db.scalars(select(AccessGrant.client_id).where(AccessGrant.tenant_id == ctx.tenant_id,
                                                                AccessGrant.membership_id == m.id)))
    return MemberOut(id=m.id, user_id=u.id, email=u.email, name=u.name, role=m.role, status=m.status,
                     mfa_enabled=u.mfa_enabled_at is not None, client_ids=grants, created_at=m.created_at)


def _get_membership(db: Session, ctx: TenantContext, member_id: uuid.UUID) -> tuple[Membership, User]:
    row = db.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                     .where(Membership.tenant_id == ctx.tenant_id, Membership.id == member_id)).first()
    if row is None:
        raise not_found("Member")
    return row[0], row[1]


def _validate_clients(db: Session, ctx: TenantContext, client_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    ids = list(dict.fromkeys(client_ids))
    if not ids:
        return []
    found = set(db.scalars(select(Client.id).where(Client.tenant_id == ctx.tenant_id, Client.id.in_(ids))))
    if found != set(ids) or not all(ctx.can_access_client(c) for c in ids):
        raise HTTPException(422, "One or more clients do not exist in this workspace")
    return ids


def _check_role_assignable(ctx: TenantContext, role: str) -> None:
    if role == OWNER_ROLE and ctx.role != OWNER_ROLE:
        raise HTTPException(403, "Only an Agency Owner can grant the Agency Owner role")


def _active_owner_count(db: Session, tenant_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(Membership).where(
        Membership.tenant_id == tenant_id, Membership.role == OWNER_ROLE, Membership.status == "active")) or 0


@router.get("/members", response_model=list[MemberOut])
def list_members(db: Session = Depends(get_db), ctx: TenantContext = Depends(require(Perm.MEMBER_READ))
                 ) -> list[MemberOut]:
    rows = db.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                      .where(Membership.tenant_id == ctx.tenant_id).order_by(User.name)).all()
    return [_member_out(db, ctx, m, u) for m, u in rows]


@router.patch("/members/{member_id}", response_model=MemberOut)
def update_member(member_id: uuid.UUID, body: MemberUpdate, request: Request, db: Session = Depends(get_db),
                  ctx: TenantContext = Depends(require(Perm.MEMBER_UPDATE))) -> MemberOut:
    m, u = _get_membership(db, ctx, member_id)
    if m.role == OWNER_ROLE and ctx.role != OWNER_ROLE:
        raise HTTPException(403, "Only an Agency Owner can change another owner")
    before = {"role": m.role, "status": m.status}
    if body.role is not None and body.role != m.role:
        _check_role_assignable(ctx, body.role)
        if m.role == OWNER_ROLE and _active_owner_count(db, ctx.tenant_id) <= 1:
            raise HTTPException(409, "A workspace must keep at least one active Agency Owner")
        m.role = body.role
    if body.status is not None and body.status != m.status:
        if body.status == "disabled" and m.role == OWNER_ROLE and _active_owner_count(db, ctx.tenant_id) <= 1:
            raise HTTPException(409, "A workspace must keep at least one active Agency Owner")
        if m.id == ctx.membership.id and body.status == "disabled":
            raise HTTPException(409, "You cannot disable your own membership")
        m.status = body.status
    changes = audit.diff(before, {"role": m.role, "status": m.status})
    if body.client_ids is not None:
        ids = _validate_clients(db, ctx, body.client_ids)
        old = set(db.scalars(select(AccessGrant.client_id).where(AccessGrant.tenant_id == ctx.tenant_id,
                                                                AccessGrant.membership_id == m.id)))
        db.execute(delete(AccessGrant).where(AccessGrant.tenant_id == ctx.tenant_id,
                                             AccessGrant.membership_id == m.id))
        for cid in ids:
            db.add(AccessGrant(tenant_id=ctx.tenant_id, membership_id=m.id, client_id=cid))
        if old != set(ids):
            changes["client_ids"] = {"from": sorted(map(str, old)), "to": sorted(map(str, ids))}
    db.flush()
    if changes:
        audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="member.updated",
                     object_type="membership", object_id=m.id, changes=changes, request=request)
    return _member_out(db, ctx, m, u)


@router.delete("/members/{member_id}", status_code=204)
def remove_member(member_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                  ctx: TenantContext = Depends(require(Perm.MEMBER_REMOVE))) -> Response:
    m, u = _get_membership(db, ctx, member_id)
    if m.role == OWNER_ROLE and (ctx.role != OWNER_ROLE or _active_owner_count(db, ctx.tenant_id) <= 1):
        raise HTTPException(409, "Cannot remove this owner (last owner, or you are not an owner)")
    if m.id == ctx.membership.id:
        raise HTTPException(409, "You cannot remove yourself")
    db.execute(update(Client).where(Client.tenant_id == ctx.tenant_id, Client.owner_membership_id == m.id)
               .values(owner_membership_id=None))
    db.delete(m)
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="member.removed",
                 object_type="membership", object_id=m.id, changes={"email": u.email, "role": m.role},
                 request=request)
    return Response(status_code=204)


# ---------------- invitations ----------------
@router.post("/members/invite", status_code=201, response_model=InvitationOut)
def invite(body: InviteIn, request: Request, db: Session = Depends(get_db),
           ctx: TenantContext = Depends(require(Perm.MEMBER_INVITE))) -> Invitation:
    s = get_settings()
    _check_role_assignable(ctx, body.role)
    email = body.email.lower()
    existing = db.scalar(select(Membership.id).join(User, User.id == Membership.user_id)
                         .where(Membership.tenant_id == ctx.tenant_id, func.lower(User.email) == email))
    if existing:
        raise HTTPException(409, "This person is already a member of the workspace")
    client_ids = _validate_clients(db, ctx, body.client_ids)
    if role_scope(body.role) == "granted" and not client_ids:
        raise HTTPException(422, "This role only sees assigned clients; select at least one client")
    # Revoke previous pending invitations for this email.
    now = utcnow()
    db.execute(update(Invitation).where(Invitation.tenant_id == ctx.tenant_id, func.lower(Invitation.email) == email,
                                        Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None))
               .values(revoked_at=now))
    token = new_token()
    inv = Invitation(tenant_id=ctx.tenant_id, email=email, role=body.role,
                     client_ids=client_ids if role_scope(body.role) == "granted" else [],
                     token_hash=token_hash(token), invited_by_user_id=ctx.user_id, created_at=now,
                     expires_at=now + timedelta(hours=s.invitation_ttl_hours))
    db.add(inv)
    db.flush()
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="member.invited",
                 object_type="invitation", object_id=inv.id,
                 changes={"email": email, "role": body.role, "client_ids": inv.client_ids}, request=request)
    send_email(OutgoingEmail(
        to=email, subject=f"You're invited to {ctx.tenant.name}",
        body=(f"{ctx.principal.user.name} invited you to join {ctx.tenant.name} as {ROLES[body.role]['name']}.\n\n"
              f"Accept (valid {s.invitation_ttl_hours} hours):\n{s.public_web_url}/invite#token={token}\n"),
    ))
    return inv


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(db: Session = Depends(get_db), ctx: TenantContext = Depends(require(Perm.MEMBER_READ))
                     ) -> list[Invitation]:
    return list(db.scalars(select(Invitation).where(
        Invitation.tenant_id == ctx.tenant_id, Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None),
        Invitation.expires_at > utcnow()).order_by(Invitation.created_at.desc())))


@router.delete("/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                      ctx: TenantContext = Depends(require(Perm.MEMBER_INVITE))) -> Response:
    inv = db.scalar(select(Invitation).where(Invitation.tenant_id == ctx.tenant_id, Invitation.id == invitation_id))
    if inv is None or inv.accepted_at or inv.revoked_at:
        raise not_found("Invitation")
    inv.revoked_at = utcnow()
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="invitation.revoked",
                 object_type="invitation", object_id=inv.id, changes={"email": inv.email}, request=request)
    return Response(status_code=204)


def _resolve_invitation(db: Session, token: str) -> tuple[Invitation, Tenant]:
    th = token_hash(token)
    tid = db.scalar(select(func.invitation_tenant(th)))
    if tid is None:
        raise HTTPException(404, "This invitation is invalid, expired or already used")
    set_db_context(db, tenant_id=tid, user_id=None)
    inv = db.scalar(select(Invitation).where(Invitation.tenant_id == tid, Invitation.token_hash == th))
    tenant = db.scalar(select(Tenant).where(Tenant.id == tid))
    if inv is None or tenant is None or tenant.status != "active":
        raise HTTPException(404, "This invitation is invalid, expired or already used")
    return inv, tenant


@router.get("/invitations/lookup", response_model=InvitationPublicOut, dependencies=[Depends(public)])
def lookup_invitation(request: Request, db: Session = Depends(get_db)) -> InvitationPublicOut:
    token = request.headers.get("x-invitation-token", "")
    if not 20 <= len(token) <= 200:
        raise HTTPException(404, "This invitation is invalid, expired or already used")
    inv, tenant = _resolve_invitation(db, token)
    exists = db.scalar(select(User.id).where(func.lower(User.email) == inv.email)) is not None
    return InvitationPublicOut(tenant_name=tenant.name, email=inv.email, role=str(ROLES[inv.role]["name"]),
                               account_exists=exists)


@router.post("/invitations/accept", status_code=204, dependencies=[Depends(public)])
def accept_invitation(body: AcceptInviteIn, request: Request, response: Response,
                      db: Session = Depends(get_db)) -> Response:
    # Invitation tokens travel in a header (never the URL path) so they stay out of access logs.
    token = request.headers.get("x-invitation-token", "")
    if not 20 <= len(token) <= 200:
        raise HTTPException(404, "This invitation is invalid, expired or already used")
    principal: Principal | None = _load_session(request, db)
    inv, tenant = _resolve_invitation(db, token)
    user = db.scalar(select(User).where(func.lower(User.email) == inv.email))
    if user is not None:
        # Existing account: must be signed in as that same account (MFA completed).
        if principal is None or principal.user.id != user.id or principal.session.mfa_pending:
            raise HTTPException(401, "Sign in as the invited email address to accept this invitation")
    else:
        if not body.name or not body.password:
            raise HTTPException(422, "Name and password are required to create your account")
        user = User(email=inv.email, name=body.name, password_hash=hash_password(body.password),
                    password_changed_at=utcnow())
        db.add(user)
        db.flush()
    set_db_context(db, tenant_id=tenant.id, user_id=user.id)
    if db.scalar(select(Membership.id).where(Membership.tenant_id == tenant.id, Membership.user_id == user.id)):
        raise HTTPException(409, "You are already a member of this workspace")
    m = Membership(tenant_id=tenant.id, user_id=user.id, role=inv.role)
    db.add(m)
    db.flush()
    for cid in inv.client_ids:
        if db.scalar(select(Client.id).where(Client.tenant_id == tenant.id, Client.id == cid)):
            db.add(AccessGrant(tenant_id=tenant.id, membership_id=m.id, client_id=cid))
    inv.accepted_at = utcnow()
    audit.record(db, tenant_id=tenant.id, actor_user_id=user.id, action="member.joined",
                 object_type="membership", object_id=m.id, changes={"role": inv.role, "invitation_id": inv.id},
                 request=request)
    if principal is not None and principal.user.id == user.id:
        sessions.rotate(db, request, response, principal.session, active_tenant_id=tenant.id)
    else:
        sessions.create_session(db, request, response, user_id=user.id, active_tenant_id=tenant.id,
                                mfa_pending=False)
    response.status_code = 204
    return response


# ---------------- audit log ----------------
@router.get("/audit-log", response_model=Page[AuditLogOut])
def audit_log(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require(Perm.AUDIT_LOG_READ)),
    object_type: str | None = Query(None, max_length=60),
    object_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: str | None = Query(None, max_length=80),
    cursor: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> Page[AuditLogOut]:
    q = (select(AuditLog, User.name).outerjoin(User, User.id == AuditLog.actor_user_id)
         .where(AuditLog.tenant_id == ctx.tenant_id))
    if object_type:
        q = q.where(AuditLog.object_type == object_type)
    if object_id:
        q = q.where(AuditLog.object_id == object_id)
    if actor_user_id:
        q = q.where(AuditLog.actor_user_id == actor_user_id)
    if action:
        q = q.where(AuditLog.action == action)
    if cursor:
        q = q.where(AuditLog.id < cursor)
    rows = db.execute(q.order_by(AuditLog.id.desc()).limit(limit + 1)).all()
    items = []
    for log, name in rows[:limit]:
        out = AuditLogOut.model_validate(log)
        out.actor_name = name
        items.append(out)
    return Page[AuditLogOut](items=items, next_cursor=str(rows[limit - 1][0].id) if len(rows) > limit else None)

