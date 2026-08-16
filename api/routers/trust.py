from fastapi import APIRouter

from api.service import service

router = APIRouter(prefix="/trust", tags=["trust"])


@router.get("/current")
def current_trust() -> dict:
    verdicts = service.scope_verdicts()
    return {
        "status": "OK" if verdicts else "UNAVAILABLE",
        "verdicts": verdicts,
    }
