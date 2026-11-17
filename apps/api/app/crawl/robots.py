"""robots.txt handling (RFC 9309 semantics, conservative where the RFC allows a choice) and sitemaps."""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.robotparser import RobotFileParser

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

ROBOTS_MAX_BYTES = 500 * 1024
ROBOTS_AGENT = "AISVBot"  # product token matched against robots.txt User-agent lines


@dataclass
class RobotsPolicy:
    outcome: str  # parsed | not_found_allow_all | auth_disallow_all | unreachable_disallow_all
    status: int | None
    text: str | None
    crawl_delay: float | None = None
    sitemaps: list[str] = field(default_factory=list)
    _parser: RobotFileParser | None = None

    def allowed(self, url: str) -> bool:
        if self.outcome == "not_found_allow_all":
            return True
        if self.outcome in ("auth_disallow_all", "unreachable_disallow_all") or self._parser is None:
            return False
        return self._parser.can_fetch(ROBOTS_AGENT, url)


def build_policy(status: int | None, text: str | None) -> RobotsPolicy:
    if status is None or status >= 500:
        # RFC 9309 2.3.1.4: unreachable -> assume complete disallow.
        return RobotsPolicy("unreachable_disallow_all", status, None)
    if status in (401, 403):
        # RFC permits crawling on 4xx; we choose the respectful option for auth-protected robots.txt.
        return RobotsPolicy("auth_disallow_all", status, None)
    if status >= 400:
        return RobotsPolicy("not_found_allow_all", status, None)
    body = (text or "")[:ROBOTS_MAX_BYTES]
    rp = RobotFileParser()
    rp.parse(body.splitlines())
    delay = rp.crawl_delay(ROBOTS_AGENT)
    sitemaps = [s.strip() for s in (rp.site_maps() or [])][:20]
    return RobotsPolicy("parsed", status, body, float(delay) if delay is not None else None, sitemaps, rp)


@dataclass
class SitemapDoc:
    urls: list[tuple[str, str | None]]  # (loc, lastmod)
    child_sitemaps: list[str]
    error: str | None = None


def parse_sitemap(xml: bytes, limit: int = 50_000) -> SitemapDoc:
    """defusedxml blocks entity expansion (billion laughs), external entities and DTD retrieval."""
    try:
        root = ElementTree.fromstring(xml, forbid_dtd=True)
    except (ElementTree.ParseError, DefusedXmlException, ValueError) as exc:
        return SitemapDoc([], [], f"invalid sitemap XML: {type(exc).__name__}")

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    urls: list[tuple[str, str | None]] = []
    children: list[str] = []
    kind = local(root.tag)
    for node in root:
        if len(urls) >= limit:
            break
        loc = lastmod = None
        for child in node:
            name = local(child.tag)
            if name == "loc" and child.text:
                loc = child.text.strip()
            elif name == "lastmod" and child.text:
                lastmod = child.text.strip()[:40]
        if not loc:
            continue
        if kind == "sitemapindex":
            children.append(loc)
        else:
            urls.append((loc, lastmod))
    if kind not in ("urlset", "sitemapindex"):
        return SitemapDoc([], [], f"unexpected root element <{kind}>")
    return SitemapDoc(urls, children[:50])
