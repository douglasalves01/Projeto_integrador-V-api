"""Global FastAPI exception handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.exc import OperationalError, TimeoutError

from app.core.config import get_settings
from app.core.exceptions import AppError, DatabaseTimeoutError

settings = get_settings()


def _request_context(request: Request) -> dict:
    return {
        "request_id": getattr(request.state, "request_id", None),
        "user_id": getattr(request.state, "user_id", None),
        "path": request.url.path,
        "method": request.method,
    }


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    message = str(exc).lower()
    return any(token in message for token in ("timeout", "timed out", "time out", "lock wait timeout"))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        log_fn = logger.warning if exc.status_code < 500 else logger.error
        log_fn("application error", error=exc.detail, status_code=exc.status_code, **_request_context(request))
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(OperationalError)
    async def database_operational_handler(request: Request, exc: OperationalError) -> JSONResponse:
        if _is_timeout_error(exc):
            logger.error("database timeout", error=str(exc), **_request_context(request))
            timeout = DatabaseTimeoutError()
            return JSONResponse(status_code=timeout.status_code, content={"detail": timeout.detail})
        logger.exception("database operational error", **_request_context(request))
        return JSONResponse(status_code=500, content={"detail": "Database error"})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled exception", **_request_context(request))
        detail = str(exc) if settings.DEBUG else "Internal server error"
        return JSONResponse(status_code=500, content={"detail": detail})
