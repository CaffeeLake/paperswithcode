"""Resolve a request IP without trusting caller-supplied forwarding headers."""

import ipaddress

from fastapi import Request


def get_client_ip(request: Request) -> str | None:
    peer = request.client.host if request.client else None
    if not peer:
        return None
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return None
    candidate = peer
    if peer_ip.is_loopback:
        forwarded = request.headers.get("X-Real-IP")
        if forwarded:
            candidate = forwarded.strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None
