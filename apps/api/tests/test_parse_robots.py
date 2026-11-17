from app.crawl.parse import normalize_url, parse_html
from app.crawl.robots import build_policy, parse_sitemap


def test_extracts_fields_and_ignores_script_text() -> None:
    p = parse_html("""<html lang="de"><head><base href="https://x.example/sub/">
      <title> Hello
      World </title><meta name="description" content="Desc"><meta name="robots" content="noindex">
      <link rel="canonical" href="page"><script>var t = "lots of words here";</script></head>
      <body><h1>One</h1><h2>a</h2><h2>b</h2><a href="rel">Rel</a><a href="/abs" rel="nofollow">Abs</a>
      <a href="javascript:alert(1)">JS</a><a href="#top">Top</a><p>visible text</p></body></html>""",
                   "https://x.example/start")
    assert p.title == "Hello World" and p.meta_description == "Desc" and p.meta_robots == "noindex"
    assert p.canonical == "https://x.example/sub/page" and p.lang == "de"
    assert p.h1 == ["One"] and p.h2_count == 2
    assert [(lk.url, lk.nofollow) for lk in p.links] == [
        ("https://x.example/sub/rel", False), ("https://x.example/abs", True), ("https://x.example/sub/", False)]
    assert p.word_count == 9  # One a b Rel Abs JS Top visible text — title (head) and script text excluded


def test_control_and_bidi_characters_are_stripped() -> None:
    p = parse_html("<title>Safe‮evil\u0000​ title</title>", "https://x.example/")
    assert p.title == "Safeevil title"


def test_jsonld_validation() -> None:
    p = parse_html('<script type="application/ld+json">{"@context":"https://schema.org","@graph":'
                   '[{"@type":"Organization"},{"name":"no type"}]}</script>'
                   '<script type="application/ld+json">[1,2</script>', "https://x.example/")
    assert p.jsonld[0] == {"valid": False, "error": "node without @type", "types": ["Organization"]}
    assert p.jsonld[1]["valid"] is False and "syntax" in p.jsonld[1]["error"]


def test_normalize_url() -> None:
    assert normalize_url("HTTP://Example.COM:80/a?b=1#frag") == "http://example.com/a?b=1"
    assert normalize_url("https://example.com:8443/") == "https://example.com:8443/"
    assert normalize_url("ftp://example.com/") is None
    assert normalize_url("https://user:pw@example.com/") is None


def test_robots_policy() -> None:
    p = build_policy(200, "User-agent: *\nDisallow: /private\n\nUser-agent: AISVBot\nDisallow: /nobot\n"
                          "Crawl-delay: 3\nSitemap: https://x.example/s.xml\n")
    assert p.allowed("https://x.example/private/a") is True  # AISVBot group overrides the * group
    assert p.allowed("https://x.example/nobot/a") is False
    assert p.crawl_delay == 3.0 and p.sitemaps == ["https://x.example/s.xml"]
    assert build_policy(None, None).allowed("https://x.example/") is False
    assert build_policy(500, None).allowed("https://x.example/") is False
    assert build_policy(401, None).allowed("https://x.example/") is False
    assert build_policy(404, None).allowed("https://x.example/") is True


def test_sitemap_parsing_and_xml_attacks() -> None:
    doc = parse_sitemap(b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap>'
                        b"<loc>https://x.example/a.xml</loc></sitemap></sitemapindex>")
    assert doc.child_sitemaps == ["https://x.example/a.xml"] and doc.urls == []
    bomb = (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>'
            b"<urlset><url><loc>&lol2;</loc></url></urlset>")
    assert parse_sitemap(bomb).error and parse_sitemap(bomb).urls == []
    xxe = (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
           b"<urlset><url><loc>&xxe;</loc></url></urlset>")
    assert parse_sitemap(xxe).urls == [] and parse_sitemap(xxe).error
    assert parse_sitemap(b"not xml").error
