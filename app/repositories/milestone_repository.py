"""Repository for Milestone database operations (Phase 8)."""

import uuid
from datetime import date
from typing import Sequence

from sqlalchemy.orm import Session

from app.models.milestone import Milestone, MilestoneStatus


class MilestoneRepository:
    """Encapsulates database access for Milestone model."""

    @staticmethod
    def get_by_id(db: Session, milestone_id: uuid.UUID) -> Milestone | None:
        """Retrieve milestone by ID."""
        return db.query(Milestone).filter(Milestone.id == milestone_id).first()

    @staticmethod
    def list_by_project(
        db: Session,
        project_id: uuid.UUID,
        status: MilestoneStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[Milestone], int]:
        """List milestones for a project ordered by due_date ASC NULLS LAST, created_at ASC."""
        base_query = db.query(Milestone).filter(Milestone.project_id == project_id)
        if status is not None:
            base_query = base_query.filter(Milestone.status == status)

        total = base_query.count()
        items = (
            base_query.order_by(Milestone.due_date.asc().nulls_last(), Milestone.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def create(
        db: Session,
        project_id: uuid.UUID,
        title: str,
        description: str | None,
        due_date: date | None,
        status: MilestoneStatus = MilestoneStatus.pending,
    ) -> Milestone:
        """Create a new milestone."""
        milestone = Milestone(
            project_id=project_id,
            title=title.strip(),
            description=description.strip() if isinstance(description, str) else description,
            due_date=due_date,
            status=status,
        )
        db.add(milestone)
        db.flush()
        return milestone

    @staticmethod
    def update(
        db: Session,
        milestone: Milestone,
        title: str | None = None,
        description: str | None = None,
        due_date: date | None = None,
        status: MilestoneStatus | None = None,
        clear_description: bool = False,
        clear_due_date: bool = False,
    ) -> Milestone:
        """Update milestone fields based on caller mutations."""
        if title is not None:
            milestone.title = title.strip()
        if clear_description:
            milestone.description = None
        elif description is not None:
            milestone.description = description.strip()
        if clear_due_date:
            milestone.due_date = None
        elif due_date is not None:
            milestone.due_date = due_date
        if status is not None:
            milestone.status = status

        db.flush()
        return milestone

    @staticmethod
    def delete(db: Session, milestone: Milestone) -> None:
        """Hard-delete a milestone (no soft-delete column on milestones)."""
        db.delete(milestone)
        db.flush()


milestone_repository = MilestoneRepository()
