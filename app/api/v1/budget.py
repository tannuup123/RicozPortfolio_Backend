"""API routes for Budget management (Phase 9)."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.budget import BudgetResponse, BudgetUpsertRequest
from app.services.budget_service import budget_service

project_budget_router = APIRouter()


# ---------------------------------------------------------------------------
# Project-nested Budget Endpoints (/api/v1/projects/{project_id}/budget)
# ---------------------------------------------------------------------------


@project_budget_router.get("", response_model=BudgetResponse, status_code=status.HTTP_200_OK)
def get_project_budget(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BudgetResponse:
    """Return the project's planned budget and computed actual spend.

    Returns zero-filled defaults if no budget has been set yet.
    Accessible to any project member or broad manager.
    """
    return budget_service.get_budget(
        db=db,
        caller=current_user,
        project_id=project_id,
    )


@project_budget_router.put("", response_model=BudgetResponse, status_code=status.HTTP_200_OK)
def upsert_project_budget(
    project_id: uuid.UUID,
    payload: BudgetUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BudgetResponse:
    """Create or replace the project's planned budget.

    Idempotent: creates on first call, updates on subsequent calls.
    Permitted for project managers or broad managers (org_admin / portfolio_manager).
    """
    return budget_service.upsert_budget(
        db=db,
        caller=current_user,
        project_id=project_id,
        payload=payload,
    )
