"""One JSON error shape for every failure (US-33): {"code", "message", "details"}."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..config import ConfigError
from ..database import DatabaseError, ThreadAccessError
from .schemas import ErrorBody

log = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details

    def body(self) -> ErrorBody:
        return ErrorBody(code=self.code, message=self.message, details=self.details)


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found.")


def error_for(exc: Exception) -> tuple[int, ErrorBody]:
    """Map any exception to (HTTP status, error body). Shared by the handlers and the SSE stream."""
    if isinstance(exc, ApiError):
        return exc.status, exc.body()
    if isinstance(exc, ThreadAccessError):
        return 404, ErrorBody(code="not_found", message="Conversation not found.")
    if isinstance(exc, DatabaseError):  # before ConfigError: it's a subclass
        return 503, ErrorBody(code="database_unavailable", message=str(exc))
    if isinstance(exc, ConfigError):
        return 503, ErrorBody(code="not_configured", message=str(exc))
    log.exception("Unhandled API error", exc_info=exc)
    return 500, ErrorBody(code="internal_error", message="Something went wrong. Please try again.")


def _json(status: int, body: ErrorBody) -> JSONResponse:
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in e.get("loc", ()) if p != "body"), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return _json(422, ErrorBody(code="validation_error", message="Some fields are invalid.", details=details))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _json(exc.status_code, ErrorBody(code=code, message=str(exc.detail)))

    # Expected errors get their own handlers. A handler for plain `Exception` is Starlette's
    # last-resort 500 handler (it re-raises afterwards), so keep it for real bugs only.
    async def _known(_: Request, exc: Exception) -> JSONResponse:
        return _json(*error_for(exc))

    for cls in (ApiError, ThreadAccessError, ConfigError):  # ConfigError covers DatabaseError
        app.add_exception_handler(cls, _known)

    @app.exception_handler(Exception)
    async def _any(_: Request, exc: Exception) -> JSONResponse:
        return _json(*error_for(exc))
