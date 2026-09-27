from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.api import api_router
from backend.app.core.config import settings

app = FastAPI(
    title="MEMORA API",
    )
app.include_router(api_router, prefix="/api/v1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS
)