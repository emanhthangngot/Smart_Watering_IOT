import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import OperatorIdentity
from api.deps import require_operator
from api.models import SimCommand
from api.service import service

router = APIRouter(prefix="/sim", tags=["sim"])


@router.post("/{operation}")
def simulator_command(
    operation: str,
    body: SimCommand,
    operator: Annotated[OperatorIdentity, Depends(require_operator)],
) -> dict:
    if os.environ.get("ACTUATION_TARGET", "none") != "sim":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="simulator disabled")
    return service.submit_sim_command(operation, body.command_id, body.params, operator)
