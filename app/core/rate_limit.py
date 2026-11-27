"""Rate limiting configuration.

The API runs behind AWS ALB -> nginx -> uvicorn, so `request.client.host` is a proxy
address. Rate limits must key on the real visitor IP, otherwise every visitor shares
one bucket. We take the right-most *public* address in X-Forwarded-For: entries to the
right of it were appended by our own proxies (private VPC / loopback ranges), and
entries to the left can be forged by the client.
"""

import ipaddress
from typing import Optional

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved)


def client_ip(request: Request) -> str:
    xff: Optional[str] = request.headers.get("x-forwarded-for")
    if xff:
        for candidate in reversed([p.strip() for p in xff.split(",") if p.strip()]):
            if _is_public(candidate):
                return candidate
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip and _is_public(real_ip):
        return real_ip
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip)
