from fastapi import APIRouter
from schemas import HealthCheckResponse

router = APIRouter()

@router.post()
async def check_health() -> dict:
    return HealthCheckResponse(
        status="Healthy",
        database="connected",
        version="1.0.0"
    )