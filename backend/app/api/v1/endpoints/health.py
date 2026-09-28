from typing import Dict
from fastapi import APIRouter, Depends
from backend.app.core.security import verify_api_hitter
from backend.app.core.database import check_db_health
from backend.app.core.config import settings
from backend.schemas import HealthCheckResponse

router = APIRouter()

@router.get("/",
    response_model=HealthCheckResponse,
)
async def check_health(
    _oauth: str = Depends(verify_api_hitter),
) -> Dict[str, str]:
    
    db_info = await check_db_health()

    return HealthCheckResponse(
        status="Healthy",
        database=db_info,
        version=settings.BACKEND_VERSION
    )