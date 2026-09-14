from fastapi import FastAPI
from backend.app.api.api import api_router

app = FastAPI(title="MEMORA API")

app.include_router(api_router, prefix="/api/v1")