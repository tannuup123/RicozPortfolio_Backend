"""Repository for StrategicGoal database operations."""

import uuid

from sqlalchemy.orm import Session

from app.models.strategic_goal import StrategicGoal


class StrategicGoalRepository:
    """Encapsulates database access for StrategicGoal model."""

    @staticmethod
    def get_by_id_within_org(
        db: Session,
        goal_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> StrategicGoal | None:
        """Retrieve a strategic goal by ID strictly within an organization."""
        return (
            db.query(StrategicGoal)
            .filter(
                StrategicGoal.id == goal_id,
                StrategicGoal.organization_id == organization_id,
            )
            .first()
        )

    @staticmethod
    def list_by_org(
        db: Session,
        organization_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[StrategicGoal], int]:
        """List strategic goals for an organization with pagination and total count."""
        base_query = db.query(StrategicGoal).filter(
            StrategicGoal.organization_id == organization_id
        )
        total = base_query.count()
        goals = (
            base_query.order_by(StrategicGoal.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return goals, total

    @staticmethod
    def create(
        db: Session,
        organization_id: uuid.UUID,
        title: str,
        description: str | None,
    ) -> StrategicGoal:
        """Create a new strategic goal within an organization."""
        goal = StrategicGoal(
            organization_id=organization_id,
            title=title.strip(),
            description=description,
        )
        db.add(goal)
        db.flush()
        return goal

    @staticmethod
    def update(
        db: Session,
        goal: StrategicGoal,
        title: str | None = None,
        description: str | None = None,
    ) -> StrategicGoal:
        """Update scalar attributes on a strategic goal and flush."""
        if title is not None:
            goal.title = title.strip()
        if description is not None:
            goal.description = description
        db.flush()
        return goal

    @staticmethod
    def delete(db: Session, goal: StrategicGoal) -> None:
        """Hard delete a strategic goal."""
        db.delete(goal)
        db.flush()


strategic_goal_repository = StrategicGoalRepository()
