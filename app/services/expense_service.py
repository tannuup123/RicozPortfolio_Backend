"""Service layer for Expense operations (Phase 9)."""

import uuid
from typing import Sequence

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.expense import Expense
from app.models.project import Project
from app.models.project_member import ProjectMemberRole
from app.models.user import User
from app.repositories.expense_repository import expense_repository
from app.repositories.project_member_repository import project_member_repository
from app.repositories.project_repository import project_repository
from app.schemas.expense import ExpenseCreateRequest


def _get_caller_role_names(caller: User) -> set[str]:
    return {r.name for r in caller.roles}


def _caller_is_broad_manager(caller: User) -> bool:
    return bool(_get_caller_role_names(caller) & {"org_admin", "portfolio_manager"})


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


class ExpenseService:
    """Orchestrates business logic, permissions, and validation for expenses."""

    @staticmethod
    def list_expenses(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[Expense], int]:
        """List expenses for a project.

        Accessible to any project member or broad manager.
        """
        _require_project_in_org(db, project_id=project_id, organization_id=caller.organization_id)

        if not _caller_can_view_project(db, caller=caller, project_id=project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You are not a member of this project.",
            )

        return expense_repository.list_by_project(
            db=db,
            project_id=project_id,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def create_expense(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        payload: ExpenseCreateRequest,
    ) -> Expense:
        """Log a new expense against a project.

        Permitted for project managers or broad managers.
        """
        project = _require_project_in_org(db, project_id=project_id, organization_id=caller.organization_id)

        if not _caller_can_manage_project(db, caller=caller, project_id=project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions to log expenses for this project.",
            )

        expense = expense_repository.create(
            db=db,
            project_id=project.id,
            amount=payload.amount,
            description=payload.description,
            expense_date=payload.date,
        )
        db.commit()
        db.refresh(expense)
        return expense


expense_service = ExpenseService()
