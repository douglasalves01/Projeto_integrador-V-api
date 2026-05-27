from fastapi import APIRouter

from app.api.routes import admin, health, llm, profile, recommendations, training
from app.api.routes import embeddings

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(recommendations.router)
api_router.include_router(profile.router)
api_router.include_router(training.router)
api_router.include_router(llm.router)
api_router.include_router(admin.router)
api_router.include_router(embeddings.router)
