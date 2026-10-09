"""Repository for Portfolio database operations (Phase 6 + Phase 7)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio
from app.models.project import Project


class PortfolioRepository:
    """Encapsulates database access for Portfolio model."""

    @staticmethod
    def get_by_id_within_org(
        db: Session,
        portfolio_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Portfolio | None:
        """Retrieve an active portfolio by ID strictly within an organization."""
        return (
            db.query(Portfolio)
            .filter(
                Portfolio.id == portfolio_id,
                Portfolio.organization_id == organization_id,
                Portfolio.deleted_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def list_within_org(
        db: Session,
        organization_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Portfolio], int]:
        """List active portfolios for an organization, ordered by created_at DESC."""
        base_query = db.query(Portfolio).filter(
            Portfolio.organization_id == organization_id,
            Portfolio.deleted_at.is_(None),
        )
        total = base_query.count()
        items = (
            base_query.order_by(Portfolio.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def create(
        db: Session,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
    ) -> Portfolio:
        """Create a new portfolio within an organization."""
        portfolio = Portfolio(
            organization_id=organization_id,
            name=name.strip(),
            description=description.strip() if isinstance(description, str) else description,
        )
        db.add(portfolio)
        db.flush()
        return portfolio

    @staticmethod
    def update(
        db: Session,
        portfolio: Portfolio,
        name: str | None,
        description: str | None,
        clear_description: bool = False,
    ) -> Portfolio:
        """Mutate portfolio fields based on which arguments are supplied.

        - name:              if not None, overwrite portfolio.name
        - description:       if not None and not clearing, overwrite portfolio.description
        - clear_description: if True, set portfolio.description = None
        """
        if name is not None:
            portfolio.name = name.strip()
        if clear_description:
            portfolio.description = None
        elif description is not None:
            portfolio.description = description.strip()
        db.flush()
        return portfolio

    @staticmethod
    def soft_delete(db: Session, portfolio: Portfolio) -> Portfolio:
        """Soft-delete a portfolio by setting deleted_at to now."""
        portfolio.deleted_at = datetime.now(timezone.utc)
        db.flush()
        return portfolio

    @staticmethod
    def count_active_projects_by_portfolio(
        db: Session,
        portfolio_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> int:
        """Count active (non-deleted) projects assigned to a portfolio within an org."""
        return (
            db.query(func.count(Project.id))
            .filter(
                Project.portfolio_id == portfolio_id,
                Project.organization_id == organization_id,
                Project.deleted_at.is_(None),
            )
            .scalar()
            or 0
        )


portfolio_repository = PortfolioRepository()
