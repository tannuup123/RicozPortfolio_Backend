"""API routes for Approval management."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.approval import (
    ApprovalCreateRequest,
    ApprovalListResponse,
    ApprovalResponse,
)
from app.services.approval_service import approval_service

router = APIRouter()


@router.post("", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
def create_approval(
    idea_id: uuid.UUID,
    payload: ApprovalCreateRequest,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> ApprovalResponse:
    """Record an approval or rejection decision and atomically update Idea status.

    Only portfolio_manager or org_admin can approve or reject ideas.
    Approver ID is taken strictly from authenticated user.
    """
    approval, _ = approval_service.create_approval(
        db=db, caller=current_user, idea_id=idea_id, payload=payload
    )
    return ApprovalResponse.model_validate(approval)


@router.get("", response_model=ApprovalListResponse, status_code=status.HTTP_200_OK)
def list_approvals(
    idea_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApprovalListResponse:
    """Retrieve chronological approval history for an idea. Any authenticated user can read."""
    approvals = approval_service.list_approvals(
        db=db, caller=current_user, idea_id=idea_id
    )
    return ApprovalListResponse(
        items=[ApprovalResponse.model_validate(item) for item in approvals],
        total=len(approvals),
    )
