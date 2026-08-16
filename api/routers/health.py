from fastapi import APIRouter

from api.runtime import runtime
from api.service import service

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    result = await service.health()
    result["runtime"] = runtime.snapshot()
    return result
