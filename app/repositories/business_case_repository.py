"""Repository for BusinessCase database operations."""

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.business_case import BusinessCase


class BusinessCaseRepository:
    """Encapsulates database access for BusinessCase model."""

    @staticmethod
    def get_by_idea_id(db: Session, idea_id: uuid.UUID) -> BusinessCase | None:
        """Retrieve business case by idea ID.

        Tenant isolation is enforced via idea ownership in the service layer.
        """
        return db.query(BusinessCase).filter(BusinessCase.idea_id == idea_id).first()

    @staticmethod
    def create(
        db: Session,
        idea_id: uuid.UUID,
        estimated_cost: float | Decimal,
        estimated_benefit: float | Decimal,
        roi: Decimal | None = None,
    ) -> BusinessCase:
        """Create a new BusinessCase record."""
        bc = BusinessCase(
            idea_id=idea_id,
            estimated_cost=float(estimated_cost),
            estimated_benefit=float(estimated_benefit),
            roi=roi,
        )
        db.add(bc)
        db.flush()
        return bc

    @staticmethod
    def update(
        db: Session,
        bc: BusinessCase,
        estimated_cost: float | Decimal,
        estimated_benefit: float | Decimal,
        roi: Decimal | None = None,
    ) -> BusinessCase:
        """Update an existing BusinessCase record."""
        bc.estimated_cost = float(estimated_cost)
        bc.estimated_benefit = float(estimated_benefit)
        bc.roi = roi
        db.flush()
        return bc


business_case_repository = BusinessCaseRepository()
