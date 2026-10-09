"""Service layer for Milestone operations (Phase 8)."""

import uuid
from typing import Sequence

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.milestone import Milestone, MilestoneStatus
from app.models.project import Project
from app.models.project_member import ProjectMemberRole
from app.models.user import User
from app.repositories.milestone_repository import milestone_repository
from app.repositories.project_member_repository import project_member_repository
from app.repositories.project_repository import project_repository
from app.schemas.milestone import (
    MilestoneCreateRequest,
    MilestoneStatusEnum,
    MilestoneUpdateRequest,
)


def _get_caller_role_names(caller: User) -> set[str]:
    return {r.name for r in caller.roles}


def _caller_is_broad_manager(caller: User) -> bool:
    roles = _get_caller_role_names(caller)
    return bool(roles & {"org_admin", "portfolio_manager"})


def _require_project_in_org(
    db: Session,
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> Project:
    project = project_repository.get_by_id_within_org(
        db, project_id=project_id, organization_id=organization_id
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return project


def _caller_can_manage_project(
    db: Session,
    caller: User,
    project_id: uuid.UUID,
) -> bool:
    if _caller_is_broad_manager(caller):
        return True
    membership = project_member_repository.get_membership(
        db, project_id=project_id, user_id=caller.id
    )
    return bool(membership and membership.project_role == ProjectMemberRole.manager)


def _caller_can_view_project(
    db: Session,
    caller: User,
    project_id: uuid.UUID,
) -> bool:
    if _caller_is_broad_manager(caller):
        return True
    membership = project_member_repository.get_membership(
        db, project_id=project_id, user_id=caller.id
    )
    return membership is not None


class MilestoneService:
    """Orchestrates business logic, permissions, and validation for milestones."""

    @staticmethod
    def list_milestones(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        status_filter: MilestoneStatusEnum | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[Milestone], int]:
        """List milestones for a project.

        Viewers must have project visibility: org_admin / portfolio_manager or assigned project members.
        """
        _require_project_in_org(db, project_id=project_id, organization_id=caller.organization_id)

        if not _caller_can_view_project(db, caller=caller, project_id=project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You are not a member of this project.",
            )

        domain_status = MilestoneStatus(status_filter.value) if status_filter is not None else None

        return milestone_repository.list_by_project(
            db=db,
            project_id=project_id,
            status=domain_status,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def get_milestone(
        db: Session,
        caller: User,
        milestone_id: uuid.UUID,
    ) -> Milestone:
        """Retrieve a single milestone by ID.

        Accessible to anyone with project visibility.
        """
        milestone = milestone_repository.get_by_id(db, milestone_id=milestone_id)
        if not milestone:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Milestone not found.",
            )

        _require_project_in_org(db, project_id=milestone.project_id, organization_id=caller.organization_id)
        if not _caller_can_view_project(db, caller=caller, project_id=milestone.project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You are not a member of this project.",
            )

        return milestone

    @staticmethod
    def create_milestone(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        payload: MilestoneCreateRequest,
    ) -> Milestone:
        """Create a new milestone within a project.

        Permitted for org_admin, portfolio_manager, or assigned project manager.
        """
        _require_project_in_org(db, project_id=project_id, organization_id=caller.organization_id)

        if not _caller_can_manage_project(db, caller=caller, project_id=project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions to create milestones for this project.",
            )

        milestone = milestone_repository.create(
            db=db,
            project_id=project_id,
            title=payload.title,
            description=payload.description,
            due_date=payload.due_date,
            status=MilestoneStatus(payload.status.value),
        )
        db.commit()
        db.refresh(milestone)
        return milestone

    @staticmethod
    def update_milestone(
        db: Session,
        caller: User,
        milestone_id: uuid.UUID,
        payload: MilestoneUpdateRequest,
    ) -> Milestone:
        """Update milestone attributes.

        Permitted for org_admin, portfolio_manager, or assigned project manager.
        """
        milestone = milestone_repository.get_by_id(db, milestone_id=milestone_id)
        if not milestone:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Milestone not found.",
            )

        _require_project_in_org(db, project_id=milestone.project_id, organization_id=caller.organization_id)

        if not _caller_can_manage_project(db, caller=caller, project_id=milestone.project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions to update milestones for this project.",
            )

        new_title = payload.title if "title" in payload.model_fields_set else None
        clear_desc = ("description" in payload.model_fields_set and payload.description is None)
        new_description = (
            payload.description
            if "description" in payload.model_fields_set and payload.description is not None
            else None
        )
        clear_due_date = ("due_date" in payload.model_fields_set and payload.due_date is None)
        new_due_date = (
            payload.due_date
            if "due_date" in payload.model_fields_set and payload.due_date is not None
            else None
        )
        new_status = MilestoneStatus(payload.status.value) if payload.status is not None else None

        milestone_repository.update(
            db=db,
            milestone=milestone,
            title=new_title,
            description=new_description,
            due_date=new_due_date,
            status=new_status,
            clear_description=clear_desc,
            clear_due_date=clear_due_date,
        )
        db.commit()
        db.refresh(milestone)
        return milestone

    @staticmethod
    def delete_milestone(
        db: Session,
        caller: User,
        milestone_id: uuid.UUID,
    ) -> None:
        """Delete a milestone.

        Permitted for org_admin, portfolio_manager, or assigned project manager.
        """
        milestone = milestone_repository.get_by_id(db, milestone_id=milestone_id)
        if not milestone:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Milestone not found.",
            )

        _require_project_in_org(db, project_id=milestone.project_id, organization_id=caller.organization_id)

        if not _caller_can_manage_project(db, caller=caller, project_id=milestone.project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions to delete milestones for this project.",
            )

        milestone_repository.delete(db, milestone=milestone)
        db.commit()


milestone_service = MilestoneService()
