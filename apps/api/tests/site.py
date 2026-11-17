"""A local HTTP test website plus a SafeFetcher subclass that reaches it.

TestFetcher keeps the PRODUCTION address policy (ip_is_public) and all URL/redirect/size checks. Hostnames
ending in `.example` resolve to a public documentation-free address (93.184.215.14) that is never actually
contacted: only the final socket target is redirected to 127.0.0.1:<port>. Any other hostname resolves via
the supplied map (used by SSRF tests to return private addresses, which must be refused before connecting).
"""
from __future__ import annotations

import contextlib
import gzip
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from app.crawl.fetcher import SafeFetcher

FAKE_PUBLIC_IP = "93.184.215.14"
Route = tuple[int, dict[str, str], bytes] | Callable[[], tuple[int, dict[str, str], bytes]]


class TestSite:
    __test__ = False  # not a pytest test class

    def __init__(self, port: int = 0) -> None:
        self.routes: dict[str, Route] = {}
        self.hits: list[str] = []
        self.requests: list[tuple[str, dict[str, str]]] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                site.hits.append(self.path)
                site.requests.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
                route = site.routes.get(self.path)
                if route is None:
                    status, headers, body = 404, {"Content-Type": "text/html"}, b"<html><title>Not found</title></html>"
                else:
                    status, headers, body = route() if callable(route) else route
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                if "Content-Length" not in headers:
                    self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    self.wfile.write(body)

            def do_POST(self) -> None:  # noqa: N802
                """Test-harness control endpoint: publish a domain-verification file (simulates the site owner)."""
                if self.path != "/__publish-verification":
                    self.send_response(404)
                    self.end_headers()
                    return
                token = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))[:200]
                site.raw("/.well-known/aisv-verification.txt", token, "text/plain")
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def html(self, path: str, body: str, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self.routes[path] = (status, {"Content-Type": "text/html; charset=utf-8", **(headers or {})}, body.encode())

    def redirect(self, path: str, location: str, status: int = 301) -> None:
        self.routes[path] = (status, {"Location": location, "Content-Type": "text/html"}, b"")

    def raw(self, path: str, body: bytes, content_type: str, status: int = 200, **headers: str) -> None:
        self.routes[path] = (status, {"Content-Type": content_type, **headers}, body)

    def slow(self, path: str, seconds: float) -> None:
        def r() -> tuple[int, dict[str, str], bytes]:
            time.sleep(seconds)
            return 200, {"Content-Type": "text/html"}, b"<html></html>"

        self.routes[path] = r

    def gzip_bomb(self, path: str, decompressed_bytes: int) -> None:
        body = gzip.compress(b"\0" * decompressed_bytes)
        self.routes[path] = (200, {"Content-Type": "text/html", "Content-Encoding": "gzip"}, body)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class TestFetcher(SafeFetcher):
    __test__ = False

    def __init__(self, user_agent: str, site: TestSite, host_map: dict[str, list[str]] | None = None,
                 **kw: Any) -> None:
        self.site = site
        self.host_map = host_map or {}
        self.targets: list[tuple[str, int]] = []
        super().__init__(user_agent, resolver=self._resolve, **kw)

    def _resolve(self, host: str) -> list[str]:
        if host in self.host_map:
            return self.host_map[host]
        if host.endswith(".example"):
            return [FAKE_PUBLIC_IP]
        try:
            import ipaddress

            return [str(ipaddress.ip_address(host))]
        except ValueError:
            return []

    def _target(self, ip: str, port: int) -> tuple[str, int]:
        self.targets.append((ip, port))
        assert ip == FAKE_PUBLIC_IP, f"refused address {ip} must never be connected to"
        return "127.0.0.1", self.site.port


def build_demo_site(s: TestSite) -> None:
    """Deterministic site with known technical issues (expected counts asserted in test_crawl.py)."""
    s.raw("/robots.txt", b"User-agent: *\nDisallow: /private\nSitemap: http://site.example/sitemap.xml\n",
          "text/plain")
    s.html("/", """<!doctype html><html lang="en"><head><title>Home - Example Site</title>
      <meta name="description" content="Welcome to the example site.">
      <link rel="canonical" href="http://site.example/">
      <script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Ex"}</script>
      </head><body><h1>Welcome</h1>
      <a href="/about">About</a> <a href="/blog">Blog</a> <a href="/broken">Broken</a>
      <a href="/private/secret">Secret</a> <a href="/redirect1">Old</a> <a href="https://external.example/x">Ext</a>
      <a href="mailto:a@b.example">Mail</a> <a href="/about#team">Team</a> <a href="/image.png">Img</a>
      <a href="http://site.example:8080/other-port">Port</a>
      <script>document.title = "pwned"</script></body></html>""")
    s.html("/about", """<html><head><title>About</title><link rel="canonical" href="/about"></head>
      <body><h1>About us</h1><h1>Team</h1><a href="/">Home</a><a href="/blog">Blog</a></body></html>""")
    s.html("/blog", """<html lang="en"><head><title>Home - Example Site</title>
      <meta name="description" content="Welcome to the example site.">
      <link rel="canonical" href="/old-blog">
      <script type="application/ld+json">{"@context": "https://schema.org", "@type": "Blog",}</script>
      </head><body><p>No heading here</p><a href="/blog/post-1">Post 1</a></body></html>""")
    s.html("/blog/post-1", """<html lang="en"><head><title>First post on the example blog</title>
      <meta name="robots" content="noindex, follow"><meta name="description" content="A post.">
      </head><body><h1>Post</h1><a href="/broken">dead link</a></body></html>""")
    s.redirect("/redirect1", "/redirect2")
    s.redirect("/redirect2", "http://site.example/about")
    s.raw("/sitemap.xml", b"""<?xml version="1.0" encoding="UTF-8"?>
      <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>http://site.example/</loc></url><url><loc>http://site.example/about</loc></url>
      <url><loc>http://site.example/old-blog</loc><lastmod>2026-01-01</lastmod></url>
      <url><loc>http://site.example/orphan</loc></url></urlset>""", "application/xml")
    s.html("/orphan", """<html lang="en"><head><title>Orphan page only in the sitemap</title>
      <meta name="description" content="Orphan."><link rel="canonical" href="http://site.example/orphan">
      </head><body><h1>Orphan</h1><a href="/huge">Huge</a></body></html>""")
    s.raw("/huge", b"<html>" + b"x" * (6 * 1024 * 1024) + b"</html>", "text/html")
    s.raw("/image.png", b"\x89PNG\r\n", "image/png")
    s.raw("/private/secret", b"SECRET", "text/html")
    s.html("/.well-known/aisv-verification.txt", "")  # replaced per test


