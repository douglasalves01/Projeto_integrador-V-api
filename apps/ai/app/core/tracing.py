"""Optional OpenTelemetry tracing setup."""

from __future__ import annotations

from fastapi import FastAPI
from loguru import logger

from app.core.config import get_settings


def setup_tracing(app: FastAPI) -> None:
    """Instrument FastAPI when OTEL_ENABLED=true."""
    settings = get_settings()
    if not settings.OTEL_ENABLED:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning("OpenTelemetry packages not installed", error=str(exc))
        return

    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": settings.AI_MODEL_VERSION,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_ENDPOINT)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/metrics,/health")

    logger.info(
        "OpenTelemetry tracing enabled",
        endpoint=settings.OTEL_EXPORTER_ENDPOINT,
        service=settings.OTEL_SERVICE_NAME,
    )
