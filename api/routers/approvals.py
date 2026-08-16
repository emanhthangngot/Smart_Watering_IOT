from typing import Annotated

from fastapi import APIRouter, Depends

from api.auth import OperatorIdentity
from api.deps import require_operator
from api.models import ApprovalRequest
from api.service import service

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("/{plan_revision_id}/approve")
def approve(
    plan_revision_id: str,
    body: ApprovalRequest,
    operator: Annotated[OperatorIdentity, Depends(require_operator)],
) -> dict:
    return service.decide_approval(
        plan_revision_id=plan_revision_id,
        revision_hash=body.revision_hash,
        decision="APPROVE",
        comment=body.comment,
        operator=operator,
    )


@router.post("/{plan_revision_id}/reject")
def reject(
    plan_revision_id: str,
    body: ApprovalRequest,
    operator: Annotated[OperatorIdentity, Depends(require_operator)],
) -> dict:
    return service.decide_approval(
        plan_revision_id=plan_revision_id,
        revision_hash=body.revision_hash,
        decision="REJECT",
        comment=body.comment,
        operator=operator,
    )
