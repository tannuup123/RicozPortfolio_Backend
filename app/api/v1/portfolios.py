"""API routes for Portfolio management (Phase 7)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.portfolio import (
    PortfolioCreateRequest,
    PortfolioDetailResponse,
    PortfolioListResponse,
    PortfolioResponse,
    PortfolioUpdateRequest,
)
from app.services.portfolio_service import portfolio_service

router = APIRouter()


@router.get("", response_model=PortfolioListResponse, status_code=status.HTTP_200_OK)
def list_portfolios(
    limit: int = Query(20, ge=1, le=100, description="Page limit, capped at 100"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioListResponse:
    """Retrieve active portfolios belonging to caller's org. All authenticated roles permitted."""
    items, total = portfolio_service.list_portfolios(
        db=db,
        caller=current_user,
        limit=limit,
        offset=offset,
    )
    return PortfolioListResponse(
        items=[PortfolioResponse.model_validate(p) for p in items],
        total=total,
    )


@router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    payload: PortfolioCreateRequest,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> PortfolioResponse:
    """Create a new portfolio within caller's org (org_admin or portfolio_manager only)."""
    portfolio = portfolio_service.create_portfolio(
        db=db,
        caller=current_user,
        payload=payload,
    )
    return PortfolioResponse.model_validate(portfolio)


@router.get("/{portfolio_id}", response_model=PortfolioDetailResponse, status_code=status.HTTP_200_OK)
def get_portfolio(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioDetailResponse:
    """Retrieve single portfolio with active project count. All authenticated roles permitted."""
    portfolio, project_count = portfolio_service.get_portfolio(
        db=db,
        caller=current_user,
        portfolio_id=portfolio_id,
    )
    resp = PortfolioDetailResponse.model_validate(portfolio)
    resp.project_count = project_count
    return resp


@router.patch("/{portfolio_id}", response_model=PortfolioResponse, status_code=status.HTTP_200_OK)
def update_portfolio(
    portfolio_id: uuid.UUID,
    payload: PortfolioUpdateRequest,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> PortfolioResponse:
    """Update portfolio attributes (org_admin or portfolio_manager only)."""
    portfolio = portfolio_service.update_portfolio(
        db=db,
        caller=current_user,
        portfolio_id=portfolio_id,
        payload=payload,
    )
    return PortfolioResponse.model_validate(portfolio)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete portfolio (org_admin or portfolio_manager only)."""
    portfolio_service.delete_portfolio(
        db=db,
        caller=current_user,
        portfolio_id=portfolio_id,
    )
