import pytest

import app.crawl.verification as verification
from tests.conftest import signup
from tests.site import TestSite


@pytest.fixture(autouse=True)
def http_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    # The test site has no TLS; production requires HTTPS for meta/file proofs.
    monkeypatch.setattr(verification, "VERIFY_SCHEME", "http")


def _domain() -> tuple[object, str]:
    o = signup("o@a.example", "A")
    cid = o.post("/clients", {"name": "C"}).json()["id"]
    did = o.post(f"/clients/{cid}/domains", {"hostname": "site.example"}).json()["id"]
    return o, did


def test_well_known_file_verification(site: TestSite) -> None:
    o, did = _domain()
    start = o.post(f"/domains/{did}/verification", {"method": "well_known"}).json()  # type: ignore[attr-defined]
    assert start["status"] == "pending" and start["instructions"]["file_contents"].startswith("aisv-")
    fail = o.post(f"/domains/{did}/verification/check").json()  # type: ignore[attr-defined]
    assert fail["status"] == "pending" and "does not contain" in fail["error"]
    site.raw("/.well-known/aisv-verification.txt", (start["instructions"]["file_contents"] + "\n").encode(),
             "text/plain")
    ok = o.post(f"/domains/{did}/verification/check").json()  # type: ignore[attr-defined]
    assert ok["status"] == "verified" and ok["verified_at"]
    actions = [e["action"] for e in o.get("/audit-log?object_type=domain").json()["items"]]  # type: ignore
    assert actions[:3] == ["domain.verified", "domain.verification_failed", "domain.verification_started"]


def test_meta_tag_verification(site: TestSite) -> None:
    o, did = _domain()
    start = o.post(f"/domains/{did}/verification", {"method": "meta_tag"}).json()  # type: ignore[attr-defined]
    token = start["instructions"]["html"].split('content="')[1].split('"')[0]
    original = site.routes["/"]
    site.html("/", f'<html><head><meta name="aisv-site-verification" content="{token}"></head></html>')
    try:
        assert o.post(f"/domains/{did}/verification/check").json()["status"] == "verified"  # type: ignore
    finally:
        site.routes["/"] = original


def test_dns_txt_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    o, did = _domain()
    start = o.post(f"/domains/{did}/verification", {"method": "dns_txt"}).json()  # type: ignore[attr-defined]
    assert start["instructions"]["record_name"] == "_aisv-challenge.site.example"
    records: list[str] = ["unrelated"]
    monkeypatch.setattr(verification, "system_txt", lambda name: records if name.startswith("_aisv-challenge.") else [])
    assert o.post(f"/domains/{did}/verification/check").json()["status"] == "pending"  # type: ignore
    records.append(start["instructions"]["record_value"])
    assert o.post(f"/domains/{did}/verification/check").json()["status"] == "verified"  # type: ignore


def test_token_from_another_workspace_does_not_verify(site: TestSite) -> None:
    a, did_a = _domain()
    tok_a = a.post(f"/domains/{did_a}/verification", {"method": "well_known"}).json()  # type: ignore
    b = signup("o@b.example", "B")
    cid = b.post("/clients", {"name": "C"}).json()["id"]
    did_b = b.post(f"/clients/{cid}/domains", {"hostname": "site.example"}).json()["id"]
    b.post(f"/domains/{did_b}/verification", {"method": "well_known"})
    site.raw("/.well-known/aisv-verification.txt", tok_a["instructions"]["file_contents"].encode(), "text/plain")
    assert a.post(f"/domains/{did_a}/verification/check").json()["status"] == "verified"  # type: ignore
    assert b.post(f"/domains/{did_b}/verification/check").json()["status"] == "pending"


def test_verification_check_is_rate_limited() -> None:
    o, did = _domain()
    o.post(f"/domains/{did}/verification", {"method": "well_known"})  # type: ignore[attr-defined]
    codes = [o.post(f"/domains/{did}/verification/check").status_code for _ in range(11)]  # type: ignore
    assert codes[:10] == [200] * 10 and codes[10] == 429
