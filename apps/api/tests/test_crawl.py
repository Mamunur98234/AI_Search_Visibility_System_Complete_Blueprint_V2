"""Crawl + technical audit against the deterministic demo site (tests/conftest.py::build_demo_site)."""
from typing import Any

import pytest
from sqlalchemy import create_engine, text

import app.crawl.crawler as crawler_mod
from app.core.config import get_settings
from tests.conftest import Api, invite_and_join, signup, verify_domain_directly
from tests.site import TestFetcher, TestSite

EXPECTED = {  # rule: (eligible, affected) — derived by hand from the demo site
    "http_4xx": (9, 2), "http_5xx": (9, 0), "redirect_chain": (9, 1), "title_missing": (5, 0),
    "title_length": (5, 1), "title_duplicate": (4, 2), "meta_description_missing": (4, 1),
    "meta_description_duplicate": (3, 2), "h1_missing": (5, 1), "h1_multiple": (5, 1), "canonical_missing": (4, 0),
    "canonical_target_not_200": (4, 1), "noindex": (5, 1), "lang_missing": (5, 1), "broken_internal_link": (4, 2),
    "jsonld_invalid": (2, 1), "sitemap_url_not_200": (4, 1), "indexable_not_in_sitemap": (4, 1),
    "slow_fetch": (9, 0),
}


def _setup(hostname: str = "site.example") -> tuple[Api, str, str, str]:
    o = signup("owner@agency.example", "Agency")
    tid = o.get("/auth/me").json()["active_tenant"]["id"]
    cid = o.post("/clients", {"name": "Client"}).json()["id"]
    did = o.post(f"/clients/{cid}/domains", {"hostname": hostname}).json()["id"]
    return o, tid, cid, did


def _verify(tid: str, did: str) -> None:
    verify_domain_directly(create_engine(get_settings().migration_database_url), tid, did)


def test_unverified_domain_cannot_be_crawled() -> None:
    o, _, _, did = _setup()
    r = o.post(f"/domains/{did}/crawls", {"max_pages": 5, "delay_ms": 0})
    assert r.status_code == 409 and "Verify" in r.json()["detail"]


def test_full_crawl_records_every_url_and_exact_rule_counts(site: TestSite) -> None:
    o, tid, cid, did = _setup()
    _verify(tid, did)
    site.hits.clear()
    crawl = o.post(f"/domains/{did}/crawls", {"max_pages": 50, "delay_ms": 0}).json()
    job = o.get(f"/crawls/{crawl['id']}").json()
    assert job["status"] == "completed", job
    assert job["base_url"] == "http://site.example/"  # HTTPS unavailable on the test site -> HTTP fallback
    assert job["robots_outcome"] == "parsed" and job["sitemap_urls_found"] == 4
    assert job["state_counts"] == {"fetched": 9, "skipped": 1, "error": 1}
    assert "AISVBot" in job["user_agent"]

    pages = {p["url"]: p for p in o.get(f"/crawls/{crawl['id']}/pages?limit=200").json()["items"]}
    assert pages["http://site.example/private/secret"]["skip_reason"] == "robots_disallowed"
    assert "/private/secret" not in site.hits  # robots.txt respected: never requested
    assert pages["http://site.example/huge"]["state"] == "error"
    assert pages["http://site.example/huge"]["skip_reason"] == "too_large"
    assert pages["http://site.example/redirect1"]["status_code"] == 301
    assert pages["http://site.example/redirect1"]["title"] is None  # destination evaluated once, as its own URL
    home = pages["http://site.example/"]
    assert home["title"] == "Home - Example Site"  # inline script never executed
    assert home["jsonld"][0]["valid"] is True and home["jsonld"][0]["types"] == ["Organization"]
    # Out-of-scope links recorded but never fetched.
    for url in ("https://external.example/x", "http://site.example:8080/other-port"):
        assert url not in pages
    assert not any(h.startswith("/other-port") for h in site.hits)

    summary = o.get(f"/crawls/{crawl['id']}/audit").json()
    got = {r["key"]: (r["eligible_count"], r["affected_count"]) for r in summary["rules"]}
    assert got == EXPECTED
    for r in summary["rules"]:
        assert r["rate"] == (r["affected_count"] / r["eligible_count"] if r["eligible_count"] else None)
    prov = summary["provenance"]
    assert prov["confidence_label"] == "first_party_verified" and prov["sample_size"] == 9
    assert any("JavaScript is not executed" in x for x in prov["limitations"])

    broken = o.get(f"/crawls/{crawl['id']}/issues?rule=broken_internal_link").json()["items"]
    assert {i["url"] for i in broken} == {"http://site.example/", "http://site.example/blog/post-1"}
    assert broken[0]["evidence"]["broken_targets"] == [{"url": "http://site.example/broken", "status": 404}]
    canon = o.get(f"/crawls/{crawl['id']}/issues?rule=canonical_target_not_200").json()["items"]
    assert canon[0]["evidence"]["canonical"] == "http://site.example/old-blog"

    actions = {e["action"] for e in o.get("/audit-log?limit=100").json()["items"]}
    assert "crawl.started" in actions


def test_no_data_is_null_not_zero(site: TestSite) -> None:
    site.raw("/robots.txt", b"User-agent: *\nDisallow:\n", "text/plain")
    try:
        o, tid, _, did = _setup()
        _verify(tid, did)
        crawl = o.post(f"/domains/{did}/crawls", {"max_pages": 1, "delay_ms": 0}).json()
        rules = {r["key"]: r for r in o.get(f"/crawls/{crawl['id']}/audit").json()["rules"]}
        assert rules["jsonld_invalid"]["eligible_count"] == 1
        assert rules["sitemap_url_not_200"]["eligible_count"] in (0, 1)
        zero = [r for r in rules.values() if r["eligible_count"] == 0]
        assert zero and all(r["rate"] is None for r in zero)
    finally:
        site.raw("/robots.txt", b"User-agent: *\nDisallow: /private\nSitemap: http://site.example/sitemap.xml\n",
                 "text/plain")


def test_page_cap_and_depth_limit_are_recorded(site: TestSite) -> None:
    o, tid, _, did = _setup()
    _verify(tid, did)
    crawl = o.post(f"/domains/{did}/crawls", {"max_pages": 3, "max_depth": 1, "delay_ms": 0}).json()
    job = o.get(f"/crawls/{crawl['id']}").json()
    assert job["pages_fetched"] + job["pages_errored"] == 3
    skipped = o.get(f"/crawls/{crawl['id']}/pages?state=skipped&limit=200").json()["items"]
    reasons = {p["skip_reason"] for p in skipped}
    assert "page_cap_reached" in reasons


@pytest.mark.parametrize("status,outcome", [(503, "unreachable_disallow_all"), (403, "auth_disallow_all"),
                                            (404, "not_found_allow_all")])
def test_robots_status_semantics(site: TestSite, status: int, outcome: str) -> None:
    site.raw("/robots.txt", b"", "text/plain", status=status)
    try:
        o, tid, _, did = _setup()
        _verify(tid, did)
        site.hits.clear()
        crawl = o.post(f"/domains/{did}/crawls", {"max_pages": 2, "delay_ms": 0}).json()
        job = o.get(f"/crawls/{crawl['id']}").json()
        assert job["robots_outcome"] == outcome and job["status"] == "completed"
        if outcome.endswith("disallow_all"):
            assert job["pages_fetched"] == 0 and "/" not in site.hits
        else:
            assert job["pages_fetched"] == 2
    finally:
        site.raw("/robots.txt", b"User-agent: *\nDisallow: /private\nSitemap: http://site.example/sitemap.xml\n",
                 "text/plain")


def test_crawl_delay_from_robots_is_honoured(site: TestSite, monkeypatch: pytest.MonkeyPatch) -> None:
    site.raw("/robots.txt", b"User-agent: AISVBot\nCrawl-delay: 7\nDisallow: /private\n", "text/plain")
    sleeps: list[float] = []
    real = crawler_mod.run_crawl

    def run(tenant_id: Any, job_id: Any, fetcher_factory: Any = None, sleep: Any = None) -> str:
        return real(tenant_id, job_id, fetcher_factory, sleep=sleeps.append)

    monkeypatch.setattr(crawler_mod, "run_crawl", run)
    try:
        o, tid, _, did = _setup()
        _verify(tid, did)
        crawl = o.post(f"/domains/{did}/crawls", {"max_pages": 3, "delay_ms": 0}).json()
        assert o.get(f"/crawls/{crawl['id']}").json()["crawl_delay_s"] == 7.0
        assert [s for s in sleeps if s > 1] and max(sleeps) <= 7.0
    finally:
        site.raw("/robots.txt", b"User-agent: *\nDisallow: /private\nSitemap: http://site.example/sitemap.xml\n",
                 "text/plain")


def _pause_after(n: int, monkeypatch: pytest.MonkeyPatch, site: TestSite, action: str, tid: str) -> None:
    """Fetcher that asks for pause/cancel (via a separate DB connection, like the API would) after n fetches."""
    owner = create_engine(get_settings().migration_database_url)

    class Interrupting(TestFetcher):
        count = 0

        def fetch(self, url: str, **kw: Any) -> Any:
            Interrupting.count += 1
            if Interrupting.count == n:
                with owner.begin() as c:
                    c.execute(text("SET LOCAL lock_timeout = '5s'"))  # fail fast instead of hanging
                    c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tid})
                    n_rows = c.execute(text("UPDATE crawl_jobs SET requested_action = :a WHERE status = 'running'"),
                                       {"a": action}).rowcount
                    assert n_rows == 1
            return super().fetch(url, **kw)

    monkeypatch.setattr(crawler_mod, "make_fetcher", lambda ua: Interrupting(ua, site))


def test_pause_then_resume_continues_from_persisted_queue(site: TestSite, monkeypatch: pytest.MonkeyPatch) -> None:
    o, tid, _, did = _setup()
    _verify(tid, did)
    _pause_after(4, monkeypatch, site, "pause", tid)
    crawl = o.post(f"/domains/{did}/crawls", {"max_pages": 50, "delay_ms": 0}).json()
    paused = o.get(f"/crawls/{crawl['id']}").json()
    assert paused["status"] == "paused" and paused["state_counts"].get("queued", 0) > 0
    assert o.post(f"/domains/{did}/crawls", {"max_pages": 5, "delay_ms": 0}).status_code == 409  # one active crawl
    monkeypatch.setattr(crawler_mod, "make_fetcher", lambda ua: TestFetcher(ua, site))
    assert o.post(f"/crawls/{crawl['id']}/resume").json()["status"] == "completed"
    done = o.get(f"/crawls/{crawl['id']}").json()
    assert done["state_counts"] == {"fetched": 9, "skipped": 1, "error": 1}  # same as an uninterrupted crawl
    got = {r["key"]: (r["eligible_count"], r["affected_count"]) for r in o.get(f"/crawls/{crawl['id']}/audit")
           .json()["rules"]}
    assert got == EXPECTED


def test_cancel_stops_and_records_remaining_urls(site: TestSite, monkeypatch: pytest.MonkeyPatch) -> None:
    o, tid, _, did = _setup()
    _verify(tid, did)
    _pause_after(3, monkeypatch, site, "cancel", tid)
    crawl = o.post(f"/domains/{did}/crawls", {"max_pages": 50, "delay_ms": 0}).json()
    job = o.get(f"/crawls/{crawl['id']}").json()
    assert job["status"] == "cancelled" and job["finished_at"]
    assert job["state_counts"].get("queued", 0) == 0 and job["state_counts"]["skipped"] >= 1
    assert o.get(f"/crawls/{crawl['id']}/audit").status_code == 404  # no audit for a cancelled crawl
    assert o.post(f"/crawls/{crawl['id']}/resume").status_code == 409


def test_issue_triage_and_client_viewer_read_only(site: TestSite) -> None:
    o, tid, cid, did = _setup()
    _verify(tid, did)
    crawl = o.post(f"/domains/{did}/crawls", {"max_pages": 50, "delay_ms": 0}).json()
    issue = o.get(f"/crawls/{crawl['id']}/issues?rule=noindex").json()["items"][0]
    r = o.patch(f"/issues/{issue['id']}", {"status": "wont_fix", "note": "Intentionally noindex"})
    assert r.status_code == 200 and r.json()["status"] == "wont_fix"
    assert o.get("/audit-log?action=issue.updated").json()["items"]
    viewer = invite_and_join(o, "viewer@client.example", "client_viewer", [cid])
    assert viewer.get(f"/crawls/{crawl['id']}/audit").status_code == 200
    assert viewer.patch(f"/issues/{issue['id']}", {"status": "open"}).status_code == 403
    assert viewer.post(f"/domains/{did}/crawls", {"max_pages": 1, "delay_ms": 0}).status_code == 403


def test_domain_with_crawl_history_cannot_be_deleted(site: TestSite) -> None:
    o, tid, _, did = _setup()
    _verify(tid, did)
    o.post(f"/domains/{did}/crawls", {"max_pages": 1, "delay_ms": 0})
    assert o.delete(f"/domains/{did}").status_code == 409


def test_crawl_limits_validated() -> None:
    o, tid, _, did = _setup()
    _verify(tid, did)
    assert o.post(f"/domains/{did}/crawls", {"max_pages": 100000}).status_code == 422
    assert o.post(f"/domains/{did}/crawls", {"max_pages": 10, "delay_ms": -1}).status_code == 422


def test_host_lock_defers_concurrent_crawls_of_same_host(site: TestSite) -> None:
    from app.crawl import hostlock

    o, tid, _, did = _setup()
    _verify(tid, did)
    assert hostlock.acquire("site.example", "someone-else")
    try:
        crawl = o.post(f"/domains/{did}/crawls", {"max_pages": 2, "delay_ms": 0}).json()
        job = o.get(f"/crawls/{crawl['id']}").json()
        assert job["status"] == "queued" and "another crawl" in job["note"]
    finally:
        hostlock.release("site.example", "someone-else")
