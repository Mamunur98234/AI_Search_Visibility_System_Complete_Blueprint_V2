import ipaddress

from fastapi import Request


def client_ip(request: Request | None) -> str | None:
    """Peer IP as seen by the app (set uvicorn --proxy-headers/--forwarded-allow-ips behind a trusted proxy).
    Returns None for anything that is not a valid IP so it can be stored in an INET column."""
    if request is None or request.client is None:
        return None
    try:
        return str(ipaddress.ip_address(request.client.host))
    except ValueError:
        return None
