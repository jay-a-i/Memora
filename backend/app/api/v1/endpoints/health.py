from fastapi import APIRouter

router = APIRouter()

@router.post()
async def check_health() -> dict:
    return {"status": "OK"}