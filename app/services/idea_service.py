"""Business logic for Idea management."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.idea import Idea, IdeaStatus
from app.models.user import User
from app.repositories.idea_repository import idea_repository
from app.repositories.strategic_goal_repository import strategic_goal_repository
from app.schemas.idea import IdeaCreateRequest, IdeaStatusEnum, IdeaUpdateRequest

VALID_TRANSITIONS: dict[IdeaStatus, set[IdeaStatus]] = {
    IdeaStatus.draft: {IdeaStatus.submitted},
    IdeaStatus.submitted: {IdeaStatus.in_review},
    IdeaStatus.in_review: {IdeaStatus.approved, IdeaStatus.rejected},
    IdeaStatus.approved: set(),
    IdeaStatus.rejected: set(),
}


class IdeaService:
    """Orchestrates business logic and permissions for ideas."""

    @staticmethod
    def list_ideas(
        db: Session,
        organization_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[Idea], int]:
        """Return active ideas scoped to an organization."""
        return idea_repository.list_by_org(
            db, organization_id=organization_id, limit=limit, offset=offset
        )

    @staticmethod
    def get_idea(
        db: Session,
        idea_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Idea:
        """Return an active idea by ID within the organization, or raise 404."""
        idea = idea_repository.get_by_id_within_org(
            db, idea_id=idea_id, organization_id=organization_id
        )
        if not idea:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Idea not found.",
            )
        return idea

    @staticmethod
    def create_idea(
        db: Session,
        caller: User,
        payload: IdeaCreateRequest,
    ) -> Idea:
        """Create a new idea within the caller's organization."""
        # Validate strategic goal if linked
        if payload.strategic_goal_id is not None:
            goal = strategic_goal_repository.get_by_id_within_org(
                db,
                goal_id=payload.strategic_goal_id,
                organization_id=caller.organization_id,
            )
            if not goal:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Strategic goal not found in this organization.",
                )

        # Initial status validation
        initial_status = IdeaStatus.submitted
        if payload.status is not None:
            if payload.status not in (IdeaStatusEnum.draft, IdeaStatusEnum.submitted):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Initial idea status must be 'draft' or 'submitted'.",
                )
            initial_status = IdeaStatus(payload.status.value)

        try:
            idea = idea_repository.create(
                db,
                organization_id=caller.organization_id,
                author_id=caller.id,
                title=payload.title,
                description=payload.description,
                strategic_goal_id=payload.strategic_goal_id,
                status=initial_status,
            )
            db.commit()
            db.refresh(idea)
            return idea
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def update_idea(
        db: Session,
        caller: User,
        idea_id: uuid.UUID,
        payload: IdeaUpdateRequest,
    ) -> Idea:
        """Update an idea's fields according to RBAC and workflow rules."""
        idea = idea_repository.get_by_id_within_org(
            db, idea_id=idea_id, organization_id=caller.organization_id
        )
        if not idea:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Idea not found.",
            )

        caller_roles = {role.name for role in caller.roles}
        is_pm_or_admin = bool(caller_roles.intersection({"org_admin", "portfolio_manager"}))

        # Status transition check
        if payload.status is not None:
            if not is_pm_or_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only portfolio managers and org admins can change idea status.",
                )
            target_status = IdeaStatus(payload.status.value)
            if target_status != idea.status:
                allowed_next = VALID_TRANSITIONS.get(idea.status, set())
                if target_status not in allowed_next:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Invalid status transition from '{idea.status.value}' to "
                            f"'{target_status.value}'."
                        ),
                    )

        # Content edit permissions
        if payload.title is not None or payload.description is not None:
            if not is_pm_or_admin:
                if idea.author_id != caller.id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You can only edit your own ideas.",
                    )
                if idea.status != IdeaStatus.draft:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Ideas can only be edited while in draft status.",
                    )

        try:
            updates = {}
            if payload.title is not None:
                updates["title"] = payload.title
            if payload.description is not None:
                updates["description"] = payload.description
            if payload.status is not None:
                updates["status"] = IdeaStatus(payload.status.value)

            updated = idea_repository.update(db, idea, **updates)
            db.commit()
            db.refresh(updated)
            return updated
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def delete_idea(
        db: Session,
        caller: User,
        idea_id: uuid.UUID,
    ) -> None:
        """Soft delete an idea (portfolio_manager or org_admin only)."""
        idea = idea_repository.get_by_id_within_org(
            db, idea_id=idea_id, organization_id=caller.organization_id
        )
        if not idea:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Idea not found.",
            )

        caller_roles = {role.name for role in caller.roles}
        if not caller_roles.intersection({"org_admin", "portfolio_manager"}):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only portfolio managers and org admins can delete ideas.",
            )

        try:
            idea_repository.soft_delete(db, idea=idea)
            db.commit()
        except Exception:
            db.rollback()
            raise


idea_service = IdeaService()
