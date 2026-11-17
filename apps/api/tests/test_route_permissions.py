"""Every route must declare its access policy, and the role matrix must match core/permissions.py."""
from typing import Any

import pytest
from fastapi.routing import APIRoute

from app.core.permissions import ROLES, role_perms, role_scope
from app.main import ROUTERS
from tests.conftest import World, build_world, invite_and_join, path_values, sample_body

# Routes that only require a signed-in user (no workspace permission) — reviewed explicitly.
AUTHENTICATED_ONLY = {
    "GET /auth/me", "POST /auth/logout", "POST /auth/switch-tenant", "POST /auth/password/change",
    "POST /auth/mfa/setup", "POST /auth/mfa/enable", "POST /auth/mfa/disable", "POST /auth/mfa/verify-login",
    "GET /reference/markets", "GET /reference/languages", "GET /audit-rules",
}
PUBLIC = {
    "GET /healthz", "GET /readyz", "GET /auth/csrf", "POST /auth/signup", "POST /auth/login",
    "POST /auth/password/forgot", "POST /auth/password/reset", "GET /invitations/lookup",
    "POST /invitations/accept",
}


def all_routes() -> list[APIRoute]:
    return [r for router in ROUTERS for r in router.routes if isinstance(r, APIRoute)]


def _markers(dependant: Any) -> tuple[set[str], set[str]]:
    perms: set[str] = set()
    access: set[str] = set()
    stack = [dependant]
    while stack:
        d = stack.pop()
        call = getattr(d, "call", None)
        if call is not None:
            if hasattr(call, "required_permission"):
                perms.add(call.required_permission.value)
            if hasattr(call, "access_marker"):
                access.add(call.access_marker)
        stack.extend(d.dependencies)
    return perms, access


def _key(r: APIRoute) -> list[str]:
    return [f"{m} {r.path}" for m in sorted(r.methods)]


def test_every_route_declares_access() -> None:
    undeclared, unexpected_public, unexpected_auth_only = [], [], []
    for r in all_routes():
        perms, access = _markers(r.dependant)
        for k in _key(r):
            if perms:
                continue
            if "public" in access:
                if k not in PUBLIC:
                    unexpected_public.append(k)
            elif "authenticated" in access:
                if k not in AUTHENTICATED_ONLY:
                    unexpected_auth_only.append(k)
            else:
                undeclared.append(k)
    assert not undeclared, f"Routes with no access declaration: {undeclared}"
    assert not unexpected_public, f"Unreviewed public routes: {unexpected_public}"
    assert not unexpected_auth_only, f"Unreviewed authenticated-only routes: {unexpected_auth_only}"


def test_no_route_declares_two_permissions() -> None:
    for r in all_routes():
        perms, _ = _markers(r.dependant)
        assert len(perms) <= 1, (r.path, perms)


def test_role_scopes_are_valid() -> None:
    assert role_scope("agency_owner") == "tenant"
    assert role_scope("client_viewer") == "granted"
    assert not ({p.value for p in role_perms("client_viewer")} & {"note.read", "audit_log.read", "member.read"})


# Reviewed snapshot. Changing a route's access policy must update this table in the same change.
EXPECTED_ACCESS = {
    "GET /healthz": "public",
    "GET /readyz": "public",
    "GET /auth/csrf": "public",
    "POST /auth/signup": "public",
    "POST /auth/login": "public",
    "POST /auth/mfa/verify-login": "authenticated",
    "POST /auth/logout": "authenticated",
    "GET /auth/me": "authenticated",
    "POST /auth/switch-tenant": "authenticated",
    "POST /auth/password/forgot": "public",
    "POST /auth/password/reset": "public",
    "POST /auth/password/change": "authenticated",
    "POST /auth/mfa/setup": "authenticated",
    "POST /auth/mfa/enable": "authenticated",
    "POST /auth/mfa/disable": "authenticated",
    "GET /tenant": "tenant.read",
    "PATCH /tenant": "tenant.update",
    "GET /roles": "member.read",
    "GET /permissions": "member.read",
    "GET /members": "member.read",
    "PATCH /members/{member_id}": "member.update",
    "DELETE /members/{member_id}": "member.remove",
    "POST /members/invite": "member.invite",
    "GET /invitations": "member.read",
    "DELETE /invitations/{invitation_id}": "member.invite",
    "GET /invitations/lookup": "public",
    "POST /invitations/accept": "public",
    "GET /audit-log": "audit_log.read",
    "GET /clients": "client.read",
    "POST /clients": "client.create",
    "GET /clients/{client_id}": "client.read",
    "PATCH /clients/{client_id}": "client.update",
    "DELETE /clients/{client_id}": "client.delete",
    "GET /clients/{parent_id}/contacts": "client.read",
    "POST /clients/{parent_id}/contacts": "contact.manage",
    "GET /contacts/{item_id}": "client.read",
    "PATCH /contacts/{item_id}": "contact.manage",
    "DELETE /contacts/{item_id}": "contact.manage",
    "GET /clients/{parent_id}/brands": "client.read",
    "POST /clients/{parent_id}/brands": "brand.manage",
    "GET /brands/{item_id}": "client.read",
    "PATCH /brands/{item_id}": "brand.manage",
    "DELETE /brands/{item_id}": "brand.manage",
    "GET /clients/{parent_id}/domains": "client.read",
    "POST /clients/{parent_id}/domains": "domain.manage",
    "GET /domains/{item_id}": "client.read",
    "PATCH /domains/{item_id}": "domain.manage",
    "DELETE /domains/{item_id}": "domain.manage",
    "GET /clients/{parent_id}/projects": "client.read",
    "POST /clients/{parent_id}/projects": "project.manage",
    "GET /projects/{item_id}": "client.read",
    "PATCH /projects/{item_id}": "project.manage",
    "DELETE /projects/{item_id}": "project.manage",
    "GET /projects/{parent_id}/competitors": "client.read",
    "POST /projects/{parent_id}/competitors": "competitor.manage",
    "GET /competitors/{item_id}": "client.read",
    "PATCH /competitors/{item_id}": "competitor.manage",
    "DELETE /competitors/{item_id}": "competitor.manage",
    "GET /projects/{project_id}/markets": "client.read",
    "POST /projects/{project_id}/markets": "project.manage",
    "DELETE /project-markets/{pm_id}": "project.manage",
    "GET /clients/{client_id}/notes": "note.read",
    "POST /clients/{client_id}/notes": "note.manage",
    "DELETE /notes/{note_id}": "note.manage",
    "GET /reference/markets": "authenticated",
    "GET /reference/languages": "authenticated",
    "GET /domains": "client.read",
    "GET /domains/{domain_id}/verification": "client.read",
    "POST /domains/{domain_id}/verification": "domain.verify",
    "POST /domains/{domain_id}/verification/check": "domain.verify",
    "POST /domains/{domain_id}/crawls": "crawl.run",
    "GET /clients/{client_id}/crawls": "client.read",
    "GET /crawls/{crawl_id}": "client.read",
    "POST /crawls/{crawl_id}/pause": "crawl.run",
    "POST /crawls/{crawl_id}/resume": "crawl.run",
    "POST /crawls/{crawl_id}/cancel": "crawl.run",
    "GET /crawls/{crawl_id}/pages": "client.read",
    "GET /crawls/{crawl_id}/audit": "client.read",
    "GET /crawls/{crawl_id}/issues": "client.read",
    "PATCH /issues/{issue_id}": "issue.manage",
    "GET /audit-rules": "authenticated",
}


def test_access_policy_snapshot() -> None:
    actual = {}
    for r in all_routes():
        p, a = _markers(r.dependant)
        for k in _key(r):
            actual[k] = next(iter(p)) if p else sorted(a)[0]
    assert actual == EXPECTED_ACCESS


@pytest.fixture
def world() -> World:
    return build_world("matrix")


@pytest.mark.parametrize("role", [r for r in ROLES if r != "agency_owner"])
def test_role_matrix(world: World, role: str) -> None:
    """For every permission-guarded route: a role lacking the permission gets 403; a role holding it never does."""
    member = invite_and_join(world.owner, f"{role}@matrix.example", role,
                             [world.client_id] if role_scope(role) == "granted" else [])
    perms = {p.value for p in role_perms(role)}
    failures = []
    checked = 0
    for r in all_routes():
        required, _ = _markers(r.dependant)
        if not required:
            continue
        perm = next(iter(required))
        for method in r.methods:
            path = r.path.format(**path_values(world, r.path))
            resp = member.request(method, path, json=sample_body(r))
            checked += 1
            assert resp.status_code != 500, f"{method} {r.path}: {resp.text}"
            denied = resp.status_code == 403
            if (perm in perms) == denied:
                failures.append(f"{method} {r.path} perm={perm} status={resp.status_code}")
    guarded = sum(len(r.methods) for r in all_routes() if _markers(r.dependant)[0])
    assert checked == guarded >= 40
    assert not failures, "\n".join(failures)
