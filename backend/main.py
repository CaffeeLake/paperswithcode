"""
FastAPI backend for PapersWithCode API.

This module provides a FastAPI application that re-implements the deprecated
PapersWithCode API, starting with the Paper endpoints. It integrates with the
PostgreSQL database and provides compatible API responses.
"""

import asyncio
import contextlib
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.services.deployment_lifecycle import (
    DeploymentAccountingMiddleware,
    deployment_lifecycle,
    operator_socket_allowed,
)
from backend.services.runtime_validation import validate_runtime
from backend.utils.exceptions import DatabaseError, PaperNotFoundError

# Requests slower than this (in milliseconds) are logged so production slow
# pages can be correlated without ad-hoc instrumentation. Tune via the
# `PWC_SLOW_REQUEST_MS` env var.
_SLOW_REQUEST_MS = float(os.getenv("PWC_SLOW_REQUEST_MS", "1000"))
_timing_logger = logging.getLogger("backend.timing")


def _is_mutable_paper_detail_path(path: str) -> bool:
    if path.startswith("/api/v1/papers/arxiv/"):
        return True

    if not path.startswith("/api/v1/papers/"):
        return False

    suffix = path.removeprefix("/api/v1/papers/")
    if suffix in {"search", "recent", "stats", "trending"}:
        return False

    return bool(suffix) and "/" not in suffix


# Read-only public API prefixes that are safe to cache briefly in the browser
# and any shared CDN. These power list/detail pages on the marketing site
# (methods, tasks, datasets, ...). Auth/session paths (`/me`, `/auth`,
# `/cron`) are deliberately excluded so signed-in state stays fresh.
# Trailing slash makes prefix matches accurate (e.g. `/api/v1/papers` would
# otherwise also match `/api/v1/papers-archive/...` if that route ever
# appeared).
_PUBLIC_CACHEABLE_PREFIXES = (
    "/api/v1/papers/",
    "/api/v1/methods/",
    "/api/v1/tasks/",
    "/api/v1/datasets/",
    "/api/v1/areas/",
    "/api/v1/metrics/",
    "/api/v1/repositories/",
    "/api/v1/project-pages/",
    "/api/v1/authors/",
    "/api/v1/conferences/",
    "/api/v1/organizations/",
    "/api/v1/frameworks/",
)

# Endpoints that must never be cached even on GET because their response
# depends on the signed-in user / session cookie. Trailing slash on each
# prefix prevents false matches like `/api/v1/me` accidentally matching
# `/api/v1/methods/...`.
_PRIVATE_GET_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/me/",
    "/api/v1/cron/",
    "/api/v1/admin/",
    "/api/v1/contributions",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    settings = get_settings()
    print("🚀 Starting PapersWithCode API server")
    print(f"📊 Database: {settings.database_log_identifier}")
    print(f"🌍 Environment: {settings.environment}")
    print(f"📦 Release: {settings.release_id}")
    validate_runtime(settings)
    if settings.chat_enabled:
        if not settings.chat_require_auth:
            raise RuntimeError("PWC_CHAT_REQUIRE_AUTH must remain enabled")
        if not settings.hf_token:
            raise RuntimeError("PWC_HF_TOKEN is required when chat is enabled")

    maintenance_task = None
    pool_startup_task = None
    if (
        settings.is_deployed
        and settings.environment == "staging"
        and settings.chat_enabled
    ):
        from backend.database.connection import db_manager
        from backend.services.chat_latency_service import ChatLatencyService
        from backend.services.chat_turn_runner import shared_sandbox_manager
        from backend.services.openrouter_budget_service import (
            OpenRouterBudgetUnavailable,
            openrouter_budget_status,
        )
        from backend.services.openrouter_user_budget_service import (
            OpenRouterUserBudgetService,
        )

        manager = shared_sandbox_manager(settings)

        def reconcile_stale_chat_turns() -> dict[str, int]:
            with db_manager.session_local() as db:
                reconciled = ChatLatencyService(db).reconcile_stale_turns()
                db.commit()
            if sum(reconciled.values()):
                logging.getLogger(__name__).warning(
                    "chat stale turns reconciled complete=%d error=%d interrupted=%d",
                    reconciled["complete"],
                    reconciled["error"],
                    reconciled["interrupted"],
                )
            return reconciled

        async def reconcile_stale_latency() -> None:
            await asyncio.to_thread(reconcile_stale_chat_turns)

        async def replenish_pool_at_startup() -> None:
            try:
                await manager.reconcile()
                await reconcile_stale_latency()
                await manager.maintain_pool()
            except Exception as error:
                logging.getLogger(__name__).warning(
                    "chat blank pool startup replenishment failed error=%s",
                    type(error).__name__,
                )

        async def maintain_sandboxes() -> None:
            latency_cleanup_date = None
            openrouter_maintenance_date = None
            active_spend_alerting = False
            while True:
                await asyncio.sleep(60)
                operations = [
                    manager.reconcile,
                    reconcile_stale_latency,
                    manager.maintain_pool,
                    manager.reap_idle,
                    manager.enforce_warm_cap,
                    manager.expire_inactive_snapshots,
                ]
                today = datetime.now(UTC).date()
                if latency_cleanup_date != today:

                    async def cleanup_latency(operation_date=today) -> None:
                        nonlocal latency_cleanup_date
                        with db_manager.session_local() as db:
                            ChatLatencyService(db).cleanup()
                            db.commit()
                        latency_cleanup_date = operation_date

                    operations.append(cleanup_latency)

                if openrouter_maintenance_date != today:

                    async def maintain_openrouter_accounting(
                        operation_date=today,
                    ) -> None:
                        nonlocal openrouter_maintenance_date
                        with db_manager.session_local() as db:
                            service = OpenRouterUserBudgetService(db, settings)
                            health = service.accounting_health()
                            reconciliation = (
                                await service.reconcile_unknown(batch_size=100)
                                if settings.chat_openrouter_server_funded_enabled
                                else {"reconciled": 0, "examined": 0, "cursor": None}
                            )
                            cleanup = service.cleanup_retention(batch_size=500)
                            db.commit()
                        if health["stale_reservations"] or health["old_unknown_costs"]:
                            logging.getLogger(__name__).error(
                                "openrouter accounting incidents stale_reservations=%d "
                                "old_unknown_costs=%d",
                                health["stale_reservations"],
                                health["old_unknown_costs"],
                            )
                        if settings.chat_openrouter_server_funded_enabled:
                            try:
                                provider = await openrouter_budget_status(settings)
                                provider_microusd = round(
                                    provider.usage_monthly_usd * 1_000_000
                                )
                                drift = abs(
                                    provider_microusd - health["ledger_microusd"]
                                )
                                if (
                                    drift
                                    >= settings.chat_openrouter_drift_alert_microusd
                                ):
                                    logging.getLogger(__name__).error(
                                        "openrouter funded usage drift "
                                        "ledger_microusd=%d provider_microusd=%d "
                                        "drift_microusd=%d",
                                        health["ledger_microusd"],
                                        provider_microusd,
                                        drift,
                                    )
                            except OpenRouterBudgetUnavailable as error:
                                logging.getLogger(__name__).error(
                                    "openrouter management status unavailable error=%s",
                                    type(error).__name__,
                                )
                        openrouter_maintenance_date = operation_date
                        logging.getLogger(__name__).info(
                            "openrouter accounting maintenance reconciled=%d "
                            "examined=%d deleted_calls=%d deleted_months=%d "
                            "deleted_audit=%d",
                            reconciliation["reconciled"],
                            reconciliation["examined"],
                            cleanup["provider_calls"],
                            cleanup["monthly_usage"],
                            cleanup["credential_audit"],
                        )

                    operations.append(maintain_openrouter_accounting)

                async def monitor_active_spend() -> None:
                    nonlocal active_spend_alerting
                    with db_manager.session_local() as db:
                        status = ChatLatencyService(db).active_spend_status()
                    should_alert = status["should_alert"]
                    if should_alert and not active_spend_alerting:
                        logging.getLogger(__name__).warning(
                            "chat active spend alert "
                            "projected_monthly_usd=%.2f threshold_usd=%.2f "
                            "month_to_date_usd=%.2f cost_per_completed_turn_usd=%.6f",
                            status["projected_monthly_cost_usd"],
                            status["alert_threshold_usd"],
                            status["month_to_date_cost_usd"],
                            status["cost_per_completed_turn_usd"],
                        )
                    elif active_spend_alerting and not should_alert:
                        logging.getLogger(__name__).info(
                            "chat active spend alert recovered "
                            "projected_monthly_usd=%.2f threshold_usd=%.2f",
                            status["projected_monthly_cost_usd"],
                            status["alert_threshold_usd"],
                        )
                    active_spend_alerting = should_alert

                operations.append(monitor_active_spend)
                for operation in operations:
                    try:
                        await operation()
                    except Exception as error:
                        logging.getLogger(__name__).warning(
                            "chat sandbox maintenance failed operation=%s error=%s",
                            operation.__name__,
                            type(error).__name__,
                        )

        pool_startup_task = asyncio.create_task(replenish_pool_at_startup())
        maintenance_task = asyncio.create_task(maintain_sandboxes())

    yield

    if maintenance_task:
        maintenance_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await maintenance_task
    if pool_startup_task:
        pool_startup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pool_startup_task

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
    app.add_middleware(DeploymentAccountingMiddleware)

    # Add CORS middleware. `allow_origin_regex` is used to permit the Hugging
    # Face Space mirror (e.g. `https://<owner>-<name>.hf.space`) when the
    # `PWC_EXTRA_ALLOWED_ORIGIN_REGEX` setting is configured, without having
    # to hardcode every Space subdomain.
    cors_kwargs = dict(
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    if settings.extra_allowed_origin_regex:
        cors_kwargs["allow_origin_regex"] = settings.extra_allowed_origin_regex
    app.add_middleware(CORSMiddleware, **cors_kwargs)

    @app.middleware("http")
    async def enforce_staging_write_boundary(request, call_next):
        if settings.is_deployed and request.method not in {"GET", "HEAD", "OPTIONS"}:
            catalog_prefixes = (
                "/api/v1/papers",
                "/api/v1/tasks",
                "/api/v1/methods",
                "/api/v1/datasets",
                "/api/v1/evaluations",
                "/api/v1/metrics",
                "/api/v1/conferences",
                "/api/v1/organizations",
                "/api/v1/frameworks",
                "/api/v1/repositories",
                "/api/v1/external-resources",
                "/api/thumbnails",
            )
            is_thumbnail_mutation = request.url.path.startswith("/api/thumbnails")
            is_staging_catalog_mutation = settings.environment == "staging" and any(
                request.url.path.startswith(prefix) for prefix in catalog_prefixes[:-1]
            )
            if is_staging_catalog_mutation or (
                is_thumbnail_mutation and not settings.thumbnail_mutations_enabled
            ):
                return JSONResponse(
                    {
                        "detail": (
                            "Staging is preview-only for catalog and thumbnail "
                            "mutations"
                        )
                    },
                    status_code=403,
                )
        return await call_next(request)

    @app.middleware("http")
    async def log_slow_requests(request, call_next):
        # Outermost middleware (added last), so the measured duration covers
        # the whole handler including cache-header logic.
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000.0
        # Expose timing for ad-hoc debugging / curl -D.
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
        if duration_ms >= _SLOW_REQUEST_MS:
            _timing_logger.warning(
                "slow request: %s %s status=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
        return response

    @app.middleware("http")
    async def add_public_cache_headers(request, call_next):
        response = await call_next(request)
        if settings.environment == "staging" and response.headers.get(
            "content-type", ""
        ).startswith("text/html"):
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        if request.method != "GET":
            return response

        path = request.url.path

        # Per-paper detail rows can change (admin edits, new repos linked)
        # so keep these uncached.
        if _is_mutable_paper_detail_path(path):
            response.headers["Cache-Control"] = "no-store"
            return response

        # User-specific endpoints (bookmarks, session probes, cron dashboard)
        # must always reflect the current session.
        if (
            any(path.startswith(prefix) for prefix in _PRIVATE_GET_PREFIXES)
            or path.endswith("/curation-state")
            or path == "/api/v1/evaluations/curation-state"
        ):
            response.headers["Cache-Control"] = "no-store"
            return response

        # Public list/detail GETs benefit from a short freshness window plus
        # a longer stale-while-revalidate so repeat navigation is instant.
        if (
            response.status_code == 200
            and "cache-control" not in response.headers
            and any(path.startswith(prefix) for prefix in _PUBLIC_CACHEABLE_PREFIXES)
        ):
            response.headers["Cache-Control"] = (
                "public, max-age=60, stale-while-revalidate=300"
            )
        return response

    # Include routers
    from backend.routers import (
        agent_discovery,
        areas,
        auth,
        authors,
        bookmarks,
        chat,
        codex_add_evals,
        codex_curation_callbacks,
        codex_enrich_paper,
        conferences,
        contributions,
        cron,
        datasets,
        evaluations,
        external_resources,
        frameworks,
        inference_billing,
        methods,
        metrics,
        organizations,
        paper_assets,
        paper_pages,
        papers,
        pending_edits,
        preferences,
        repositories,
        research_catalog,
        search_discovery,
        sitemaps,
        stats,
        tasks,
        thumbnails,
    )

    app.include_router(agent_discovery.router, tags=["agent_discovery"])
    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(bookmarks.router, prefix="/api/v1", tags=["bookmarks"])
    app.include_router(contributions.router, prefix="/api/v1", tags=["contributions"])
    app.include_router(preferences.router, prefix="/api/v1", tags=["preferences"])
    app.include_router(
        inference_billing.router, prefix="/api/v1", tags=["inference-billing"]
    )
    app.include_router(pending_edits.router, prefix="/api/v1", tags=["pending_edits"])
    app.include_router(papers.router, prefix="/api/v1", tags=["papers"])
    app.include_router(research_catalog.router, prefix="/api/v1", tags=["research"])
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
    app.include_router(conferences.router, prefix="/api/v1", tags=["conferences"])
    app.include_router(organizations.router, prefix="/api/v1", tags=["organizations"])
    app.include_router(frameworks.router, prefix="/api/v1", tags=["frameworks"])
    app.include_router(stats.router, prefix="/api/v1", tags=["stats"])
    if settings.chat_enabled:
        app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
        from backend.chat_gateway_app import app as chat_gateway_app

        app.mount("/api/internal/chat-gateway", chat_gateway_app)
    app.include_router(codex_add_evals.router, prefix="/api/v1", tags=["admin"])
    app.include_router(codex_enrich_paper.router, prefix="/api/v1", tags=["admin"])
    app.include_router(
        codex_curation_callbacks.router, prefix="/api/v1", tags=["admin"]
    )
    app.include_router(thumbnails.router, prefix="/api", tags=["thumbnails"])
    app.include_router(paper_assets.router)
    # Server-rendered paper-page HTML for social previews. Mounted at the
    # app root because the public URL shape is `/paper/{id}` (not under
    # `/api/v1/...`).
    app.include_router(search_discovery.router, tags=["search_discovery"])
    app.include_router(sitemaps.router, tags=["sitemaps"])
    app.include_router(paper_pages.router, tags=["paper_pages"])
    if settings.cron_enabled:
        app.include_router(cron.router, prefix="/api/v1", tags=["cron"])

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "paperswithcode-api",
            "release_id": settings.release_id,
        }

    @app.get("/internal/ready", include_in_schema=False)
    async def internal_ready():
        lifecycle = deployment_lifecycle.status()
        if not lifecycle.accepting_chat_turns:
            return JSONResponse(
                {
                    **deployment_lifecycle.as_dict(),
                    "status": "draining",
                },
                status_code=503,
            )
        try:
            features = validate_runtime(settings)
            if settings.environment == "staging" and settings.chat_enabled:
                from backend.database.connection import db_manager
                from backend.services.chat_sandbox_service import (
                    SandboxSessionManager,
                )
                from backend.services.runtime_validation import validate_chat_schema

                with db_manager.session_local() as db:
                    validate_chat_schema(db)
                await SandboxSessionManager(settings).validate_image_reference()
        except Exception as error:
            return JSONResponse(
                {
                    "status": "not_ready",
                    "reason": str(error)[:200],
                },
                status_code=503,
            )
        route_paths = {route.path for route in app.routes}
        has_chat_routes = any(path.startswith("/api/v1/chat") for path in route_paths)
        if has_chat_routes != settings.chat_enabled:
            return JSONResponse(
                {"status": "not_ready", "reason": "chat route manifest mismatch"},
                status_code=503,
            )
        return {
            "status": "ready",
            "environment": settings.environment,
            "release_id": settings.release_id,
            "slot": lifecycle.slot,
            "runtime_id": lifecycle.runtime_id,
            "features": features,
            "frontend_assets_valid": True,
            "thumbnail_store_valid": True,
        }

    @app.get("/internal/deployment-status", include_in_schema=False)
    async def internal_deployment_status(request: Request):
        if not operator_socket_allowed(request.scope):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        return {"status": "ready", **deployment_lifecycle.as_dict()}

    @app.post("/internal/drain", include_in_schema=False)
    async def internal_drain(request: Request):
        if not operator_socket_allowed(request.scope):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        return {"status": "draining", **deployment_lifecycle.drain().__dict__}

    @app.post("/internal/undrain", include_in_schema=False)
    async def internal_undrain(request: Request):
        if not operator_socket_allowed(request.scope):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        return {"status": "ready", **deployment_lifecycle.undrain().__dict__}

    # Must remain last: it owns the public homepage/entity HTML routes and the
    # narrow top-level organization fallback.
    from backend.routers import discovery_pages

    app.include_router(discovery_pages.router, tags=["discovery_pages"])

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
