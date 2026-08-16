from fastapi import APIRouter

from api.service import service

router = APIRouter(prefix="/explain", tags=["explain"])


@router.get("/{decision_id}")
def explain(decision_id: str) -> dict:
    return service.get_explanation(decision_id)
