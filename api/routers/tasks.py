from typing import Annotated

from fastapi import APIRouter, Depends

from api.auth import OperatorIdentity
from api.deps import require_operator
from api.service import service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks() -> list[dict]:
    return service.list_tasks()


@router.post("/{task_id}/acknowledge")
def acknowledge(
    task_id: str,
    operator: Annotated[OperatorIdentity, Depends(require_operator)],
) -> dict:
    return service.transition_task(task_id, "ACKNOWLEDGED", operator)


@router.post("/{task_id}/resolve")
def resolve(
    task_id: str,
    operator: Annotated[OperatorIdentity, Depends(require_operator)],
) -> dict:
    return service.transition_task(task_id, "RESOLVED", operator)
