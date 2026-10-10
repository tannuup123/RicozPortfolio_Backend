"""Service layer for Budget operations (Phase 9)."""

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_member import ProjectMemberRole
from app.models.user import User
from app.repositories.budget_repository import budget_repository
from app.repositories.project_member_repository import project_member_repository
from app.repositories.project_repository import project_repository
from app.schemas.budget import BudgetResponse, BudgetUpsertRequest


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


def _build_budget_response(
    project_id: uuid.UUID,
    db: Session,
    budget=None,
) -> BudgetResponse:
    """Build a BudgetResponse, computing actual_spend from expenses.

    If budget is None (not yet set), returns zero-filled defaults.
    """
    actual = budget_repository.get_actual_spend(db, project_id=project_id)
    if budget is None:
        return BudgetResponse(
            id=None,
            project_id=project_id,
            amount=Decimal("0.00"),
            currency="USD",
            actual_spend=actual,
            created_at=None,
            updated_at=None,
        )
    return BudgetResponse(
        id=budget.id,
        project_id=budget.project_id,
        amount=Decimal(str(budget.amount)),
        currency=budget.currency,
        actual_spend=actual,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


class BudgetService:
    """Orchestrates business logic, permissions, and validation for project budgets."""

    @staticmethod
    def get_budget(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
    ) -> BudgetResponse:
        """Return the project's budget with computed actual spend.

        Accessible to any project member or broad manager.
        Returns zero-filled defaults if no budget has been set yet.
        """
        project = _require_project_in_org(db, project_id=project_id, organization_id=caller.organization_id)

        if not _caller_can_view_project(db, caller=caller, project_id=project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You are not a member of this project.",
            )

        budget = budget_repository.get_by_project_id(db, project_id=project.id)
        return _build_budget_response(project_id=project.id, db=db, budget=budget)

    @staticmethod
    def upsert_budget(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        payload: BudgetUpsertRequest,
    ) -> BudgetResponse:
        """Create or update the project's planned budget.

        Permitted for project managers (membership.project_role==manager) or broad managers.
        """
        project = _require_project_in_org(db, project_id=project_id, organization_id=caller.organization_id)

        if not _caller_can_manage_project(db, caller=caller, project_id=project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions to set budget for this project.",
            )

        existing = budget_repository.get_by_project_id(db, project_id=project.id)
        if existing is None:
            budget = budget_repository.create(
                db=db,
                project_id=project.id,
                amount=payload.amount,
                currency=payload.currency,
            )
        else:
            budget = budget_repository.update(
                db=db,
                budget=existing,
                amount=payload.amount,
                currency=payload.currency,
            )

        db.commit()
        db.refresh(budget)
        return _build_budget_response(project_id=project.id, db=db, budget=budget)


budget_service = BudgetService()
