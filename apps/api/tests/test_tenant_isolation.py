"""Cross-tenant isolation: application layer (IDOR) and database layer (RLS)."""
import uuid
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from tests.conftest import World, build_world, path_values, sample_body
from tests.test_route_permissions import all_routes


@pytest.fixture
def two_worlds() -> tuple[World, World]:
    return build_world("alpha"), build_world("beta")


def _snapshot(w: World) -> dict[str, Any]:
    o = w.owner
    return {
        "client": o.get(f"/clients/{w.client_id}").json(),
        "contacts": o.get(f"/clients/{w.client_id}/contacts").json(),
        "brands": o.get(f"/clients/{w.client_id}/brands").json(),
        "domains": o.get(f"/clients/{w.client_id}/domains").json(),
        "projects": o.get(f"/clients/{w.client_id}/projects").json(),
        "competitors": o.get(f"/projects/{w.project_id}/competitors").json(),
        "markets": o.get(f"/projects/{w.project_id}/markets").json(),
        "notes": o.get(f"/clients/{w.client_id}/notes").json(),
        "members": o.get("/members").json(),
        "invitations": o.get("/invitations").json(),
    }


def test_every_object_route_returns_404_for_foreign_ids(two_worlds: tuple[World, World]) -> None:
    a, b = two_worlds
    before = _snapshot(a)
    checked, leaks = 0, []
    for r in all_routes():
        if "{" not in r.path:
            continue
        for method in r.methods:
            path = r.path.format(**path_values(a, r.path))  # tenant A's IDs ...
            resp = b.owner.request(method, path, json=sample_body(r))  # ... requested by tenant B's OWNER
            checked += 1
            if resp.status_code != 404:
                leaks.append(f"{method} {r.path} -> {resp.status_code} {resp.text[:120]}")
    assert checked >= 25
    assert not leaks, "\n".join(leaks)
    assert _snapshot(a) == before, "Tenant A data changed after tenant B requests"


def test_lists_only_show_own_tenant(two_worlds: tuple[World, World]) -> None:
    a, b = two_worlds
    names = [c["name"] for c in b.owner.get("/clients").json()["items"]]
    assert names == ["beta Client"]
    emails = {m["email"] for m in b.owner.get("/members").json()}
    assert all(e.endswith("@beta.example") for e in emails)
    logs = b.owner.get("/audit-log?limit=200").json()["items"]
    assert logs and all(entry["object_id"] != a.client_id for entry in logs)


def test_cannot_switch_into_foreign_tenant(two_worlds: tuple[World, World]) -> None:
    a, b = two_worlds
    assert b.owner.post("/auth/switch-tenant", {"tenant_id": a.tenant_id}).status_code == 404


def test_invite_cannot_grant_foreign_client(two_worlds: tuple[World, World]) -> None:
    a, b = two_worlds
    r = b.owner.post("/members/invite", {"email": "x@beta.example", "role": "client_viewer",
                                         "client_ids": [a.client_id]})
    assert r.status_code == 422


def test_owner_cannot_be_assigned_foreign_membership(two_worlds: tuple[World, World]) -> None:
    a, b = two_worlds
    r = b.owner.patch(f"/clients/{b.client_id}", {"owner_membership_id": a.member_id})
    assert r.status_code == 422


# ---------------- database layer (RLS) ----------------
@pytest.fixture
def app_engine() -> Any:
    return create_engine(get_settings().database_url)


def test_rls_without_tenant_context_returns_nothing(two_worlds: tuple[World, World], app_engine: Any) -> None:
    with app_engine.connect() as c:
        for table in ["clients", "contacts", "brands", "domains", "projects", "competitors", "notes",
                      "memberships", "invitations", "audit_log", "access_grants", "project_markets", "tenants"]:
            assert c.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0, table  # noqa: S608


def test_rls_with_tenant_context_only_returns_that_tenant(two_worlds: tuple[World, World], app_engine: Any) -> None:
    a, b = two_worlds
    with app_engine.begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": a.tenant_id})
        ids = {str(r[0]) for r in c.execute(text("SELECT tenant_id FROM clients"))}
        assert ids == {a.tenant_id}
        assert c.execute(text("SELECT count(*) FROM clients WHERE id = :id"),
                         {"id": b.client_id}).scalar() == 0


def test_rls_blocks_writing_into_other_tenant(two_worlds: tuple[World, World], app_engine: Any) -> None:
    a, b = two_worlds
    with app_engine.connect() as c:
        c.begin()
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": a.tenant_id})
        with pytest.raises(Exception, match="row-level security"):
            c.execute(text("INSERT INTO clients (id, tenant_id, name, status, created_at, updated_at) "
                           "VALUES (:id, :t, 'evil', 'active', now(), now())"),
                      {"id": str(uuid.uuid4()), "t": b.tenant_id})
        c.rollback()
        c.begin()
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": a.tenant_id})
        updated = c.execute(text("UPDATE clients SET name='pwned' WHERE id = :id"), {"id": b.client_id}).rowcount
        assert updated == 0
        c.rollback()


def test_composite_fk_prevents_cross_tenant_parent(two_worlds: tuple[World, World], owner_engine: Any) -> None:
    """Even the schema owner (bypassing RLS) cannot attach a child to another tenant's parent."""
    a, b = two_worlds
    with owner_engine.connect() as c, pytest.raises(Exception, match="foreign key"):
        c.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": a.tenant_id})
        c.execute(text("INSERT INTO contacts (id, tenant_id, client_id, name, is_approver, created_at, updated_at) "
                       "VALUES (:id, :t, :cid, 'x', false, now(), now())"),
                  {"id": str(uuid.uuid4()), "t": a.tenant_id, "cid": b.client_id})


def test_audit_log_is_append_only_for_app_role(two_worlds: tuple[World, World], app_engine: Any) -> None:
    a, _ = two_worlds
    for stmt in ["UPDATE audit_log SET action = 'tampered'", "DELETE FROM audit_log"]:
        with app_engine.connect() as c:
            c.begin()
            c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": a.tenant_id})
            with pytest.raises(Exception, match="permission denied"):
                c.execute(text(stmt))
            c.rollback()


def test_app_role_cannot_bypass_rls(app_engine: Any) -> None:
    with app_engine.connect() as c:
        row = c.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
        assert row == (False, False)
