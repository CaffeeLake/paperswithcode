import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import aiohttp
import pytest

WORKFLOWS_DIR = Path(__file__).parents[2] / ".github" / "workflows"
if str(WORKFLOWS_DIR) not in sys.path:
    sys.path.append(str(WORKFLOWS_DIR))

from scripts.daily import import_hf_daily_papers as importer_module  # noqa: E402
from scripts.daily.import_hf_daily_papers import (  # noqa: E402
    HuggingFaceDailyPapersJob,
)


def _paper(arxiv_id):
    return {"paper": {"id": arxiv_id}}


class _Response:
    def __init__(self, status, payload=None, json_error=None):
        self.status = status
        self.payload = payload
        self.json_error = json_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class _Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def get(self, url, *, params, timeout):
        self.requests.append((url, params, timeout))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def _job_with_responses(monkeypatch, responses):
    job = HuggingFaceDailyPapersJob.__new__(HuggingFaceDailyPapersJob)
    job.logger = MagicMock()
    session = _Session(responses)
    monkeypatch.setattr(importer_module.aiohttp, "ClientSession", lambda: session)
    return job, session


def _fetch(job, date="2026-06-04"):
    return asyncio.run(job.fetch_daily_papers(date))


def test_fetches_more_than_fifty_papers_across_pages(monkeypatch):
    first_page = [_paper(f"2606.{index:05d}") for index in range(50)]
    second_page = [_paper(f"2606.{index:05d}") for index in range(50, 54)]
    job, session = _job_with_responses(
        monkeypatch,
        [_Response(200, first_page), _Response(200, second_page)],
    )

    result = _fetch(job)

    assert result == first_page + second_page
    assert [request[1]["p"] for request in session.requests] == [0, 1]
    assert all(request[1]["limit"] == 50 for request in session.requests)
    assert all(request[1]["sort"] == "publishedAt" for request in session.requests)


def test_exact_page_size_fetches_empty_terminal_page(monkeypatch):
    first_page = [_paper(f"2606.{index:05d}") for index in range(50)]
    job, session = _job_with_responses(
        monkeypatch,
        [_Response(200, first_page), _Response(200, [])],
    )

    assert _fetch(job) == first_page
    assert [request[1]["p"] for request in session.requests] == [0, 1]


def test_duplicate_ids_across_pages_are_removed_in_first_seen_order(monkeypatch):
    first_page = [_paper(f"2606.{index:05d}") for index in range(50)]
    duplicate = first_page[-1]
    new_paper = _paper("2606.99999")
    job, _ = _job_with_responses(
        monkeypatch,
        [_Response(200, first_page), _Response(200, [duplicate, new_paper])],
    )

    result = _fetch(job)

    assert result == first_page + [new_paper]


@pytest.mark.parametrize("response", [_Response(200, []), _Response(400)])
def test_empty_and_http_400_dates_return_empty(monkeypatch, response):
    job, session = _job_with_responses(monkeypatch, [response])

    assert _fetch(job) == []
    assert len(session.requests) == 1


def test_later_page_failure_raises_instead_of_returning_partial_cohort(monkeypatch):
    first_page = [_paper(f"2606.{index:05d}") for index in range(50)]
    job, _ = _job_with_responses(
        monkeypatch,
        [_Response(200, first_page), _Response(503)],
    )

    with pytest.raises(RuntimeError, match="HTTP 503 on page 1"):
        _fetch(job)

    job.logger.error.assert_called_once()


def test_later_page_network_failure_raises_instead_of_returning_partial_cohort(
    monkeypatch,
):
    first_page = [_paper(f"2606.{index:05d}") for index in range(50)]
    job, _ = _job_with_responses(
        monkeypatch,
        [_Response(200, first_page), aiohttp.ClientConnectionError("disconnected")],
    )

    with pytest.raises(RuntimeError, match="page 1: disconnected"):
        _fetch(job)

    job.logger.error.assert_called_once()
