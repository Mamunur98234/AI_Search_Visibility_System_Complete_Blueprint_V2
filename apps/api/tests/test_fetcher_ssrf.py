"""SSRF and resource-exhaustion defences of SafeFetcher (threat model T6, T8)."""
import os

import pytest

from app.crawl.fetcher import FetchError, SafeFetcher, ip_is_public
from tests.site import FAKE_PUBLIC_IP, TestFetcher, TestSite

UA = "AISVBot-test"

BLOCKED = [
    "127.0.0.1", "127.255.255.254", "10.0.0.1", "172.16.0.1", "172.31.255.255", "192.168.1.1",
    "169.254.169.254",  # cloud metadata
    "100.64.0.1",  # CGNAT
    "0.0.0.0", "255.255.255.255", "224.0.0.1", "240.0.0.1",  # noqa: S104
    "192.0.2.1", "198.51.100.1", "203.0.113.1", "198.18.0.1",  # documentation / benchmarking
    "::1", "::", "fe80::1", "fc00::1", "fd12:3456::1", "ff02::1",
    "::ffff:127.0.0.1", "::ffff:169.254.169.254", "::ffff:10.0.0.1",  # IPv4-mapped
    "2002:7f00:1::1",  # 6to4 wrapping 127.0.0.1
    "64:ff9b::a00:1",  # NAT64 wrapping 10.0.0.1
    "2001::1",  # Teredo
    "not-an-ip",
]
ALLOWED = ["8.8.8.8", "1.1.1.1", FAKE_PUBLIC_IP, "2606:4700:4700::1111", "2001:4860:4860::8888"]


@pytest.mark.parametrize("ip", BLOCKED)
def test_non_public_addresses_rejected(ip: str) -> None:
    assert ip_is_public(ip) is False


@pytest.mark.parametrize("ip", ALLOWED)
def test_public_addresses_allowed(ip: str) -> None:
    assert ip_is_public(ip) is True


@pytest.mark.parametrize("ip", ["127.0.0.1", "169.254.169.254", "10.1.2.3", "::1", "::ffff:192.168.0.1"])
def test_hostname_resolving_to_internal_address_is_refused_before_connecting(site: TestSite, ip: str) -> None:
    f = TestFetcher(UA, site, host_map={"evil.test": [ip]})
    with pytest.raises(FetchError) as e:
        f.fetch("http://evil.test/")
    assert e.value.reason == "blocked_ip"
    assert f.targets == []  # no socket was ever opened


def test_any_internal_address_in_answer_set_is_refused(site: TestSite) -> None:
    f = TestFetcher(UA, site, host_map={"mixed.test": [FAKE_PUBLIC_IP, "10.0.0.5"]})
    with pytest.raises(FetchError) as e:
        f.fetch("http://mixed.test/")
    assert e.value.reason == "blocked_ip" and f.targets == []


@pytest.mark.parametrize("url,reason", [
    ("file:///etc/passwd", "blocked_scheme"), ("ftp://site.example/", "blocked_scheme"),
    ("gopher://site.example/", "blocked_scheme"), ("javascript:alert(1)", "blocked_scheme"),
    ("http://site.example:22/", "blocked_port"), ("http://site.example:8080/", "blocked_port"),
    ("http://user:pw@site.example/", "invalid_url"), ("http://site.example@169.254.169.254/", "invalid_url"),
    ("http:///nohost", "invalid_url"), ("http://169.254.169.254/latest/meta-data/", "blocked_ip"),
    ("http://[::1]/", "blocked_ip"), ("http://0x7f000001/", "dns_error"),
])
def test_url_validation(site: TestSite, url: str, reason: str) -> None:
    f = TestFetcher(UA, site)
    with pytest.raises(FetchError) as e:
        f.fetch(url)
    assert e.value.reason == reason
    assert f.targets == []


def test_redirect_to_metadata_service_is_blocked(site: TestSite) -> None:
    site.redirect("/to-metadata", "http://169.254.169.254/latest/meta-data/iam/")
    f = TestFetcher(UA, site)
    with pytest.raises(FetchError) as e:
        f.fetch("http://site.example/to-metadata")
    assert e.value.reason == "blocked_ip"
    assert f.targets == [(FAKE_PUBLIC_IP, 80)]  # only the first, validated hop connected


def test_redirect_to_internal_hostname_is_blocked(site: TestSite) -> None:
    site.redirect("/to-internal", "http://intranet.test/admin")
    f = TestFetcher(UA, site, host_map={"intranet.test": ["192.168.0.10"]})
    with pytest.raises(FetchError) as e:
        f.fetch("http://site.example/to-internal")
    assert e.value.reason == "blocked_ip"


def test_dns_rebinding_cannot_swap_address_between_check_and_connect(site: TestSite) -> None:
    """Resolution happens once per hop and the socket goes to that validated address."""
    answers = iter([[FAKE_PUBLIC_IP], ["127.0.0.1"]])

    class Rebinding(TestFetcher):
        def _resolve(self, host: str) -> list[str]:
            return next(answers)

    site.redirect("/rebind", "http://rebind.example/second")
    f = Rebinding(UA, site)
    with pytest.raises(FetchError) as e:
        f.fetch("http://rebind.example/rebind")
    assert e.value.reason == "blocked_ip"
    assert f.resolutions == 2 and f.targets == [(FAKE_PUBLIC_IP, 80)]


def test_redirect_out_of_scope_is_reported(site: TestSite) -> None:
    site.redirect("/away", "https://other.example/")
    f = TestFetcher(UA, site)
    with pytest.raises(FetchError) as e:
        f.fetch("http://site.example/away", in_scope=lambda u: "//site.example/" in u)
    assert e.value.reason == "redirect_out_of_scope"


def test_redirect_loop_is_capped(site: TestSite) -> None:
    site.redirect("/loop-a", "/loop-b")
    site.redirect("/loop-b", "/loop-a")
    with pytest.raises(FetchError) as e:
        TestFetcher(UA, site).fetch("http://site.example/loop-a")
    assert e.value.reason == "too_many_redirects"


def test_oversized_body_is_aborted(site: TestSite) -> None:
    site.raw("/big", b"a" * 300_000, "text/html")
    with pytest.raises(FetchError) as e:
        TestFetcher(UA, site, max_bytes=100_000).fetch("http://site.example/big")
    assert e.value.reason == "too_large"


def test_compression_bomb_is_aborted_on_decoded_size(site: TestSite) -> None:
    site.gzip_bomb("/bomb", 20 * 1024 * 1024)  # ~20 KB on the wire, 20 MB decoded
    with pytest.raises(FetchError) as e:
        TestFetcher(UA, site, max_bytes=1024 * 1024).fetch("http://site.example/bomb")
    assert e.value.reason == "too_large"


def test_slow_response_times_out(site: TestSite) -> None:
    site.slow("/slow", 2.0)
    with pytest.raises(FetchError) as e:
        TestFetcher(UA, site, read_timeout=0.3).fetch("http://site.example/slow")
    assert e.value.reason == "timeout"


def test_environment_proxies_are_ignored(site: TestSite, monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        monkeypatch.setenv(var, "http://127.0.0.1:9")  # would fail if honoured
    res = TestFetcher(UA, site).fetch("http://site.example/")
    assert res.status == 200 and os.environ["HTTP_PROXY"]


def test_identifies_itself_and_sends_correct_host(site: TestSite) -> None:
    site.raw("/ua", b"ok", "text/plain")
    ua = "Mozilla/5.0 (compatible; AISVBot/0.2; +https://x.example/bot)"
    assert TestFetcher(ua, site).fetch("http://site.example/ua").status == 200
    sent = next(h for path, h in reversed(site.requests) if path == "/ua")
    assert sent["user-agent"] == ua
    assert sent["host"] == "site.example"  # Host header is the hostname even though the socket used the pinned IP


def test_production_fetcher_has_no_test_hooks_enabled() -> None:
    f = SafeFetcher(UA)
    assert f.ip_allowed is ip_is_public
    assert f.allowed_ports == {80, 443}
    assert f._target("8.8.8.8", 443) == ("8.8.8.8", 443)
