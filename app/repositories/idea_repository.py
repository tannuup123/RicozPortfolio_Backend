"""Repository for Idea database operations."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.idea import Idea, IdeaStatus


class IdeaRepository:
    """Encapsulates database access for Idea model."""

    @staticmethod
    def get_by_id_within_org(
        db: Session,
        idea_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Idea | None:
        """Retrieve an active (non-deleted) idea by ID strictly within an organization."""
        return (
            db.query(Idea)
            .filter(
                Idea.id == idea_id,
                Idea.organization_id == organization_id,
                Idea.deleted_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def list_by_org(
        db: Session,
        organization_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Idea], int]:
        """List active ideas for an organization with pagination and total count."""
        base_query = db.query(Idea).filter(
            Idea.organization_id == organization_id,
            Idea.deleted_at.is_(None),
        )
        total = base_query.count()
        ideas = (
            base_query.order_by(Idea.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return ideas, total

    @staticmethod
    def create(
        db: Session,
        organization_id: uuid.UUID,
        author_id: uuid.UUID,
        title: str,
        description: str,
        strategic_goal_id: uuid.UUID | None = None,
        status: IdeaStatus = IdeaStatus.submitted,
    ) -> Idea:
        """Create a new idea within an organization with default status submitted."""
        idea = Idea(
            organization_id=organization_id,
            author_id=author_id,
            title=title.strip(),
            description=description.strip(),
            strategic_goal_id=strategic_goal_id,
            status=status,
        )
        db.add(idea)
        db.flush()
        return idea

    @staticmethod
    def update(
        db: Session,
        idea: Idea,
        **fields: Any,
    ) -> Idea:
        """Update provided fields on an idea and flush."""
        for field, value in fields.items():
            if value is not None and hasattr(idea, field):
                if isinstance(value, str) and field in {"title", "description"}:
                    value = value.strip()
                setattr(idea, field, value)
        db.flush()
        return idea

    @staticmethod
    def soft_delete(db: Session, idea: Idea) -> None:
        """Soft-delete an idea by setting deleted_at timestamp."""
        idea.deleted_at = datetime.now(timezone.utc)
        db.flush()


idea_repository = IdeaRepository()
