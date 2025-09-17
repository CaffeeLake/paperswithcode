"""
FastAPI backend for PapersWithCode API.

This module provides a FastAPI application that re-implements the deprecated 
PapersWithCode API, starting with the Paper endpoints. It integrates with the 
PostgreSQL database and provides compatible API responses.
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .database.connection import get_database_session
from .models.database import Paper as DBPaper
from .models.api import Paper, Papers
from .services.paper_service import PaperService
from .utils.exceptions import PaperNotFoundError, DatabaseError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    settings = get_settings()
    print(f"🚀 Starting PapersWithCode API server")
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
        lifespan=lifespan
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
    from .routers import papers
    app.include_router(papers.router, prefix="/api/v1", tags=["papers"])
    
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
            "docs": "/docs" if settings.environment == "development" else None
        }
    
    # Global exception handlers
    @app.exception_handler(PaperNotFoundError)
    async def paper_not_found_handler(request, exc: PaperNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": "Paper not found", "detail": str(exc)}
        )
    
    @app.exception_handler(DatabaseError)
    async def database_error_handler(request, exc: DatabaseError):
        return JSONResponse(
            status_code=500,
            content={"error": "Database error", "detail": str(exc)}
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
        log_level=settings.log_level.lower()
    )
