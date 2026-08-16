from fastapi import APIRouter

router = APIRouter(prefix="/trust", tags=["trust"])


@router.get("/current")
def current_trust() -> dict:
    return {"status": "UNAVAILABLE", "reason": "trust engine pending M2 integration", "scopes": {}}
