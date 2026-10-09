import logging

from fastapi import APIRouter, Depends, Response, status

from src.core.config import settings
from src.core.database import check_db_health
from src.core.security import verify_api_hitter
from backend.src.schemas.common_schemas import HealthCheckResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/",
    response_model=HealthCheckResponse,
    summary="Service and database health",
)
async def check_health(
    response: Response,
    _auth: str = Depends(verify_api_hitter),
) -> HealthCheckResponse:
    """
    Reports service and database health.

    Returns 503 when the database is unreachable so orchestrators and load
    balancers can act on the status code rather than parsing the body.
    """
    db_info = await check_db_health()
    healthy = db_info.get("status") == "healthy"

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning("Health check failed: %s", db_info)

    return HealthCheckResponse(
        status="healthy" if healthy else "unhealthy",
        database=db_info,
        version=settings.BACKEND_VERSION,
    )
