from fastapi import APIRouter

from api.service import service

router = APIRouter(prefix="/timeline", tags=["timeline"])


@router.get("/{trace_id}")
def timeline(trace_id: str) -> list[dict]:
    return service.get_timeline(trace_id)
