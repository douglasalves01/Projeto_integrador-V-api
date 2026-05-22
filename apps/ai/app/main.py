from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes import health, metrics
from app.core.cache import close_redis
from app.core.config import get_settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.metrics import set_model_metrics
from app.core.middleware import register_request_middleware
from app.core.tracing import setup_tracing
from app.schemas.health import DetailedHealthResponse
from app.services.model_loader import model_loader

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    from loguru import logger

    logger.info(
        "Starting VOD AI service",
        app_name=settings.APP_NAME,
        model_version=settings.AI_MODEL_VERSION,
        model_path=settings.MODEL_PATH,
        otel_enabled=settings.OTEL_ENABLED,
    )

    model_loader.load()
    app.state.models = model_loader.as_dict()
    app.state.models_loaded = model_loader.is_loaded
    app.state.model_version = model_loader.current_model_version
    set_model_metrics(model_loader.current_model_version, model_loader.is_loaded)

    if settings.LLM_ENABLED:
        try:
            from app.core.database import SessionLocal
            from app.services import catalog_loader, llm_recommendation_service as llmsvc

            llmsvc.load_llm_models(load_vodchat=settings.VODCHAT_ENABLED)
            with SessionLocal() as db:
                catalog = catalog_loader.load_catalog_from_db(db)
            llmsvc.update_catalog(catalog)
            logger.info("LLM models loaded", catalog_items=len(catalog))
        except Exception as exc:
            logger.warning(
                "LLM models not loaded; classic recommender remains available",
                error=str(exc),
            )

    yield

    await close_redis()
    logger.info("VOD AI service shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.AI_MODEL_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

register_exception_handlers(app)
setup_tracing(app)

register_request_middleware(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics.router)
app.include_router(health.router)
app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/health", response_model=DetailedHealthResponse, include_in_schema=False)
async def root_health(request: Request) -> DetailedHealthResponse:
    """Root health endpoint for Docker HEALTHCHECK."""
    return await health.build_health_response(request)
