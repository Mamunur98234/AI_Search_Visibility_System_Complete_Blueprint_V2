"""Domain ownership verification. Crawling is only permitted for verified domains.

Methods (the customer publishes a public, per-workspace token):
  dns_txt     TXT record at _aisv-challenge.<host> with value  aisv-verification=<token>
  meta_tag    <meta name="aisv-site-verification" content="<token>"> on https://<host>/
  well_known  https://<host>/.well-known/aisv-verification.txt containing <token>
meta_tag / well_known require HTTPS so the proof cannot be spoofed by a network attacker.
"""
from __future__ import annotations

import secrets
from collections.abc import Callable

from app.crawl.fetcher import FetchError, SafeFetcher
from app.crawl.parse import normalize_url, parse_html

VERIFY_SCHEME = "https"
TXT_LABEL = "_aisv-challenge"
WELL_KNOWN_PATH = "/.well-known/aisv-verification.txt"
METHODS = ("dns_txt", "meta_tag", "well_known")

TxtResolver = Callable[[str], list[str]]


def new_token() -> str:
    return "aisv-" + secrets.token_hex(16)


def instructions(method: str, host: str, token: str) -> dict[str, str]:
    if method == "dns_txt":
        return {"summary": "Add a DNS TXT record, then check. DNS changes can take time to propagate.",
                "record_name": f"{TXT_LABEL}.{host}", "record_type": "TXT",
                "record_value": f"aisv-verification={token}"}
    if method == "meta_tag":
        return {"summary": f"Add this tag inside <head> of {VERIFY_SCHEME}://{host}/ and publish, then check.",
                "html": f'<meta name="aisv-site-verification" content="{token}">'}
    return {"summary": f"Publish a plain-text file at {VERIFY_SCHEME}://{host}{WELL_KNOWN_PATH} "
                       "containing only the token, then check.",
            "url": f"{VERIFY_SCHEME}://{host}{WELL_KNOWN_PATH}", "file_contents": token}


def system_txt(name: str) -> list[str]:
    import dns.exception
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.lifetime = 5.0
    try:
        answer = resolver.resolve(name, "TXT")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except dns.exception.DNSException as exc:
        raise FetchError("dns_error", type(exc).__name__) from exc
    return [b"".join(r.strings).decode("utf-8", "replace") for r in answer]


def check(method: str, host: str, token: str, *, fetcher: SafeFetcher,
          txt_resolver: TxtResolver | None = None) -> tuple[bool, str | None]:
    """Returns (verified, human-readable reason when not verified)."""
    try:
        if method == "dns_txt":
            values = [v.strip() for v in (txt_resolver or system_txt)(f"{TXT_LABEL}.{host}")]
            if f"aisv-verification={token}" in values:
                return True, None
            return False, f"No matching TXT record found at {TXT_LABEL}.{host} ({len(values)} TXT value(s) present)"

        def same_host(url: str) -> bool:
            n = normalize_url(url)
            return n is not None and n.startswith(f"{VERIFY_SCHEME}://{host}/")

        if method == "meta_tag":
            res = fetcher.fetch(f"{VERIFY_SCHEME}://{host}/", in_scope=same_host)
            if res.status != 200:
                return False, f"Homepage returned HTTP {res.status}"
            page = parse_html(res.text(limit=2_000_000), res.final_url)
            if token in page.verification_tokens:
                return True, None
            return False, "Verification meta tag not found on the homepage"
        if method == "well_known":
            res = fetcher.fetch(f"{VERIFY_SCHEME}://{host}{WELL_KNOWN_PATH}", in_scope=same_host, accept="text/plain")
            if res.status != 200:
                return False, f"Verification file returned HTTP {res.status}"
            if res.text(limit=1024).strip().splitlines()[:1] == [token]:
                return True, None
            return False, "Verification file does not contain the expected token"
    except FetchError as exc:
        return False, f"Could not check ({exc.reason}{': ' + exc.detail if exc.detail else ''})"
    return False, "Unknown verification method"
