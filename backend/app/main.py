"""Application entry point: logging, workbook loading at startup, CORS, routers, error handling."""
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging_config import configure_logging, request_id_var
from app.exceptions.errors import WorkbookError
from app.exceptions.handlers import register_exception_handlers
from app.repositories.workbook_repository import WorkbookRepository
from app.services.dataset_registry import DatasetRegistry
from app.services.document_registry import DocumentRegistry
from app.services.workbook_refresh_service import WorkbookRefreshService
from app.services.monitoring_service import MonitoringService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting %s (env=%s)", settings.app_name, settings.app_env)
    try:
        workbook_path = Path(settings.workbook_path)
        # If workbook missing, try to restore from embedded base64
        if not workbook_path.exists():
            try:
                from app import workbook_data
                import base64
                workbook_path.parent.mkdir(parents=True, exist_ok=True)
                data = base64.b64decode(workbook_data.WORKBOOK_B64)
                with open(workbook_path, 'wb') as f:
                    f.write(data)
                logger.info("Restored workbook from embedded data to %s", workbook_path)
            except Exception as exc:
                logger.warning("Failed to restore embedded workbook: %s", exc)
        repository = WorkbookRepository.load(workbook_path)
    except WorkbookError as exc:
        logger.error("Startup aborted - workbook problem: %s", exc)
        raise
    app.state.repository = repository
    app.state.workbook_refresh = WorkbookRefreshService(
        Path(settings.workbook_path), repository, enabled=settings.workbook_auto_refresh
    )
    app.state.dataset_registry = DatasetRegistry(repository)
    app.state.document_registry = DocumentRegistry()
    
    # Start automatic monitoring and run an initial scan.
    monitoring = MonitoringService(
        settings=settings,
        history_path=(
            settings.upload_dir.parent
            / "monitoring"
            / "monitoring_state.json"
        ),
        interval_seconds=300,
    )
    app.state.monitoring = monitoring

    await monitoring.start(app.state.document_registry)
    try:
        yield
    finally:
        monitoring = getattr(app.state, "monitoring", None)
        if monitoring is not None:
            await monitoring.stop()

        logger.info("Shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Deterministic query API over the employee leave workbook.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Dataset-Id"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        # Reuse a caller-provided ID when present so logs can be correlated
        # across services, otherwise generate one for this request. The value
        # lives in this request's async context, so streaming tasks keep it.
        # Attach a request ID to logs so related events are easier to trace.
        request_id = request.headers.get("X-Request-ID") or uuid4().hex[:12]
        request_id_var.set(request_id)
        started = time.perf_counter()
        response = await call_next(request)
        monitoring = getattr(request.app.state, "monitoring", None)

        if monitoring is not None:
           if response.status_code >= 500:
               monitoring.record_event(
                   "api.server_error",
                   "high",
                   f"{request.method} {request.url.path} returned "
                   f"HTTP {response.status_code}.",
               )
           elif response.status_code == 429:
               monitoring.record_event(
                   "api.rate_limited",
                   "medium",
                   f"{request.method} {request.url.path} returned HTTP 429.",
               )    
        response.headers["X-Request-ID"] = request_id
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("%s %s -> %d (%.1f ms)", request.method, request.url.path,
                    response.status_code, elapsed_ms)
        return response

    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
