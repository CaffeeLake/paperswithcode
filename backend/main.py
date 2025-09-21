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

try:
    from .config import get_settings
    from .utils.exceptions import PaperNotFoundError, DatabaseError
except ImportError:
    # Handle case when running as script
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).parent
    sys.path.insert(0, str(backend_dir))
    from config import get_settings
    from utils.exceptions import PaperNotFoundError, DatabaseError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    settings = get_settings()
    print("🚀 Starting PapersWithCode API server")
    print(f"📊 Database: {settings.database_url}")
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
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # Include routers
    try:
        from .routers import papers, authors, thumbnails, repositories
    except ImportError:
        from routers import papers, authors, thumbnails, repositories

    app.include_router(papers.router, prefix="/api/v1", tags=["papers"])
    app.include_router(authors.router, prefix="/api/v1", tags=["authors"])
    app.include_router(repositories.router, prefix="/api/v1", tags=["repositories"])
    app.include_router(thumbnails.router, prefix="/api", tags=["thumbnails"])

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
