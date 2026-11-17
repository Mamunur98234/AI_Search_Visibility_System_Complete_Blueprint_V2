"""ASGI entry point for browser end-to-end tests ONLY (never deployed; tests/ is excluded from images).

Identical to app.main:app except outbound fetches use TestFetcher, which keeps the production SSRF policy
but routes the socket to a local demo website, and verification proofs are checked over HTTP because the
local site has no TLS certificate. Production code has no switch that enables any of this.
"""
import os

import app.crawl.crawler as crawler_mod
import app.crawl.verification as verification
import app.routers.crawl as crawl_router
from app.main import app
from tests.site import TestFetcher, TestSite, build_demo_site

site = TestSite(port=int(os.environ.get("E2E_SITE_PORT", "8199")))
build_demo_site(site)


def _factory(ua: str) -> TestFetcher:
    return TestFetcher(ua, site)


crawler_mod.make_fetcher = _factory  # type: ignore[assignment]
crawl_router.make_fetcher = _factory  # type: ignore[assignment]
verification.VERIFY_SCHEME = "http"

__all__ = ["app"]
