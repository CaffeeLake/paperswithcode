import asyncio
import socket

import pytest

from backend.services.safe_outbound_http_service import (
    PinnedResolver,
    SafeOutboundHttpError,
    _address_is_public,
    _validated_url,
    resolve_public_addresses,
    fetch_public_resource,
)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
def test_non_public_addresses_are_rejected(address):
    assert not _address_is_public(address)


def test_public_ipv4_and_ipv6_are_accepted():
    assert _address_is_public("8.8.8.8")
    assert _address_is_public("2606:4700:4700::1111")
    assert _address_is_public("::ffff:8.8.8.8")


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "ftp://example.com/file",
        "http://example.com:8080/file",
        "http://user@example.com/file",
        "http://2130706433/",
    ],
)
def test_ambiguous_or_unsupported_urls_are_rejected(url):
    with pytest.raises(SafeOutboundHttpError):
        _validated_url(url)


def test_mixed_public_private_dns_answer_is_rejected(monkeypatch):
    async def fake_getaddrinfo(*_args, **_kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]

    async def exercise():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
        with pytest.raises(SafeOutboundHttpError) as error:
            await resolve_public_addresses("example.com", 443)
        assert error.value.status_code == 403

    asyncio.run(exercise())


def test_pinned_resolver_returns_only_validated_addresses():
    async def exercise():
        resolver = PinnedResolver("example.com", ("8.8.8.8", "2606:4700:4700::1111"))
        records = await resolver.resolve("example.com", 443)
        assert [record["host"] for record in records] == [
            "8.8.8.8",
            "2606:4700:4700::1111",
        ]
        with pytest.raises(OSError):
            await resolver.resolve("attacker.example", 443)

    asyncio.run(exercise())


def test_redirect_target_is_revalidated_before_next_request(monkeypatch):
    calls = []

    async def fake_fetch(url, **_kwargs):
        calls.append(url)
        return 302, "", b"", "http://127.0.0.1/metadata"

    monkeypatch.setattr(
        "backend.services.safe_outbound_http_service._fetch_one_hop", fake_fetch
    )

    async def exercise():
        with pytest.raises(SafeOutboundHttpError) as error:
            await fetch_public_resource(
                "https://example.com/start",
                allowed_content_types=frozenset({"text/html"}),
                max_bytes=100,
                timeout_seconds=1,
            )
        assert error.value.status_code == 403
        assert calls == ["https://example.com/start"]

    asyncio.run(exercise())


def test_allowed_host_registry_applies_to_redirect_hops(monkeypatch):
    responses = iter(
        [
            (302, "", b"", "https://other.example/file.pdf"),
            (200, "application/pdf", b"%PDF", None),
        ]
    )

    async def fake_fetch(_url, **_kwargs):
        return next(responses)

    monkeypatch.setattr(
        "backend.services.safe_outbound_http_service._fetch_one_hop", fake_fetch
    )

    async def exercise():
        with pytest.raises(SafeOutboundHttpError) as error:
            await fetch_public_resource(
                "https://example.com/file.pdf",
                allowed_content_types=frozenset({"application/pdf"}),
                max_bytes=100,
                timeout_seconds=1,
                allowed_hosts=frozenset({"example.com"}),
            )
        assert error.value.status_code == 403

    asyncio.run(exercise())
