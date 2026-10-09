"""Repository for Portfolio database operations (Phase 6 minimal scope)."""

import uuid

from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio


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


portfolio_repository = PortfolioRepository()
