"""Minimal localhost-only application for Codex evaluation curation jobs."""

from fastapi import FastAPI

from backend.routers import (
    codex_add_evals,
    codex_curation_callbacks,
    codex_enrich_paper,
)


def create_codex_add_evals_app() -> FastAPI:
    app = FastAPI(
        title="Papers With Code Codex Add Evals",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(codex_add_evals.router, prefix="/api/v1")
    app.include_router(codex_enrich_paper.router, prefix="/api/v1")
    app.include_router(codex_curation_callbacks.router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "healthy", "service": "codex-add-evals"}

    return app


app = create_codex_add_evals_app()
