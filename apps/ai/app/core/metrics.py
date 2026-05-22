"""Prometheus metrics for the AI service."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

HTTP_REQUESTS_TOTAL = Counter(
    "vod_ai_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "vod_ai_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 2.5, 5.0),
)

MODEL_LOADED = Gauge(
    "vod_ai_model_loaded",
    "Whether recommendation models are loaded (1=yes, 0=no)",
)

MODEL_INFO = Info("vod_ai_model", "Deployed model metadata")


def record_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    status = str(status_code)
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration_seconds)


def set_model_metrics(version: str, loaded: bool) -> None:
    MODEL_LOADED.set(1 if loaded else 0)
    MODEL_INFO.info({"version": version, "loaded": str(loaded).lower()})
