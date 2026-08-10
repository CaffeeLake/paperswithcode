import asyncio

import httpx

from backend.config import Settings
from backend.services import github_preview_service as previews


def test_github_preview_uses_server_token_and_caches_response():
    previews._CACHE.clear()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "description": "Small language models",
                "stargazers_count": 9_000,
                "forks_count": 500,
                "language": "Python",
                "archived": False,
                "owner": {"avatar_url": "https://avatars.example/huggingface.png"},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(github_token="server-secret")
    first = asyncio.run(
        previews.get_github_repository_preview(
            "huggingface", "smollm", settings, client=client
        )
    )
    second = asyncio.run(
        previews.get_github_repository_preview(
            "huggingface", "smollm", settings, client=client
        )
    )
    asyncio.run(client.aclose())

    assert first == second
    assert first.avatar_url == "https://avatars.example/huggingface.png"
    assert len(requests) == 1
    assert requests[0].headers["authorization"] == "Bearer server-secret"


def test_github_preview_never_falls_back_to_unauthenticated_requests():
    previews._CACHE.clear()
    settings = Settings(github_token="")

    try:
        asyncio.run(
            previews.get_github_repository_preview("huggingface", "smollm", settings)
        )
    except previews.GithubPreviewError as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("Expected missing token to fail closed")
