"""Tests for shared generator rate-limit retry parsing."""

from backend.models.rate_limiting import MAX_RETRY_DELAY_SECONDS, RateLimitingMixin


class _Limiter(RateLimitingMixin):
    def __init__(self):
        super().__init__()


def test_parse_retry_delay_uses_gemini_retry_delay():
    limiter = _Limiter()
    error = (
        "429 RESOURCE_EXHAUSTED. {'retryDelay': '45s', "
        "'resource': 'generativelanguage.googleapis.com'}"
    )
    assert limiter._parse_retry_delay(error) == 45


def test_parse_retry_delay_rejects_overly_large_values():
    limiter = _Limiter()
    error = (
        "429 RESOURCE_EXHAUSTED. retry after 550207717 seconds "
        "for quota project 123456789"
    )
    assert limiter._parse_retry_delay(error) is None


def test_parse_retry_delay_caps_at_max():
    limiter = _Limiter()
    error = "'retryDelay': '999s'"
    assert limiter._parse_retry_delay(error) is None
    assert MAX_RETRY_DELAY_SECONDS == 300
