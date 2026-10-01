"""API routes for Strategic Goal management."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.strategic_goal import (
    StrategicGoalCreateRequest,
    StrategicGoalListResponse,
    StrategicGoalResponse,
    StrategicGoalUpdateRequest,
)
from app.services.strategic_goal_service import strategic_goal_service

router = APIRouter()


@router.get("", response_model=StrategicGoalListResponse, status_code=status.HTTP_200_OK)
def list_strategic_goals(
    limit: int = Query(20, ge=1, le=100, description="Page limit, capped at 100"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategicGoalListResponse:
    """Retrieve strategic goals belonging to the caller's organization. All roles permitted."""
    goals, total = strategic_goal_service.list_goals(
        db=db,
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
    )
    return StrategicGoalListResponse(
        items=[StrategicGoalResponse.model_validate(g) for g in goals],
        total=total,
    )


@router.post("", response_model=StrategicGoalResponse, status_code=status.HTTP_201_CREATED)
def create_strategic_goal(
    payload: StrategicGoalCreateRequest,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> StrategicGoalResponse:
    """Create a new strategic goal (org_admin or portfolio_manager only)."""
    goal = strategic_goal_service.create_goal(db=db, caller=current_user, payload=payload)
    return StrategicGoalResponse.model_validate(goal)


@router.get("/{goal_id}", response_model=StrategicGoalResponse, status_code=status.HTTP_200_OK)
def get_strategic_goal(
    goal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategicGoalResponse:
    """Retrieve a single strategic goal by ID within the caller's organization."""
    goal = strategic_goal_service.get_goal(
        db=db,
        goal_id=goal_id,
        organization_id=current_user.organization_id,
    )
    return StrategicGoalResponse.model_validate(goal)


@router.patch("/{goal_id}", response_model=StrategicGoalResponse, status_code=status.HTTP_200_OK)
def update_strategic_goal(
    goal_id: uuid.UUID,
    payload: StrategicGoalUpdateRequest,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> StrategicGoalResponse:
    """Update a strategic goal's title or description (org_admin or portfolio_manager only)."""
    goal = strategic_goal_service.update_goal(
        db=db, caller=current_user, goal_id=goal_id, payload=payload
    )
    return StrategicGoalResponse.model_validate(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategic_goal(
    goal_id: uuid.UUID,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> None:
    """Delete a strategic goal (org_admin or portfolio_manager only)."""
    strategic_goal_service.delete_goal(db=db, caller=current_user, goal_id=goal_id)
