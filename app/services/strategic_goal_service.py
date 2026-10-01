"""Business logic for StrategicGoal management."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.strategic_goal import StrategicGoal
from app.models.user import User
from app.repositories.strategic_goal_repository import strategic_goal_repository
from app.schemas.strategic_goal import StrategicGoalCreateRequest, StrategicGoalUpdateRequest


class StrategicGoalService:
    """Orchestrates business logic for strategic goals."""

    @staticmethod
    def list_goals(
        db: Session,
        organization_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[StrategicGoal], int]:
        """Return paginated strategic goals scoped to an organization."""
        return strategic_goal_repository.list_by_org(
            db, organization_id=organization_id, limit=limit, offset=offset
        )

    @staticmethod
    def get_goal(
        db: Session,
        goal_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> StrategicGoal:
        """Return a strategic goal by ID within the organization, or raise 404."""
        goal = strategic_goal_repository.get_by_id_within_org(
            db, goal_id=goal_id, organization_id=organization_id
        )
        if not goal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategic goal not found.",
            )
        return goal

    @staticmethod
    def create_goal(
        db: Session,
        caller: User,
        payload: StrategicGoalCreateRequest,
    ) -> StrategicGoal:
        """Create a new strategic goal within the caller's organization."""
        try:
            goal = strategic_goal_repository.create(
                db,
                organization_id=caller.organization_id,
                title=payload.title,
                description=payload.description,
            )
            db.commit()
            db.refresh(goal)
            return goal
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def update_goal(
        db: Session,
        caller: User,
        goal_id: uuid.UUID,
        payload: StrategicGoalUpdateRequest,
    ) -> StrategicGoal:
        """Update a strategic goal's attributes within the caller's organization."""
        goal = strategic_goal_repository.get_by_id_within_org(
            db, goal_id=goal_id, organization_id=caller.organization_id
        )
        if not goal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategic goal not found.",
            )
        try:
            updated = strategic_goal_repository.update(
                db,
                goal=goal,
                title=payload.title,
                description=payload.description,
            )
            db.commit()
            db.refresh(updated)
            return updated
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def delete_goal(
        db: Session,
        caller: User,
        goal_id: uuid.UUID,
    ) -> None:
        """Hard delete a strategic goal within the caller's organization."""
        goal = strategic_goal_repository.get_by_id_within_org(
            db, goal_id=goal_id, organization_id=caller.organization_id
        )
        if not goal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategic goal not found.",
            )
        try:
            strategic_goal_repository.delete(db, goal=goal)
            db.commit()
        except Exception:
            db.rollback()
            raise


strategic_goal_service = StrategicGoalService()
