"""SafeFetcher: the ONLY component allowed to make outbound HTTP requests to customer websites.

Defences (see docs/threat-model.md T6-T8):
  * http/https only; ports 80/443 only; no credentials in URLs.
  * Every hostname is resolved by us; the request is refused if ANY resolved address is not globally
    routable (loopback, private, link-local incl. cloud metadata 169.254.169.254, CGNAT, multicast,
    reserved, documentation, unspecified, IPv4-mapped/NAT64 forms of those...).
  * The TCP connection goes to the exact IP we validated (DNS pinning) with SNI/Host set to the
    hostname, so a DNS-rebinding answer between check and connect cannot redirect us.
  * Redirects are never followed automatically: each hop is re-parsed, re-scoped, re-resolved and
    re-validated. Max 5 hops.
  * Connect/read timeouts plus a total deadline; decoded body capped (defeats compression bombs).
  * Environment proxy variables are ignored (urllib3 pools are created directly).
  * Nothing fetched is executed: no JavaScript engine, no plugin, no file is written to disk.
"""
from __future__ import annotations

import ipaddress
import ssl
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import urllib3
from urllib3.exceptions import (
    ConnectTimeoutError,
    DecodeError,
    HTTPError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
    SSLError,
)

ALLOWED_SCHEMES = {"http", "https"}
DEFAULT_PORTS = {"http": 80, "https": 443}

Resolver = Callable[[str], list[str]]
IpCheck = Callable[[str], bool]


class FetchError(Exception):
    """Raised for requests that must not or could not be made. `reason` is a stable code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: int
    redirect_chain: list[dict[str, object]] = field(default_factory=list)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    def text(self, limit: int | None = None) -> str:
        ct = self.headers.get("content-type", "")
        charset = "utf-8"
        if "charset=" in ct:
            charset = ct.split("charset=")[-1].split(";")[0].strip().strip('"') or "utf-8"
        data = self.body if limit is None else self.body[:limit]
        try:
            return data.decode(charset, errors="replace")
        except LookupError:
            return data.decode("utf-8", errors="replace")


def ip_is_public(ip_str: str) -> bool:
    """True only for globally routable unicast addresses."""
    try:
        ip = ipaddress.ip_address(ip_str.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip_is_public(str(ip.ipv4_mapped))
        if ip.sixtofour is not None:
            return ip_is_public(str(ip.sixtofour))
        if ip.teredo is not None:
            return False
        if ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network("64:ff9b:1::/48"):
            return False  # NAT64 can translate to internal IPv4
    return bool(ip.is_global) and not ip.is_multicast and not ip.is_reserved


def system_resolve(host: str, timeout: float = 5.0) -> list[str]:
    """A and AAAA lookup with a deadline (dnspython). IP literals are returned as-is for checking."""
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        pass
    import dns.exception
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    out: list[str] = []
    for rtype in ("A", "AAAA"):
        try:
            out.extend(r.to_text() for r in resolver.resolve(host, rtype))
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
        except dns.exception.DNSException as exc:
            raise FetchError("dns_error", type(exc).__name__) from exc
    if not out:
        raise FetchError("dns_error", "no A/AAAA records")
    return out


def normalize_host(host: str) -> str:
    h = host.strip().lower().rstrip(".")
    try:
        return h.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise FetchError("invalid_url", "bad hostname") from exc


class SafeFetcher:
    def __init__(
        self,
        user_agent: str,
        *,
        resolver: Resolver | None = None,
        ip_allowed: IpCheck = ip_is_public,
        allowed_ports: Iterable[int] = (80, 443),
        connect_timeout: float = 5.0,
        read_timeout: float = 10.0,
        total_timeout: float = 25.0,
        max_bytes: int = 5 * 1024 * 1024,
        max_redirects: int = 5,
    ) -> None:
        self.user_agent = user_agent
        self.resolver = resolver or system_resolve
        self.ip_allowed = ip_allowed
        self.allowed_ports = set(allowed_ports)
        self.timeout = urllib3.Timeout(connect=connect_timeout, read=read_timeout)
        self.total_timeout = total_timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.resolutions = 0  # observable for tests (one resolution per hop)

    # Overridable hook (tests map a public port to a local test server). Production never overrides it.
    def _target(self, ip: str, port: int) -> tuple[str, int]:
        return ip, port

    def validate_url(self, url: str) -> tuple[str, str, int, str]:
        """Returns (scheme, host, port, path_and_query) or raises FetchError."""
        if len(url) > 2048:
            raise FetchError("invalid_url", "URL too long")
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            raise FetchError("blocked_scheme", scheme or "none")
        if parts.username or parts.password or "@" in parts.netloc:
            raise FetchError("invalid_url", "credentials in URL")
        if not parts.hostname:
            raise FetchError("invalid_url", "no host")
        try:
            port = parts.port or DEFAULT_PORTS[scheme]
        except ValueError as exc:
            raise FetchError("invalid_url", "bad port") from exc
        if port not in self.allowed_ports:
            raise FetchError("blocked_port", str(port))
        host = normalize_host(parts.hostname)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        return scheme, host, port, path

    def _resolve_checked(self, host: str) -> str:
        self.resolutions += 1
        addrs = self.resolver(host)
        if not addrs:
            raise FetchError("dns_error", "no addresses")
        bad = [a for a in addrs if not self.ip_allowed(a)]
        if bad:
            raise FetchError("blocked_ip", f"{host} resolves to non-public address")
        return addrs[0]

    def fetch(
        self,
        url: str,
        *,
        in_scope: Callable[[str], bool] | None = None,
        accept: str = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
    ) -> FetchResult:
        start = time.monotonic()
        deadline = start + self.total_timeout
        chain: list[dict[str, object]] = []
        current = url
        for _hop in range(self.max_redirects + 1):
            if in_scope is not None and not in_scope(current):
                raise FetchError("redirect_out_of_scope" if chain else "out_of_scope", current)
            scheme, host, port, path = self.validate_url(current)
            ip = self._resolve_checked(host)
            status, headers, body = self._request(scheme, host, port, ip, path, accept, deadline)
            location = headers.get("location")
            if status in (301, 302, 303, 307, 308) and location:
                nxt = urljoin(current, location.strip())
                chain.append({"url": current, "status": status, "location": nxt})
                current = nxt
                continue
            return FetchResult(url=url, final_url=current, status=status, headers=headers, body=body,
                               elapsed_ms=int((time.monotonic() - start) * 1000), redirect_chain=chain)
        raise FetchError("too_many_redirects", str(self.max_redirects))

    def _request(self, scheme: str, host: str, port: int, ip: str, path: str, accept: str,
                 deadline: float) -> tuple[int, dict[str, str], bytes]:
        tip, tport = self._target(ip, port)
        host_header = host if port == DEFAULT_PORTS[scheme] else f"{host}:{port}"
        pool: urllib3.HTTPConnectionPool
        if scheme == "https":
            ctx = ssl.create_default_context()
            pool = urllib3.HTTPSConnectionPool(
                tip, tport, timeout=self.timeout, retries=False, maxsize=1, ssl_context=ctx,
                server_hostname=host, assert_hostname=host,
            )
        else:
            pool = urllib3.HTTPConnectionPool(tip, tport, timeout=self.timeout, retries=False, maxsize=1)
        try:
            resp = pool.urlopen(
                "GET", path, redirect=False, preload_content=False, decode_content=True, assert_same_host=False,
                headers={"Host": host_header, "User-Agent": self.user_agent, "Accept": accept,
                         "Accept-Encoding": "gzip, deflate", "Connection": "close"},
            )
            try:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                declared = headers.get("content-length", "")
                if declared.isdigit() and int(declared) > self.max_bytes:
                    raise FetchError("too_large", f"declared {declared} bytes")
                chunks: list[bytes] = []
                total = 0
                while True:
                    if time.monotonic() > deadline:
                        raise FetchError("timeout", "total deadline exceeded")
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise FetchError("too_large", f"more than {self.max_bytes} bytes")
                    chunks.append(chunk)
                return resp.status, headers, b"".join(chunks)
            finally:
                resp.release_conn()
                resp.close()
        except FetchError:
            raise
        except (TimeoutError, ConnectTimeoutError, ReadTimeoutError) as exc:
            raise FetchError("timeout", type(exc).__name__) from exc
        except SSLError as exc:
            raise FetchError("tls_error", "certificate or TLS handshake failed") from exc
        except DecodeError as exc:
            raise FetchError("decode_error", "invalid content encoding") from exc
        except (NewConnectionError, ProtocolError, HTTPError, OSError) as exc:
            raise FetchError("connection_error", type(exc).__name__) from exc
        finally:
            pool.close()
