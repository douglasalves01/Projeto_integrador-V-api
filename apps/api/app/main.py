from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Inicializa cliente do servico de IA do monorepo (apps/ai)
    if settings.AI_ENABLED:
        from app.integrations.ai_client import init_ai_client
        init_ai_client(
            base_url=settings.AI_SERVICE_URL,
            api_key=settings.AI_SERVICE_API_KEY or None,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # Import and include routers
    from app.routers import auth_router, user_router, video_router, genre_router
    from app.routers import category_router, plan_router, favorite_router
    from app.routers import watch_session_router, interaction_router
    from app.routers import recommendation_router, report_router

    app.include_router(auth_router.router, prefix="/auth", tags=["Auth"])
    app.include_router(user_router.router, prefix="/users", tags=["Users"])
    app.include_router(video_router.router, prefix="/videos", tags=["Videos"])
    app.include_router(genre_router.router, prefix="/genres", tags=["Genres"])
    app.include_router(category_router.router, prefix="/categories", tags=["Categories"])
    app.include_router(plan_router.router, prefix="/plans", tags=["Plans"])
    app.include_router(favorite_router.router, prefix="/favorites", tags=["Favorites"])
    app.include_router(watch_session_router.router, tags=["Watch Sessions"])
    app.include_router(interaction_router.router, prefix="/admin", tags=["Interactions"])
    app.include_router(recommendation_router.router, tags=["Recommendations"])
    app.include_router(report_router.router, prefix="/admin/reports", tags=["Reports"])

    return app


app = create_app()
