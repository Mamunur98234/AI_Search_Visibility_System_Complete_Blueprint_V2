import uuid
from datetime import timedelta

from fastapi import Request, Response
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.net import client_ip
from app.core.security import new_token, token_hash
from app.models import AuthSession
from app.models.base import utcnow


def create_session(
    db: Session, request: Request, response: Response, *, user_id: uuid.UUID,
    active_tenant_id: uuid.UUID | None, mfa_pending: bool,
) -> AuthSession:
    """Always issues a brand-new token (prevents session fixation)."""
    s = get_settings()
    token = new_token()
    now = utcnow()
    sess = AuthSession(
        user_id=user_id, token_hash=token_hash(token), active_tenant_id=active_tenant_id, mfa_pending=mfa_pending,
        created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=s.session_absolute_hours),
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400],
    )
    db.add(sess)
    db.flush()
    set_session_cookie(response, token)
    return sess


def set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name, token, httponly=True, secure=s.is_production, samesite="lax", path="/",
        max_age=s.session_absolute_hours * 3600,
    )


def clear_session_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.session_cookie_name, path="/", secure=s.is_production, httponly=True, samesite="lax")


def revoke(db: Session, sess: AuthSession) -> None:
    sess.revoked_at = utcnow()


def revoke_all_for_user(db: Session, user_id: uuid.UUID, *, except_id: uuid.UUID | None = None) -> None:
    stmt = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if except_id:
        stmt = stmt.where(AuthSession.id != except_id)
    db.execute(stmt.values(revoked_at=utcnow()))


def rotate(db: Session, request: Request, response: Response, old: AuthSession, *,
           active_tenant_id: uuid.UUID | None, mfa_pending: bool = False) -> AuthSession:
    revoke(db, old)
    return create_session(db, request, response, user_id=old.user_id, active_tenant_id=active_tenant_id,
                          mfa_pending=mfa_pending)
