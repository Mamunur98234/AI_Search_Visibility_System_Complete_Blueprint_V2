import hashlib
import re
import secrets
import uuid
from datetime import timedelta

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import get_db, set_db_context
from app.core.deps import Principal, authenticated, mfa_pending_ok, public
from app.core.ids import uuid7
from app.core.net import client_ip
from app.core.permissions import OWNER_ROLE, role_perms, role_scope
from app.core.security import (
    hash_password,
    new_token,
    password_needs_rehash,
    secret_box,
    token_hash,
    verify_password,
)
from app.models import AccessEvent, Membership, PasswordResetToken, Tenant, User
from app.models.base import utcnow
from app.schemas import (
    ChangePasswordIn,
    ForgotIn,
    LoginIn,
    LoginOut,
    MeOut,
    MfaCodeIn,
    MfaSetupOut,
    RecoveryCodesOut,
    ResetIn,
    SignupIn,
    SwitchTenantIn,
    TenantSummary,
)
from app.services import audit, sessions
from app.services.email import OutgoingEmail, send_email

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Email or password is incorrect"


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _email_key(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()[:32]


def _event(db: Session, request: Request, kind: str, user_id: uuid.UUID | None) -> None:
    db.add(AccessEvent(user_id=user_id, kind=kind, ip=client_ip(request),
                       user_agent=(request.headers.get("user-agent") or "")[:400]))


def _limit(key: str, limit: int, window: int) -> None:
    allowed, _ = ratelimit.hit(key, limit, window)
    if not allowed:
        raise HTTPException(429, "Too many attempts. Please wait and try again.",
                            headers={"Retry-After": str(window)})


def _find_user(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def _first_tenant(db: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    set_db_context(db, tenant_id=None, user_id=user_id)
    return db.scalar(
        select(Membership.tenant_id).join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == user_id, Membership.status == "active", Tenant.status == "active")
        .order_by(Membership.created_at).limit(1)
    )


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "agency"
    return f"{base}-{secrets.token_hex(3)}"


@router.get("/csrf", dependencies=[Depends(public)])
def csrf(request: Request, response: Response) -> dict[str, str]:
    """Issues the double-submit CSRF cookie. The SPA echoes it in the X-CSRF-Token header."""
    s = get_settings()
    token = request.cookies.get(s.csrf_cookie_name) or new_token(24)
    response.set_cookie(s.csrf_cookie_name, token, httponly=False, secure=s.is_production, samesite="strict",
                        path="/")
    return {"csrf_token": token}


@router.post("/signup", status_code=201, response_model=LoginOut, dependencies=[Depends(public)])
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)) -> LoginOut:
    s = get_settings()
    if not s.allow_signup:
        raise HTTPException(403, "Self-service signup is disabled on this deployment")
    _limit(f"signup:ip:{_ip(request)}", 10, 3600)
    if _find_user(db, body.email):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    user = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password),
                password_changed_at=utcnow())
    db.add(user)
    # The id must exist before the RLS context is set (defaults are only applied at flush).
    tenant = Tenant(id=uuid7(), name=body.agency_name, slug=_slugify(body.agency_name))
    try:
        db.flush()
        set_db_context(db, tenant_id=tenant.id, user_id=user.id)
        db.add(tenant)
        db.flush()
        membership = Membership(tenant_id=tenant.id, user_id=user.id, role=OWNER_ROLE)
        db.add(membership)
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "An account with this email already exists. Sign in instead.") from exc
    audit.record(db, tenant_id=tenant.id, actor_user_id=user.id, action="tenant.created", object_type="tenant",
                 object_id=tenant.id, changes={"name": tenant.name}, request=request)
    audit.record(db, tenant_id=tenant.id, actor_user_id=user.id, action="member.added",
                 object_type="membership", object_id=membership.id, changes={"role": OWNER_ROLE}, request=request)
    _event(db, request, "signup", user.id)
    sessions.create_session(db, request, response, user_id=user.id, active_tenant_id=tenant.id, mfa_pending=False)
    return LoginOut(mfa_required=False)


@router.post("/login", response_model=LoginOut, dependencies=[Depends(public)])
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> LoginOut:
    s = get_settings()
    _limit(f"login:ip:{_ip(request)}", s.login_rate_limit_per_ip, s.login_rate_window_seconds)
    acct_key = f"login:acct:{_email_key(body.email)}"
    _limit(acct_key, s.login_rate_limit_per_account, s.login_rate_window_seconds)

    user = _find_user(db, body.email)
    ok = verify_password(user.password_hash if user else None, body.password)
    if not user or not ok or user.status != "active":
        _event(db, request, "login_failed", user.id if user else None)
        db.commit()  # persist the failure event even though we raise
        raise HTTPException(401, GENERIC_LOGIN_ERROR)

    ratelimit.reset(acct_key)
    assert user.password_hash is not None
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    mfa = user.mfa_enabled_at is not None
    tenant_id = _first_tenant(db, user.id)
    sessions.create_session(db, request, response, user_id=user.id, active_tenant_id=tenant_id, mfa_pending=mfa)
    if not mfa:
        user.last_login_at = utcnow()
    _event(db, request, "login_password_ok" if mfa else "login", user.id)
    return LoginOut(mfa_required=mfa)


def _check_mfa_code(db: Session, user: User, code: str) -> bool:
    if not user.mfa_secret_enc:
        return False
    code = code.replace(" ", "").replace("-", "")
    if code.isdigit() and len(code) == 6:
        return bool(pyotp.TOTP(secret_box().decrypt(user.mfa_secret_enc)).verify(code, valid_window=1))
    h = token_hash(code.lower())
    if user.mfa_recovery_hashes and h in user.mfa_recovery_hashes:
        user.mfa_recovery_hashes = [x for x in user.mfa_recovery_hashes if x != h]  # single use
        return True
    return False


@router.post("/mfa/verify-login", response_model=LoginOut)
def mfa_verify_login(body: MfaCodeIn, request: Request, response: Response, db: Session = Depends(get_db),
                     p: Principal = Depends(mfa_pending_ok)) -> LoginOut:
    if not p.session.mfa_pending:
        return LoginOut(mfa_required=False)
    _limit(f"mfa:user:{p.user.id}", 6, 900)
    if not _check_mfa_code(db, p.user, body.code):
        _event(db, request, "mfa_failed", p.user.id)
        db.commit()
        raise HTTPException(401, "Invalid verification code")
    ratelimit.reset(f"mfa:user:{p.user.id}")
    sessions.rotate(db, request, response, p.session, active_tenant_id=p.session.active_tenant_id)
    p.user.last_login_at = utcnow()
    _event(db, request, "login", p.user.id)
    return LoginOut(mfa_required=False)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           p: Principal = Depends(mfa_pending_ok)) -> Response:
    sessions.revoke(db, p.session)
    _event(db, request, "logout", p.user.id)
    sessions.clear_session_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(db: Session = Depends(get_db), p: Principal = Depends(authenticated)) -> MeOut:
    rows = db.execute(
        select(Tenant.id, Tenant.name, Membership.role)
        .join(Membership, Membership.tenant_id == Tenant.id)
        .where(Membership.user_id == p.user.id, Membership.status == "active", Tenant.status == "active")
        .order_by(Tenant.name)
    ).all()
    tenants = [TenantSummary(id=r[0], name=r[1], role=r[2]) for r in rows]
    active = next((t for t in tenants if t.id == p.session.active_tenant_id), None)
    return MeOut(
        id=p.user.id, email=p.user.email, name=p.user.name, mfa_enabled=p.user.mfa_enabled_at is not None,
        active_tenant=active, tenants=tenants,
        permissions=sorted(x.value for x in role_perms(active.role)) if active else [],
        scope=role_scope(active.role) if active else None,
    )


@router.post("/switch-tenant", status_code=204)
def switch_tenant(body: SwitchTenantIn, request: Request, response: Response, db: Session = Depends(get_db),
                  p: Principal = Depends(authenticated)) -> Response:
    ok = db.scalar(
        select(Membership.id).join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == p.user.id, Membership.tenant_id == body.tenant_id,
               Membership.status == "active", Tenant.status == "active")
    )
    if not ok:
        raise HTTPException(404, "Workspace not found")
    sessions.rotate(db, request, response, p.session, active_tenant_id=body.tenant_id)
    response.status_code = 204
    return response


@router.post("/password/forgot", status_code=202, dependencies=[Depends(public)])
def forgot_password(body: ForgotIn, request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    s = get_settings()
    _limit(f"forgot:ip:{_ip(request)}", 10, 3600)
    allowed, _ = ratelimit.hit(f"forgot:acct:{_email_key(body.email)}", 3, 3600)
    user = _find_user(db, body.email)
    if user and user.status == "active" and allowed:
        token = new_token()
        now = utcnow()
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash(token), created_at=now,
                                  expires_at=now + timedelta(minutes=s.password_reset_ttl_minutes)))
        _event(db, request, "password_reset_requested", user.id)
        # Token travels in the URL fragment, so it is never sent to servers or logged in access logs.
        send_email(OutgoingEmail(
            to=user.email, subject="Reset your password",
            body=(f"A password reset was requested for your account.\n\n"
                  f"Reset link (valid {s.password_reset_ttl_minutes} minutes):\n"
                  f"{s.public_web_url}/reset-password#token={token}\n\n"
                  "If you did not request this, you can ignore this email."),
        ))
    # Identical response whether or not the account exists (no enumeration).
    return {"detail": "If an account exists for that email, a reset link has been sent."}


@router.post("/password/reset", status_code=204, dependencies=[Depends(public)])
def reset_password(body: ResetIn, request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    _limit(f"reset:ip:{_ip(request)}", 20, 3600)
    now = utcnow()
    rec = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash(body.token)))
    if rec is None or rec.used_at is not None or rec.expires_at <= now:
        raise HTTPException(400, "This reset link is invalid or has expired")
    user = db.get(User, rec.user_id)
    if user is None or user.status != "active":
        raise HTTPException(400, "This reset link is invalid or has expired")
    rec.used_at = now
    user.password_hash = hash_password(body.password)
    user.password_changed_at = now
    sessions.revoke_all_for_user(db, user.id)
    _event(db, request, "password_reset", user.id)
    sessions.clear_session_cookie(response)
    response.status_code = 204
    return response


@router.post("/password/change", status_code=204)
def change_password(body: ChangePasswordIn, request: Request, response: Response, db: Session = Depends(get_db),
                    p: Principal = Depends(authenticated)) -> Response:
    _limit(f"pwchange:user:{p.user.id}", 10, 900)
    if not verify_password(p.user.password_hash, body.current_password):
        raise HTTPException(400, "Current password is incorrect")
    p.user.password_hash = hash_password(body.new_password)
    p.user.password_changed_at = utcnow()
    sessions.revoke_all_for_user(db, p.user.id, except_id=p.session.id)
    sessions.rotate(db, request, response, p.session, active_tenant_id=p.session.active_tenant_id)
    _event(db, request, "password_changed", p.user.id)
    response.status_code = 204
    return response


@router.post("/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(db: Session = Depends(get_db), p: Principal = Depends(authenticated)) -> MfaSetupOut:
    if p.user.mfa_enabled_at:
        raise HTTPException(409, "MFA is already enabled")
    secret = pyotp.random_base32()
    p.user.mfa_secret_enc = secret_box().encrypt(secret)
    uri = pyotp.TOTP(secret).provisioning_uri(name=p.user.email, issuer_name="AI Search Visibility")
    return MfaSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/enable", response_model=RecoveryCodesOut)
def mfa_enable(body: MfaCodeIn, request: Request, db: Session = Depends(get_db),
               p: Principal = Depends(authenticated)) -> RecoveryCodesOut:
    if p.user.mfa_enabled_at:
        raise HTTPException(409, "MFA is already enabled")
    if not p.user.mfa_secret_enc or not body.code.isdigit() or not _check_mfa_code(db, p.user, body.code):
        raise HTTPException(400, "Invalid verification code")
    codes = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(10)]
    p.user.mfa_recovery_hashes = [token_hash(c.replace("-", "")) for c in codes]
    p.user.mfa_enabled_at = utcnow()
    _event(db, request, "mfa_enabled", p.user.id)
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/mfa/disable", status_code=204)
def mfa_disable(body: MfaCodeIn, request: Request, response: Response, db: Session = Depends(get_db),
                p: Principal = Depends(authenticated)) -> Response:
    if not p.user.mfa_enabled_at:
        raise HTTPException(409, "MFA is not enabled")
    _limit(f"mfa:user:{p.user.id}", 6, 900)
    if not _check_mfa_code(db, p.user, body.code):
        raise HTTPException(400, "Invalid verification code")
    p.user.mfa_secret_enc = None
    p.user.mfa_enabled_at = None
    p.user.mfa_recovery_hashes = None
    _event(db, request, "mfa_disabled", p.user.id)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
