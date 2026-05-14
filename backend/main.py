"""
FastAPI backend for PapersWithCode API.

This module provides a FastAPI application that re-implements the deprecated
PapersWithCode API, starting with the Paper endpoints. It integrates with the
PostgreSQL database and provides compatible API responses.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.utils.exceptions import PaperNotFoundError, DatabaseError


def _is_mutable_paper_detail_path(path: str) -> bool:
    if path.startswith("/api/v1/papers/arxiv/"):
        return True

    if not path.startswith("/api/v1/papers/"):
        return False

    suffix = path.removeprefix("/api/v1/papers/")
    if suffix in {"search", "recent", "stats", "trending"}:
        return False

    return bool(suffix) and "/" not in suffix


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    settings = get_settings()
    print("🚀 Starting PapersWithCode API server")
    print(f"📊 Database: {settings.database_log_identifier}")
    print(f"🌍 Environment: {settings.environment}")

    yield

    # Shutdown
    print("🛑 Shutting down PapersWithCode API server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="PapersWithCode API",
        description="Re-implementation of the deprecated PapersWithCode API",
        version="1.0.0",
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url="/redoc" if settings.environment == "development" else None,
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_public_cache_headers(request, call_next):
        response = await call_next(request)
        if request.method == "GET" and _is_mutable_paper_detail_path(request.url.path):
            response.headers["Cache-Control"] = "no-store"
            return response

        if (
            request.method == "GET"
            and request.url.path.startswith("/api/v1/papers")
            and response.status_code == 200
            and "cache-control" not in response.headers
        ):
            response.headers["Cache-Control"] = (
                "public, max-age=60, stale-while-revalidate=300"
            )
        return response

    # Include routers
    from backend.routers import (
        papers,
        external_resources,
        authors,
        thumbnails,
        repositories,
        areas,
        tasks,
        methods,
        datasets,
        evaluations,
        metrics,
        cron,
        auth,
    )

    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(papers.router, prefix="/api/v1", tags=["papers"])
    # External-resource ingestion endpoints share the `/papers` prefix because
    # the resulting rows live in the same `papers` table.
    app.include_router(
        external_resources.router, prefix="/api/v1", tags=["external_resources"]
    )
    app.include_router(authors.router, prefix="/api/v1", tags=["authors"])
    app.include_router(repositories.router, prefix="/api/v1", tags=["repositories"])
    app.include_router(areas.router, prefix="/api/v1", tags=["areas"])
    app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
    app.include_router(methods.router, prefix="/api/v1", tags=["methods"])
    app.include_router(datasets.router, prefix="/api/v1", tags=["datasets"])
    app.include_router(evaluations.router, prefix="/api/v1", tags=["evaluations"])
    app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
    app.include_router(thumbnails.router, prefix="/api", tags=["thumbnails"])
    app.include_router(cron.router, prefix="/api/v1", tags=["cron"])

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "paperswithcode-api"}

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "PapersWithCode API",
            "version": "1.0.0",
            "description": "Re-implementation of the deprecated PapersWithCode API",
            "docs": "/docs" if settings.environment == "development" else None,
        }

    # Global exception handlers
    @app.exception_handler(PaperNotFoundError)
    async def paper_not_found_handler(request, exc: PaperNotFoundError):
        return JSONResponse(
            status_code=404, content={"error": "Paper not found", "detail": str(exc)}
        )

    @app.exception_handler(DatabaseError)
    async def database_error_handler(request, exc: DatabaseError):
        return JSONResponse(
            status_code=500, content={"error": "Database error", "detail": str(exc)}
        )

    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
    )
