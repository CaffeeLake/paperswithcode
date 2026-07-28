"""Machine-readable discovery metadata for the public API."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse


router = APIRouter()

_ORIGIN = "https://paperswithcode.co"
_CATALOG_URL = f"{_ORIGIN}/.well-known/api-catalog"
_PROFILE = "https://www.rfc-editor.org/info/rfc9727"
_MEDIA_TYPE = f'application/linkset+json; profile="{_PROFILE}"'
_HEADERS = {
    "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400",
    "Link": f'<{_CATALOG_URL}>; rel="api-catalog"',
}


@router.api_route("/docs/api", methods=["GET", "HEAD"], include_in_schema=False)
def api_documentation() -> HTMLResponse:
    """Return a compact human-readable entry point for the public API."""

    return HTMLResponse(
        """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Papers With Code API</title></head>
<body>
<main>
<h1>Papers With Code API</h1>
<p>The public catalog API is available under <code>/api/v1/</code>.</p>
<ul>
<li><a href="/openapi.json">OpenAPI description</a></li>
<li><a href="/.well-known/api-catalog">API catalog</a></li>
<li><a href="/health">Service health</a></li>
</ul>
<p>Most catalog read endpoints require no authentication. User-specific and
administrative operations declare their requirements in the OpenAPI description.</p>
</main>
</body>
</html>
""",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.api_route(
    "/.well-known/api-catalog",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def api_catalog() -> JSONResponse:
    """Return the RFC 9727 catalog for the public Papers With Code API."""

    return JSONResponse(
        {
            "linkset": [
                {
                    "anchor": f"{_ORIGIN}/api/v1/papers/",
                    "service-desc": [
                        {
                            "href": f"{_ORIGIN}/openapi.json",
                            "type": "application/json",
                        }
                    ],
                    "service-doc": [
                        {
                            "href": f"{_ORIGIN}/docs/api",
                            "type": "text/html",
                        }
                    ],
                    "status": [
                        {
                            "href": f"{_ORIGIN}/health",
                            "type": "application/json",
                        }
                    ],
                }
            ]
        },
        media_type=_MEDIA_TYPE,
        headers=_HEADERS,
    )
