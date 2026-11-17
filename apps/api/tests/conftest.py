"""Test harness. Requires a PostgreSQL with roles from infra/postgres/init-roles.sql and an
`aisv_test` database. Tests run against the real schema with RLS active (app role), never SQLite."""
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://aisv_app:change-me-app@localhost:5432/aisv_test")
os.environ.setdefault("MIGRATION_DATABASE_URL",
                      "postgresql+psycopg://aisv_owner:change-me-owner@localhost:5432/aisv_test")
os.environ["EMAIL_BACKEND"] = "memory"
os.environ["REDIS_URL"] = ""
os.environ.setdefault("ENCRYPTION_KEYS", Fernet.generate_key().decode())
os.environ["ALLOWED_ORIGINS"] = "http://testserver"
os.environ["ALLOW_SIGNUP"] = "true"

import logging  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.email import MEMORY_OUTBOX  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "correct horse battery staple"


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> Iterator[None]:
    cfg = Config(os.path.join(HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session")
def owner_engine() -> Any:
    return create_engine(get_settings().migration_database_url)


@pytest.fixture(autouse=True)
def _clean(owner_engine: Any) -> Iterator[None]:
    with owner_engine.begin() as c:
        c.execute(text(
            "TRUNCATE notes, competitors, project_markets, projects, domains, brands, contacts, access_grants, "
            "clients, invitations, audit_log, memberships, sessions, password_reset_tokens, access_events, "
            "users, tenants CASCADE"))
    ratelimit.set_backend(None)
    MEMORY_OUTBOX.clear()
    yield


class Api:
    """A browser-like client: own cookie jar, CSRF header handled automatically."""

    def __init__(self) -> None:
        self.c = TestClient(app, base_url="http://testserver")
        self.csrf = self.c.get("/api/v1/auth/csrf").json()["csrf_token"]

    def _h(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {"X-CSRF-Token": self.csrf}
        h.update(extra or {})
        return h

    def get(self, path: str, **kw: Any) -> Any:
        return self.c.get(f"/api/v1{path}", **kw)

    def post(self, path: str, json: Any = None, headers: dict[str, str] | None = None) -> Any:
        return self.c.post(f"/api/v1{path}", json=json, headers=self._h(headers))

    def patch(self, path: str, json: Any = None) -> Any:
        return self.c.patch(f"/api/v1{path}", json=json, headers=self._h())

    def delete(self, path: str) -> Any:
        return self.c.delete(f"/api/v1{path}", headers=self._h())

    def request(self, method: str, path: str, json: Any = None, headers: dict[str, str] | None = None) -> Any:
        return self.c.request(method, f"/api/v1{path}", json=json, headers=self._h(headers))


def signup(email: str, agency: str, name: str = "Test User") -> Api:
    api = Api()
    r = api.post("/auth/signup", {"email": email, "name": name, "password": PASSWORD, "agency_name": agency})
    assert r.status_code == 201, r.text
    return api


def last_email_token(marker: str) -> str:
    body = MEMORY_OUTBOX[-1].body
    return body.split(f"{marker}#token=")[1].split()[0]


def invite_and_join(owner: Api, email: str, role: str, client_ids: list[str] | None = None) -> Api:
    r = owner.post("/members/invite", {"email": email, "role": role, "client_ids": client_ids or []})
    assert r.status_code == 201, r.text
    token = last_email_token("/invite")
    member = Api()
    r = member.post("/invitations/accept", {"name": email.split("@")[0], "password": PASSWORD},
                    headers={"X-Invitation-Token": token})
    assert r.status_code == 204, r.text
    return member


@dataclass
class World:
    """A fully populated tenant used by isolation and permission tests."""

    owner: Api
    tenant_id: str
    client_id: str
    contact_id: str
    brand_id: str
    domain_id: str
    project_id: str
    competitor_id: str
    pm_id: str
    note_id: str
    member_id: str  # a non-owner member
    invitation_id: str


def build_world(prefix: str) -> World:
    owner = signup(f"owner@{prefix}.example", f"{prefix} Agency")
    me = owner.get("/auth/me").json()
    c = owner.post("/clients", {"name": f"{prefix} Client"}).json()
    cid = c["id"]
    contact = owner.post(f"/clients/{cid}/contacts", {"name": "Pat Contact", "email": f"pat@{prefix}.example"}).json()
    brand = owner.post(f"/clients/{cid}/brands", {"name": f"{prefix} Brand", "aliases": ["Alias"]}).json()
    domain = owner.post(f"/clients/{cid}/domains", {"hostname": f"www.{prefix}.example", "is_primary": True}).json()
    project = owner.post(f"/clients/{cid}/projects", {"name": "Main"}).json()
    comp = owner.post(f"/projects/{project['id']}/competitors", {"name": "Rival", "domains": ["rival.example"]}).json()
    pm = owner.post(f"/projects/{project['id']}/markets", {"market_code": "US", "language_code": "en"}).json()
    note = owner.post(f"/clients/{cid}/notes", {"body": "internal note"}).json()
    invite_and_join(owner, f"analyst@{prefix}.example", "seo_analyst", [cid])
    members = owner.get("/members").json()
    member_id = next(m["id"] for m in members if m["role"] == "seo_analyst")
    inv = owner.post("/members/invite", {"email": f"pending@{prefix}.example", "role": "auditor"}).json()
    return World(owner=owner, tenant_id=me["active_tenant"]["id"], client_id=cid, contact_id=contact["id"],
                 brand_id=brand["id"], domain_id=domain["id"], project_id=project["id"], competitor_id=comp["id"],
                 pm_id=pm["id"], note_id=note["id"], member_id=member_id, invitation_id=inv["id"])


# Path-parameter resolution for route-enumerating tests.
def path_values(w: World, path: str) -> dict[str, str]:
    seg = path.split("/")
    v: dict[str, str] = {}
    if "{parent_id}" in path:
        v["parent_id"] = w.client_id if seg[1] == "clients" else w.project_id
    if "{item_id}" in path:
        v["item_id"] = {
            "contacts": w.contact_id, "brands": w.brand_id, "domains": w.domain_id, "projects": w.project_id,
            "competitors": w.competitor_id,
        }[seg[1]]
    for key, val in {"client_id": w.client_id, "project_id": w.project_id, "member_id": w.member_id,
                     "invitation_id": w.invitation_id, "pm_id": w.pm_id, "note_id": w.note_id}.items():
        if f"{{{key}}}" in path:
            v[key] = val
    return v


SAMPLE_BODIES: dict[str, Any] = {
    "ClientIn": {"name": "X"}, "ClientUpdate": {"name": "X2"},
    "ContactIn": {"name": "X"}, "ContactUpdate": {"name": "X2"},
    "BrandIn": {"name": "X"}, "BrandUpdate": {"name": "X2"},
    "DomainIn": {"hostname": f"h{uuid.uuid4().hex[:8]}.example"}, "DomainUpdate": {"is_primary": False},
    "ProjectIn": {"name": "X"}, "ProjectUpdate": {"name": "X2"},
    "CompetitorIn": {"name": "X"}, "CompetitorUpdate": {"name": "X2"},
    "ProjectMarketIn": {"market_code": "GB", "language_code": "en"},
    "NoteIn": {"body": "x"},
    "MemberUpdate": {"status": "active"},
    "InviteIn": {"email": "someone-new@other.example", "role": "auditor"},
    "TenantUpdate": {"name": "Renamed"},
}


def sample_body(route: Any) -> Any:
    body = route.body_field
    if body is None:
        return None
    name = body.field_info.annotation.__name__ if hasattr(body.field_info, "annotation") else body.type_.__name__
    if name == "DomainIn":
        return {"hostname": f"h{uuid.uuid4().hex[:8]}.example"}
    return SAMPLE_BODIES[name]
