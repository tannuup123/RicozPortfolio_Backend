"""API routes for Milestone management (Phase 8)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.milestone import (
    MilestoneCreateRequest,
    MilestoneListResponse,
    MilestoneResponse,
    MilestoneStatusEnum,
    MilestoneUpdateRequest,
)
from app.services.milestone_service import milestone_service

project_milestones_router = APIRouter()
milestones_router = APIRouter()


# ---------------------------------------------------------------------------
# Project-nested Milestone Endpoints (/api/v1/projects/{project_id}/milestones)
# ---------------------------------------------------------------------------


@project_milestones_router.get("", response_model=MilestoneListResponse, status_code=status.HTTP_200_OK)
def list_project_milestones(
    project_id: uuid.UUID,
    status_filter: MilestoneStatusEnum | None = Query(None, alias="status", description="Filter by milestone status"),
    limit: int = Query(20, ge=1, le=100, description="Page limit, capped at 100"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MilestoneListResponse:
    """List milestones in a project. Accessible to authorized project viewers."""
    items, total = milestone_service.list_milestones(
        db=db,
        caller=current_user,
        project_id=project_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return MilestoneListResponse(
        items=[MilestoneResponse.model_validate(m) for m in items],
        total=total,
    )


@project_milestones_router.post("", response_model=MilestoneResponse, status_code=status.HTTP_201_CREATED)
def create_project_milestone(
    project_id: uuid.UUID,
    payload: MilestoneCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MilestoneResponse:
    """Create a milestone in a project. Accessible to project managers / org admin."""
    milestone = milestone_service.create_milestone(
        db=db,
        caller=current_user,
        project_id=project_id,
        payload=payload,
    )
    return MilestoneResponse.model_validate(milestone)


# ---------------------------------------------------------------------------
# Direct Milestone Endpoints (/api/v1/milestones/{milestone_id})
# ---------------------------------------------------------------------------


@milestones_router.get("/{milestone_id}", response_model=MilestoneResponse, status_code=status.HTTP_200_OK)
def get_milestone(
    milestone_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MilestoneResponse:
    """Retrieve a single milestone by ID. Accessible to authorized project viewers."""
    milestone = milestone_service.get_milestone(
        db=db,
        caller=current_user,
        milestone_id=milestone_id,
    )
    return MilestoneResponse.model_validate(milestone)


@milestones_router.patch("/{milestone_id}", response_model=MilestoneResponse, status_code=status.HTTP_200_OK)
def update_milestone(
    milestone_id: uuid.UUID,
    payload: MilestoneUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MilestoneResponse:
    """Update milestone attributes. Accessible to project managers / org admin."""
    milestone = milestone_service.update_milestone(
        db=db,
        caller=current_user,
        milestone_id=milestone_id,
        payload=payload,
    )
    return MilestoneResponse.model_validate(milestone)


@milestones_router.delete("/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_milestone(
    milestone_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a milestone. Accessible to project managers / org admin."""
    milestone_service.delete_milestone(
        db=db,
        caller=current_user,
        milestone_id=milestone_id,
    )
