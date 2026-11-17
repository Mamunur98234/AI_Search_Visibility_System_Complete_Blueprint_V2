import uuid
from datetime import date, datetime
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.net import client_ip
from app.models import AuditLog

_SECRET_MARKERS = ("password", "token", "secret", "mfa", "recovery", "hash")


def _clean(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: ("[redacted]" if any(m in k.lower() for m in _SECRET_MARKERS) else _clean(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(v) for v in value]
    return value


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {k: {"from": before.get(k), "to": after.get(k)} for k in after if before.get(k) != after.get(k)}


def record(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    object_type: str,
    object_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    changes: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            client_id=client_id,
            changes=_clean(changes) if changes else None,
            ip=client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:400] if request else None,
            request_id=getattr(request.state, "request_id", None) if request else None,
        )
    )
