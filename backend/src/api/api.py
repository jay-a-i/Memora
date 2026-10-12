# backend/src/api/api.py

from fastapi import APIRouter
from src.api.v1.endpoints import chat
from src.api.v1.endpoints import health
from src.api.v1.endpoints import documents

api_router = APIRouter()

api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(health.router, prefix="/health", tags=["Health"])