from fastapi import APIRouter

from api.runtime import runtime
from api.service import service

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    result = service.health()
    result["runtime"] = runtime.snapshot()
    return result
