"""API routes for Expense management (Phase 9)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.expense import ExpenseCreateRequest, ExpenseListResponse, ExpenseResponse
from app.services.expense_service import expense_service

project_expenses_router = APIRouter()


# ---------------------------------------------------------------------------
# Project-nested Expense Endpoints (/api/v1/projects/{project_id}/expenses)
# ---------------------------------------------------------------------------


@project_expenses_router.get("", response_model=ExpenseListResponse, status_code=status.HTTP_200_OK)
def list_project_expenses(
    project_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100, description="Page limit, capped at 100"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpenseListResponse:
    """List expenses for a project (newest-first by date).

    Accessible to any project member or broad manager.
    """
    items, total = expense_service.list_expenses(
        db=db,
        caller=current_user,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )
    return ExpenseListResponse(
        items=[ExpenseResponse.model_validate(e) for e in items],
        total=total,
    )


@project_expenses_router.post("", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_project_expense(
    project_id: uuid.UUID,
    payload: ExpenseCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpenseResponse:
    """Log a new expense against a project.

    Permitted for project managers or broad managers.
    """
    expense = expense_service.create_expense(
        db=db,
        caller=current_user,
        project_id=project_id,
        payload=payload,
    )
    return ExpenseResponse.model_validate(expense)
