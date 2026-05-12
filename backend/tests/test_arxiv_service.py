from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx

from backend.services.arxiv_service import ArxivService


def test_build_direct_pdf_url_uses_known_version_without_metadata_lookup():
    service = ArxivService.__new__(ArxivService)

    assert (
        service._build_direct_pdf_url("arXiv:1806.00187", "v3")
        == "https://arxiv.org/pdf/1806.00187v3"
    )


def test_build_direct_pdf_url_replaces_existing_version_suffix():
    service = ArxivService.__new__(ArxivService)

    assert (
        service._build_direct_pdf_url("2605.06535v1", "v2")
        == "https://arxiv.org/pdf/2605.06535v2"
    )


def test_429_retry_delay_uses_retry_after_seconds():
    service = ArxivService.__new__(ArxivService)
    response = httpx.Response(429, headers={"retry-after": "42"})

    assert service._get_429_retry_delay(response, attempt=0) == 42


def test_429_retry_delay_uses_http_date_retry_after():
    service = ArxivService.__new__(ArxivService)
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=120)
    response = httpx.Response(
        429,
        headers={"retry-after": format_datetime(retry_at, usegmt=True)},
    )

    assert 0 < service._get_429_retry_delay(response, attempt=0) <= 120


def test_429_retry_delay_falls_back_to_exponential_cooldown():
    service = ArxivService.__new__(ArxivService)
    response = httpx.Response(429)

    assert service._get_429_retry_delay(response, attempt=1) == 120
