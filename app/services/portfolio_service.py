"""Service layer for Portfolio operations (Phase 7)."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio
from app.models.user import User
from app.repositories.portfolio_repository import portfolio_repository
from app.schemas.portfolio import PortfolioCreateRequest, PortfolioUpdateRequest


class PortfolioService:
    """Orchestrates business logic and permissions for portfolios."""

    @staticmethod
    def create_portfolio(
        db: Session,
        caller: User,
        payload: PortfolioCreateRequest,
    ) -> Portfolio:
        """Create a new portfolio within the caller's organization.

        Role: portfolio_manager or org_admin (enforced at router level).
        """
        portfolio = portfolio_repository.create(
            db,
            organization_id=caller.organization_id,
            name=payload.name,
            description=payload.description,
        )
        db.commit()
        db.refresh(portfolio)
        return portfolio

    @staticmethod
    def list_portfolios(
        db: Session,
        caller: User,
        limit: int,
        offset: int,
    ) -> tuple[list[Portfolio], int]:
        """List active portfolios in the caller's organization.

        All authenticated users may list portfolios.
        """
        return portfolio_repository.list_within_org(
            db,
            organization_id=caller.organization_id,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def get_portfolio(
        db: Session,
        caller: User,
        portfolio_id: uuid.UUID,
    ) -> tuple[Portfolio, int]:
        """Retrieve a single portfolio with its active project count.

        Returns (portfolio, project_count).  Raises 404 if not found or soft-deleted.
        All authenticated users may view portfolios.
        """
        portfolio = portfolio_repository.get_by_id_within_org(
            db,
            portfolio_id=portfolio_id,
            organization_id=caller.organization_id,
        )
        if not portfolio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found.",
            )
        project_count = portfolio_repository.count_active_projects_by_portfolio(
            db,
            portfolio_id=portfolio_id,
            organization_id=caller.organization_id,
        )
        return portfolio, project_count

    @staticmethod
    def update_portfolio(
        db: Session,
        caller: User,
        portfolio_id: uuid.UUID,
        payload: PortfolioUpdateRequest,
    ) -> Portfolio:
        """Update portfolio name / description.

        Role: portfolio_manager or org_admin (enforced at router level).
        Raises 404 if not found or soft-deleted.

        PATCH semantics (via model_fields_set):
        - name omitted        → preserve existing name
        - name: <string>      → update name  (null already rejected by schema validator)
        - description omitted → preserve existing description
        - description: null   → clear description (set to None)
        - description: <str>  → update description
        """
        portfolio = portfolio_repository.get_by_id_within_org(
            db,
            portfolio_id=portfolio_id,
            organization_id=caller.organization_id,
        )
        if not portfolio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found.",
            )

        new_name = payload.name if "name" in payload.model_fields_set else None
        clear_desc = (
            "description" in payload.model_fields_set and payload.description is None
        )
        new_description = (
            payload.description
            if "description" in payload.model_fields_set and payload.description is not None
            else None
        )

        portfolio_repository.update(
            db,
            portfolio=portfolio,
            name=new_name,
            description=new_description,
            clear_description=clear_desc,
        )
        db.commit()
        db.refresh(portfolio)
        return portfolio

    @staticmethod
    def delete_portfolio(
        db: Session,
        caller: User,
        portfolio_id: uuid.UUID,
    ) -> None:
        """Soft-delete a portfolio.

        Role: portfolio_manager or org_admin (enforced at router level).
        Raises 404 if not found or already soft-deleted.

        Soft-delete semantics:
        - Sets portfolio.deleted_at = now().
        - Associated projects are NOT deleted and retain their portfolio_id FK value.
          The DB ON DELETE SET NULL constraint fires only on physical row deletion;
          soft-deletion is a Python-level operation and does not trigger it.
        - After soft-deletion, GET /portfolios/{id} and GET /portfolios return 404/exclude
          this portfolio.  New project assignments to this UUID also return 404.
        """
        portfolio = portfolio_repository.get_by_id_within_org(
            db,
            portfolio_id=portfolio_id,
            organization_id=caller.organization_id,
        )
        if not portfolio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found.",
            )
        portfolio_repository.soft_delete(db, portfolio)
        db.commit()


portfolio_service = PortfolioService()
