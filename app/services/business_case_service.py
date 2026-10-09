"""Business logic for BusinessCase operations."""

import uuid
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.business_case import BusinessCase
from app.models.user import User
from app.repositories.business_case_repository import business_case_repository
from app.repositories.idea_repository import idea_repository
from app.schemas.business_case import BusinessCaseCreateRequest, BusinessCaseUpdateRequest


class BusinessCaseService:
    """Orchestrates business logic and validations for business cases."""

    @staticmethod
    def _compute_roi(cost_val: float, benefit_val: float) -> Decimal | None:
        """Compute ROI with deterministic Decimal arithmetic quantized to 2 decimal places."""
        if cost_val == 0:
            return None
        cost = Decimal(str(cost_val))
        benefit = Decimal(str(benefit_val))
        raw_roi = (benefit - cost) / cost
        return raw_roi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def create_business_case(
        db: Session,
        caller: User,
        idea_id: uuid.UUID,
        payload: BusinessCaseCreateRequest,
    ) -> BusinessCase:
        """Create a new BusinessCase.

        Enforces idea existence within caller's organization and ensures single BC per idea (409 on duplicate).
        """
        idea = idea_repository.get_by_id_within_org(
            db, idea_id=idea_id, organization_id=caller.organization_id
        )
        if not idea:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Idea not found.",
            )

        existing = business_case_repository.get_by_idea_id(db, idea_id=idea_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A business case already exists for this idea.",
            )

        roi = BusinessCaseService._compute_roi(payload.estimated_cost, payload.estimated_benefit)

        try:
            bc = business_case_repository.create(
                db,
                idea_id=idea_id,
                estimated_cost=payload.estimated_cost,
                estimated_benefit=payload.estimated_benefit,
                roi=roi,
            )
            db.commit()
            db.refresh(bc)
            return bc
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def update_business_case(
        db: Session,
        caller: User,
        idea_id: uuid.UUID,
        payload: BusinessCaseUpdateRequest,
    ) -> BusinessCase:
        """Update an existing BusinessCase.

        Returns 404 if no business case exists yet.
        """
        idea = idea_repository.get_by_id_within_org(
            db, idea_id=idea_id, organization_id=caller.organization_id
        )
        if not idea:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Idea not found.",
            )

        bc = business_case_repository.get_by_idea_id(db, idea_id=idea_id)
        if not bc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No business case found for this idea.",
            )

        roi = BusinessCaseService._compute_roi(payload.estimated_cost, payload.estimated_benefit)

        try:
            updated_bc = business_case_repository.update(
                db,
                bc=bc,
                estimated_cost=payload.estimated_cost,
                estimated_benefit=payload.estimated_benefit,
                roi=roi,
            )
            db.commit()
            db.refresh(updated_bc)
            return updated_bc
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_business_case(
        db: Session,
        caller: User,
        idea_id: uuid.UUID,
    ) -> BusinessCase:
        """Retrieve a business case for an idea within caller's organization."""
        idea = idea_repository.get_by_id_within_org(
            db, idea_id=idea_id, organization_id=caller.organization_id
        )
        if not idea:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Idea not found.",
            )

        bc = business_case_repository.get_by_idea_id(db, idea_id=idea_id)
        if not bc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No business case found for this idea.",
            )

        return bc


business_case_service = BusinessCaseService()
