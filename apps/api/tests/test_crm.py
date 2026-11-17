from tests.conftest import invite_and_join, signup


def test_client_crud_with_audit_trail() -> None:
    owner = signup("owner@a.example", "A")
    c = owner.post("/clients", {"name": "Acme", "industry": "SaaS", "renewal_date": "2027-01-31"}).json()
    assert c["status"] == "onboarding"
    r = owner.patch(f"/clients/{c['id']}", {"status": "active", "industry": "B2B SaaS"})
    assert r.status_code == 200 and r.json()["status"] == "active"
    entries = owner.get(f"/audit-log?object_type=client&object_id={c['id']}").json()["items"]
    assert [e["action"] for e in entries] == ["client.updated", "client.created"]
    assert entries[0]["changes"]["status"] == {"from": "onboarding", "to": "active"}
    assert entries[0]["actor_name"] == "Test User"
    assert owner.patch(f"/clients/{c['id']}", {"name": None}).status_code == 422
    assert owner.delete(f"/clients/{c['id']}").status_code == 204
    assert owner.get("/clients").json()["items"] == []
    assert len(owner.get("/clients?status=archived").json()["items"]) == 1


def test_client_search_escapes_wildcards_and_paginates() -> None:
    owner = signup("owner@a.example", "A")
    for n in ["100% Growth", "Alpha", "Beta", "Gamma"]:
        owner.post("/clients", {"name": n})
    assert [c["name"] for c in owner.get("/clients?q=%25").json()["items"]] == ["100% Growth"]
    page1 = owner.get("/clients?limit=2").json()
    assert len(page1["items"]) == 2 and page1["next_cursor"]
    page2 = owner.get(f"/clients?limit=2&cursor={page1['next_cursor']}").json()
    assert len(page2["items"]) == 2 and page2["next_cursor"] is None
    assert {c["id"] for c in page1["items"]}.isdisjoint({c["id"] for c in page2["items"]})


def test_domains_validation_uniqueness_and_primary() -> None:
    owner = signup("owner@a.example", "A")
    cid = owner.post("/clients", {"name": "Acme"}).json()["id"]
    for bad in ["https://acme.example", "acme.example/path", "127.0.0.1", "localhost", "acme.example:8080",
                "user@acme.example", "-bad.example"]:
        assert owner.post(f"/clients/{cid}/domains", {"hostname": bad}).status_code == 422, bad
    d1 = owner.post(f"/clients/{cid}/domains", {"hostname": "ACME.example.", "is_primary": True}).json()
    assert d1["hostname"] == "acme.example" and d1["verification_status"] == "unverified"
    assert owner.post(f"/clients/{cid}/domains", {"hostname": "acme.example"}).status_code == 409
    d2 = owner.post(f"/clients/{cid}/domains", {"hostname": "bücher.example", "is_primary": True}).json()
    assert d2["hostname"] == "xn--bcher-kva.example"
    primaries = [d for d in owner.get(f"/clients/{cid}/domains").json() if d["is_primary"]]
    assert [d["id"] for d in primaries] == [d2["id"]]


def test_brands_projects_competitors_markets_contacts_notes() -> None:
    owner = signup("owner@a.example", "A")
    cid = owner.post("/clients", {"name": "Acme"}).json()["id"]
    b = owner.post(f"/clients/{cid}/brands", {"name": "Acme", "aliases": [" Acme Inc ", "Acme Inc", ""]}).json()
    assert b["aliases"] == ["Acme Inc"]
    p = owner.post(f"/clients/{cid}/projects", {"name": "AI visibility", "start_date": "2026-01-01"}).json()
    bad = owner.post(f"/clients/{cid}/projects", {"name": "x", "start_date": "2026-02-01", "end_date": "2026-01-01"})
    assert bad.status_code == 422
    comp = owner.post(f"/projects/{p['id']}/competitors", {"name": "Rival", "domains": ["Rival.example"]}).json()
    assert comp["domains"] == ["rival.example"]
    assert owner.post(f"/projects/{p['id']}/markets", {"market_code": "us", "language_code": "EN"}).status_code == 201
    assert owner.post(f"/projects/{p['id']}/markets", {"market_code": "US", "language_code": "en"}).status_code == 409
    assert owner.post(f"/projects/{p['id']}/markets", {"market_code": "ZZ", "language_code": "en"}).status_code == 422
    ct = owner.post(f"/clients/{cid}/contacts", {"name": "Sam", "email": "sam@acme.example", "is_approver": True})
    assert ct.status_code == 201
    assert owner.post(f"/clients/{cid}/contacts", {"name": "Bad", "email": "not-an-email"}).status_code == 422
    n = owner.post(f"/clients/{cid}/notes", {"body": "<script>alert(1)</script>"}).json()
    assert n["body"] == "<script>alert(1)</script>"  # stored verbatim; rendered as text (escaped) by the UI
    assert owner.delete(f"/notes/{n['id']}").status_code == 204
    actions = {e["action"] for e in owner.get("/audit-log?limit=200").json()["items"]}
    assert {"brand.created", "project.created", "competitor.created", "project_market.added", "contact.created",
            "note.created", "note.deleted"} <= actions


def test_analyst_cannot_edit_contacts_but_can_edit_brands() -> None:
    owner = signup("owner@a.example", "A")
    cid = owner.post("/clients", {"name": "Acme"}).json()["id"]
    analyst = invite_and_join(owner, "an@a.example", "seo_analyst", [cid])
    assert analyst.post(f"/clients/{cid}/contacts", {"name": "x"}).status_code == 403
    assert analyst.post(f"/clients/{cid}/brands", {"name": "x"}).status_code == 201
