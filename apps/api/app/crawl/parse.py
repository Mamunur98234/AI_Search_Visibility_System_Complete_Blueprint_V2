"""Non-executing HTML extraction (stdlib html.parser). Crawled content is untrusted data: we extract
bounded plain-text fields only; markup is never stored or rendered, scripts are never run."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit

_WS = re.compile(r"\s+")
_SKIP_TEXT = {"script", "style", "noscript", "template", "svg", "head"}
MAX_LINKS = 2000
MAX_JSONLD_BLOCKS = 20


def clean_text(value: str, limit: int) -> str:
    """Collapse whitespace, drop control/format characters (incl. bidi overrides), cap length."""
    value = "".join(ch for ch in value if unicodedata.category(ch)[0] != "C" or ch in "\t\n ")
    return _WS.sub(" ", value).strip()[:limit]


def normalize_url(url: str, base: str | None = None) -> str | None:
    """Absolute http(s) URL without fragment, lowercase scheme/host, default port removed."""
    try:
        absolute = urljoin(base, url.strip()) if base else url.strip()
        absolute, _ = urldefrag(absolute)
        p = urlsplit(absolute)
    except ValueError:
        return None
    scheme = p.scheme.lower()
    if scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        return None
    host = p.hostname.lower().rstrip(".")
    try:
        port = p.port
    except ValueError:
        return None
    netloc = host if port in (None, 80 if scheme == "http" else 443) else f"{host}:{port}"
    path = p.path or "/"
    out = urlunsplit((scheme, netloc, path, p.query, ""))
    return out if len(out) <= 2048 else None


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


@dataclass
class Link:
    url: str
    nofollow: bool
    anchor: str


@dataclass
class ParsedPage:
    title: str | None = None
    meta_description: str | None = None
    meta_robots: str | None = None
    canonical: str | None = None
    lang: str | None = None
    h1: list[str] = field(default_factory=list)
    h2_count: int = 0
    links: list[Link] = field(default_factory=list)
    jsonld: list[dict[str, Any]] = field(default_factory=list)
    verification_tokens: list[str] = field(default_factory=list)
    word_count: int = 0
    content_hash: str = ""


class _Extractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.page = ParsedPage()
        self._stack: list[str] = []
        self._title: list[str] | None = None
        self._h1: list[str] | None = None
        self._anchor: tuple[str, bool, list[str]] | None = None
        self._jsonld: list[str] | None = None
        self._text: list[str] = []
        self._title_done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag not in ("meta", "link", "br", "img", "input", "hr", "base", "source", "area", "wbr"):
            self._stack.append(tag)
        if tag == "html" and a.get("lang"):
            self.page.lang = clean_text(a["lang"], 40)
        elif tag == "base" and a.get("href"):
            nb = normalize_url(a["href"], self.base)
            if nb:
                self.base = nb
        elif tag == "title" and not self._title_done:
            self._title = []
        elif tag == "meta":
            name = a.get("name", "").lower()
            content = a.get("content", "")
            if name == "description" and self.page.meta_description is None:
                self.page.meta_description = clean_text(content, 2000)
            elif name in ("robots", "aisvbot"):
                prev = self.page.meta_robots
                self.page.meta_robots = clean_text(f"{prev}, {content}" if prev else content, 300)
            elif name == "aisv-site-verification":
                self.page.verification_tokens.append(clean_text(content, 100))
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split() and self.page.canonical is None:
            self.page.canonical = normalize_url(a.get("href", ""), self.base) or clean_text(a.get("href", ""), 500)
        elif tag == "h1":
            self._h1 = []
        elif tag == "h2":
            self.page.h2_count += 1
        elif tag == "a" and a.get("href") and len(self.page.links) < MAX_LINKS:
            target = normalize_url(a["href"], self.base)
            if target:
                self._anchor = (target, "nofollow" in a.get("rel", "").lower().split(), [])
        elif tag == "script" and a.get("type", "").lower().strip() == "application/ld+json":
            self._jsonld = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass
        if tag == "title" and self._title is not None:
            self.page.title = clean_text("".join(self._title), 1000)
            self._title = None
            self._title_done = True
        elif tag == "h1" and self._h1 is not None:
            self.page.h1.append(clean_text("".join(self._h1), 300))
            self._h1 = None
        elif tag == "a" and self._anchor is not None:
            url, nofollow, text = self._anchor
            self.page.links.append(Link(url=url, nofollow=nofollow, anchor=clean_text("".join(text), 200)))
            self._anchor = None
        elif tag == "script" and self._jsonld is not None:
            if len(self.page.jsonld) < MAX_JSONLD_BLOCKS:
                self.page.jsonld.append(_check_jsonld("".join(self._jsonld)))
            self._jsonld = None

    def handle_data(self, data: str) -> None:
        if self._title is not None:
            self._title.append(data)
        if self._jsonld is not None:
            self._jsonld.append(data)
            return
        if self._h1 is not None:
            self._h1.append(data)
        if self._anchor is not None:
            self._anchor[2].append(data)
        if not any(t in _SKIP_TEXT for t in self._stack):
            self._text.append(data)


def _check_jsonld(raw: str) -> dict[str, Any]:
    """Syntax + minimal structure check. Never promises rich results or AI inclusion."""
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"valid": False, "error": f"JSON syntax error at line {exc.lineno} col {exc.colno}", "types": []}
    items = data if isinstance(data, list) else [data]
    types: list[str] = []
    problems: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            problems.append("top-level item is not an object")
            continue
        graph = it.get("@graph")
        nodes = graph if isinstance(graph, list) else [it]
        if "@context" not in it:
            problems.append("missing @context")
        for n in nodes:
            if isinstance(n, dict):
                t = n.get("@type")
                if t is None:
                    problems.append("node without @type")
                elif isinstance(t, list):
                    types.extend(str(x)[:80] for x in t)
                else:
                    types.append(str(t)[:80])
    return {"valid": not problems, "error": "; ".join(sorted(set(problems)))[:300] or None, "types": types[:30]}


def parse_html(html: str, base_url: str) -> ParsedPage:
    ex = _Extractor(base_url)
    try:
        ex.feed(html)
        ex.close()
    except Exception:  # noqa: BLE001,S110 - malformed markup: keep whatever was extracted
        pass
    text = clean_text(" ".join(ex._text), 2_000_000)
    ex.page.word_count = len(text.split()) if text else 0
    ex.page.content_hash = hashlib.sha256(text.lower().encode()).hexdigest()
    return ex.page
