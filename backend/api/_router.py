from api import chat, documents, health
from fastapi import APIRouter

router = APIRouter()

router.include_router(chat.router, prefix="/chat", tags=["Chat"])
router.include_router(documents.router, prefix="/documents", tags=["Documents"])
router.include_router(health.router, prefix="/health", tags=["Health"])