from app.services.email import MEMORY_OUTBOX
from tests.conftest import PASSWORD, Api, invite_and_join, last_email_token, signup


def _client(owner: Api, name: str) -> str:
    return str(owner.post("/clients", {"name": name}).json()["id"])


def test_invitation_flow_and_lookup() -> None:
    owner = signup("owner@a.example", "Agency A")
    owner.post("/members/invite", {"email": "New.Person@a.example", "role": "auditor"})
    assert "/invite#token=" in MEMORY_OUTBOX[-1].body  # token only in URL fragment
    token = last_email_token("/invite")
    anon = Api()
    info = anon.get("/invitations/lookup", headers={"X-Invitation-Token": token}).json()
    assert info == {"tenant_name": "Agency A", "email": "new.person@a.example", "role": "Auditor (read-only)",
                    "account_exists": False}
    r = anon.post("/invitations/accept", {"name": "New", "password": PASSWORD}, headers={"X-Invitation-Token": token})
    assert r.status_code == 204
    assert anon.get("/auth/me").json()["active_tenant"]["role"] == "auditor"
    # single use
    assert Api().get("/invitations/lookup", headers={"X-Invitation-Token": token}).status_code == 404


def test_existing_user_must_sign_in_to_accept() -> None:
    owner = signup("owner@a.example", "Agency A")
    other = signup("pat@b.example", "Agency B")
    owner.post("/members/invite", {"email": "pat@b.example", "role": "auditor"})
    token = last_email_token("/invite")
    hdr = {"X-Invitation-Token": token}
    assert Api().post("/invitations/accept", {}, headers=hdr).status_code == 401
    assert Api().post("/invitations/accept", {"name": "x", "password": PASSWORD}, headers=hdr).status_code == 401
    assert other.post("/invitations/accept", {}, headers=hdr).status_code == 204
    me = other.get("/auth/me").json()
    assert me["active_tenant"]["name"] == "Agency A"
    assert {t["name"] for t in me["tenants"]} == {"Agency A", "Agency B"}
    b_id = next(t["id"] for t in me["tenants"] if t["name"] == "Agency B")
    assert other.post("/auth/switch-tenant", {"tenant_id": b_id}).status_code == 204
    assert other.get("/auth/me").json()["active_tenant"]["role"] == "agency_owner"


def test_granted_role_only_sees_assigned_clients() -> None:
    owner = signup("owner@a.example", "A")
    c1, c2 = _client(owner, "One"), _client(owner, "Two")
    viewer = invite_and_join(owner, "v@a.example", "client_viewer", [c1])
    names = [c["name"] for c in viewer.get("/clients").json()["items"]]
    assert names == ["One"]
    assert viewer.get(f"/clients/{c2}").status_code == 404
    assert viewer.get(f"/clients/{c1}/notes").status_code == 403  # internal notes hidden from client roles
    assert viewer.get("/audit-log").status_code == 403
    assert viewer.post("/clients", {"name": "x"}).status_code == 403


def test_granted_role_requires_clients_and_grants_update() -> None:
    owner = signup("owner@a.example", "A")
    c1, c2 = _client(owner, "One"), _client(owner, "Two")
    r = owner.post("/members/invite", {"email": "x@a.example", "role": "seo_analyst", "client_ids": []})
    assert r.status_code == 422
    analyst = invite_and_join(owner, "an@a.example", "seo_analyst", [c1])
    mid = next(m["id"] for m in owner.get("/members").json() if m["email"] == "an@a.example")
    assert owner.patch(f"/members/{mid}", {"client_ids": [c2]}).status_code == 200
    assert [c["name"] for c in analyst.get("/clients").json()["items"]] == ["Two"]
    log = owner.get("/audit-log?action=member.updated").json()["items"]
    assert log and "client_ids" in log[0]["changes"]


def test_account_manager_gets_access_to_clients_they_create() -> None:
    owner = signup("owner@a.example", "A")
    c1 = _client(owner, "One")
    am = invite_and_join(owner, "am@a.example", "account_manager", [c1])
    new = am.post("/clients", {"name": "AM Client"})
    assert new.status_code == 201
    assert {c["name"] for c in am.get("/clients").json()["items"]} == {"One", "AM Client"}


def test_only_owner_can_grant_owner_and_last_owner_protected() -> None:
    owner = signup("owner@a.example", "A")
    admin = invite_and_join(owner, "admin@a.example", "agency_admin")
    assert admin.post("/members/invite", {"email": "o2@a.example", "role": "agency_owner"}).status_code == 403
    members = owner.get("/members").json()
    owner_mid = next(m["id"] for m in members if m["role"] == "agency_owner")
    admin_mid = next(m["id"] for m in members if m["role"] == "agency_admin")
    assert admin.patch(f"/members/{owner_mid}", {"role": "auditor"}).status_code == 403
    assert admin.patch(f"/members/{admin_mid}", {"role": "agency_owner"}).status_code == 403
    assert owner.patch(f"/members/{owner_mid}", {"role": "auditor"}).status_code == 409  # last owner
    assert owner.delete(f"/members/{owner_mid}").status_code == 409
    assert owner.patch(f"/members/{admin_mid}", {"role": "agency_owner"}).status_code == 200
    assert owner.patch(f"/members/{owner_mid}", {"role": "agency_admin"}).status_code == 200


def test_removed_member_loses_access_immediately() -> None:
    owner = signup("owner@a.example", "A")
    aud = invite_and_join(owner, "aud@a.example", "auditor")
    assert aud.get("/clients").status_code == 200
    mid = next(m["id"] for m in owner.get("/members").json() if m["email"] == "aud@a.example")
    assert owner.patch(f"/members/{mid}", {"status": "disabled"}).status_code == 200
    assert aud.get("/clients").status_code == 403
    assert owner.delete(f"/members/{mid}").status_code == 204
    assert aud.get("/clients").status_code == 403
    assert owner.get("/audit-log?action=member.removed").json()["items"]


def test_invitation_revocation() -> None:
    owner = signup("owner@a.example", "A")
    inv = owner.post("/members/invite", {"email": "x@a.example", "role": "auditor"}).json()
    token = last_email_token("/invite")
    assert owner.delete(f"/invitations/{inv['id']}").status_code == 204
    assert Api().get("/invitations/lookup", headers={"X-Invitation-Token": token}).status_code == 404
    assert owner.get("/invitations").json() == []
