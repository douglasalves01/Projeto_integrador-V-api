"""HTTP middleware: request context, structured logging, Prometheus."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from loguru import logger
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.metrics import record_request


def _resolve_path(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


def _normalize_metric_path(path: str) -> str:
    """Reduce cardinality for Prometheus labels."""
    if path.startswith("/api/v1/recommendations/"):
        return "/api/v1/recommendations/{user_id}"
    if path.startswith("/api/v1/profile/") and path.endswith("/update"):
        return "/api/v1/profile/{user_id}/update"
    if path.startswith("/api/v1/train/status/"):
        return "/api/v1/train/status/{job_id}"
    return path


class RequestContextASGIMiddleware:
    """Pure ASGI middleware (compatible with FastAPI exception handlers)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = None
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                request_id = value.decode()
                break
        if not request_id:
            request_id = str(uuid.uuid4())

        scope.setdefault("state", {})
        if isinstance(scope["state"], dict):
            scope["state"]["request_id"] = request_id

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration_seconds = time.perf_counter() - started
        duration_ms = duration_seconds * 1000
        path = scope.get("path", "/")
        method = scope.get("method", "GET")
        metric_path = _normalize_metric_path(path)
        record_request(method, metric_path, status_code, duration_seconds)

        user_id = None
        state = scope.get("state")
        if isinstance(state, dict):
            user_id = state.get("user_id")

        logger.bind(
            request_id=request_id,
            user_id=user_id,
            method=method,
            path=path,
            status_code=status_code,
            latency_ms=round(duration_ms, 2),
        ).info("request completed")


def register_request_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestContextASGIMiddleware)
