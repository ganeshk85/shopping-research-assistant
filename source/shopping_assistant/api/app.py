"""FastAPI application (Sprint 7): the web app's backend.

    create_app()                 -> FastAPI app with all routes under /api/v1
    export_openapi(path)         -> writes the spec the TypeScript client is generated from

Run it with `shopping-assistant api serve` (binds to 127.0.0.1 only).
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic.json_schema import models_json_schema

from ..config import PROJECT_ROOT, ConfigError, Settings, load_settings
from ..tools.notifier import Notifier
from . import routes_checks, routes_settings, routes_threads, routes_watchlist
from .deps import MonitorFactory, Services, SessionFactory, get_services
from .errors import install_error_handlers
from .schemas import Health, StreamEvent

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
API_VERSION = "1.0.0"
# Where the generated TypeScript client reads the spec from (source/packages/api-client).
DEFAULT_OPENAPI_PATH = PROJECT_ROOT / "packages" / "api-client" / "openapi.json"

system = APIRouter(tags=["system"])


@system.get("/health", response_model=Health, summary="Is the API (and its database) up?")
def health(services: Services = Depends(get_services)) -> Health:
    """Always 200 while the API runs; `database` says whether PostgreSQL is reachable."""
    try:
        with services.database().connection() as conn:
            conn.execute("SELECT 1")
        return Health(database="ok")
    except ConfigError:  # includes DatabaseError (unreachable) and a missing DATABASE_URL
        return Health(database="unavailable")


def create_app(
    settings: Optional[Settings] = None,
    *,
    session_factory: Optional[SessionFactory] = None,
    monitor_factory: Optional[MonitorFactory] = None,
    notifier_factory: Optional[Callable[[Settings], Notifier]] = None,
) -> FastAPI:
    settings = settings or load_settings()
    services = Services(settings, session_factory, monitor_factory, notifier_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:  # apply pending migrations; if the DB is down, start anyway and report it via /health
            services.database().migrate()
        except ConfigError as exc:
            log.warning("Database not available at start-up: %s", exc)
        yield
        services.shutdown()  # waits for a check started from the API to finish

    app = FastAPI(
        title="Shopping Research Assistant API",
        version=API_VERSION,
        summary="Research products, track Canadian prices, get drop alerts. Never purchases anything.",
        lifespan=lifespan,
    )
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.web_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    install_error_handlers(app)
    for router in (system, routes_threads.router, routes_watchlist.router, routes_checks.router, routes_settings.router):
        app.include_router(router, prefix=API_PREFIX)
    app.openapi = lambda: _openapi(app)  # type: ignore[method-assign]
    return app


def _openapi(app: FastAPI) -> dict:
    """The generated spec plus the SSE event models (FastAPI can't infer a stream's schema)."""
    if app.openapi_schema:
        return app.openapi_schema
    spec = get_openapi(title=app.title, version=app.version, summary=app.summary, routes=app.routes)
    schemas = spec.setdefault("components", {}).setdefault("schemas", {})
    _, defs = models_json_schema([(StreamEvent, "serialization")], ref_template="#/components/schemas/{model}")
    schemas.update(defs.get("$defs", {}))
    # Validation errors are returned as ErrorBody (see errors.py), not FastAPI's default shape.
    error_ref = {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorBody"}}}
    for operation in (op for ops in spec["paths"].values() for op in ops.values()):
        if "422" in operation["responses"]:
            operation["responses"]["422"] = {"description": "Invalid input", "content": error_ref}
    for unused in ("HTTPValidationError", "ValidationError"):
        schemas.pop(unused, None)
    app.openapi_schema = spec
    return spec


def openapi_json(app: Optional[FastAPI] = None) -> str:
    """Stable text form of the spec (what gets committed and diffed)."""
    app = app or create_app(_spec_settings())
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def _spec_settings() -> Settings:
    # The spec doesn't depend on keys or the database; don't read .env just to build it.
    from dataclasses import replace

    return replace(load_settings(), database_url="")


def export_openapi(path: Path = DEFAULT_OPENAPI_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(openapi_json(), encoding="utf-8")
    return path
