"""API routes for Dashboard endpoints (Phase 10)."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import PortfolioDashboardResponse, ProjectDashboardResponse
from app.services.dashboard_service import dashboard_service

project_dashboard_router = APIRouter()
portfolio_dashboard_router = APIRouter()


@project_dashboard_router.get(
    "",
    response_model=ProjectDashboardResponse,
    status_code=status.HTTP_200_OK,
)
def get_project_dashboard(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectDashboardResponse:
    """Return a live project dashboard snapshot.

    Includes task completion %, budget utilization %, open risk count,
    and a composite health flag.

    Accessible to any project member or broad manager (org_admin /
    portfolio_manager) within the same organization.
    """
    return dashboard_service.get_project_dashboard(
        db=db,
        caller=current_user,
        project_id=project_id,
    )


@portfolio_dashboard_router.get(
    "",
    response_model=PortfolioDashboardResponse,
    status_code=status.HTTP_200_OK,
)
def get_portfolio_dashboard(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioDashboardResponse:
    """Return a portfolio dashboard with a per-project summary list.

    Projects are sorted by name (ascending) and include status,
    budget utilization %, open risk count, and health flag.

    Restricted to org_admin and portfolio_manager.
    """
    return dashboard_service.get_portfolio_dashboard(
        db=db,
        caller=current_user,
        portfolio_id=portfolio_id,
    )
