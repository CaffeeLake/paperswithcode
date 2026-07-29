from urllib.parse import parse_qs

import httpx

from backend.services.openalex_reference_service import OpenAlexReferenceClient


def test_openalex_batches_exact_arxiv_urls_and_merges_duplicate_work_records():
    def handler(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.url.query.decode())
        assert query["per_page"] == ["100"]
        assert "http://arxiv.org/abs/2103.00020" in query["filter"][0]
        assert "https://arxiv.org/abs/2103.00020" in query["filter"][0]
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "locations": [
                            {"landing_page_url": "http://arxiv.org/abs/2103.00020"}
                        ],
                        "referenced_works": ["https://openalex.org/W10"],
                    },
                    {
                        "id": "https://openalex.org/W2",
                        "locations": [
                            {"landing_page_url": "https://arxiv.org/pdf/2103.00020.pdf"}
                        ],
                        "referenced_works": ["https://openalex.org/W11"],
                    },
                ]
            },
        )

    client = OpenAlexReferenceClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        request_delay=0,
    )
    batch = client.fetch_works(["2103.00020"])

    assert batch is not None
    assert batch.work_ids_by_arxiv["2103.00020"] == {
        "https://openalex.org/W1",
        "https://openalex.org/W2",
    }
    assert batch.references_by_arxiv["2103.00020"] == {
        "https://openalex.org/W10",
        "https://openalex.org/W11",
    }
    assert client.api_calls == 1


def test_openalex_failed_batch_is_not_returned_as_empty_coverage():
    client = OpenAlexReferenceClient(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(429, json={"error": "limited"})
            )
        ),
        request_delay=0,
        max_retries=2,
    )

    assert client.fetch_works(["2103.00020"]) is None
    assert client.api_calls == 2
    assert client.rate_limit_hits == 2
    assert client.failed_requests == 1
