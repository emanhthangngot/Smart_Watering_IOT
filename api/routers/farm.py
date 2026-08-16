from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.auth import OperatorIdentity
from api.deps import require_operator
from api.models import FarmRequest
from api.service import service

router = APIRouter(prefix="/farm", tags=["farm"])


@router.post("/request")
def create_request(
    body: FarmRequest,
    operator: Annotated[OperatorIdentity, Depends(require_operator)],
) -> dict[str, str]:
    return service.create_farm_request(
        intent=body.intent,
        scope=body.scope,
        text=body.text,
        operator=operator,
    )


@router.get("/state")
async def get_state() -> dict:
    return await service.farm_state()


@router.get("/plan/{revision_id}")
def get_plan(revision_id: str) -> dict:
    return service.get_plan(revision_id)
