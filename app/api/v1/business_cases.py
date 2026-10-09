"""API routes for BusinessCase management."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.business_case import (
    BusinessCaseCreateRequest,
    BusinessCaseResponse,
    BusinessCaseUpdateRequest,
)
from app.services.business_case_service import business_case_service

router = APIRouter()


@router.post("", response_model=BusinessCaseResponse, status_code=status.HTTP_201_CREATED)
def create_business_case(
    idea_id: uuid.UUID,
    payload: BusinessCaseCreateRequest,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> BusinessCaseResponse:
    """Create a new business case for an idea (CREATE ONLY).

    Returns 409 Conflict if a business case already exists for this idea.
    """
    bc = business_case_service.create_business_case(
        db=db, caller=current_user, idea_id=idea_id, payload=payload
    )
    return BusinessCaseResponse.model_validate(bc)


@router.patch("", response_model=BusinessCaseResponse, status_code=status.HTTP_200_OK)
def update_business_case(
    idea_id: uuid.UUID,
    payload: BusinessCaseUpdateRequest,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> BusinessCaseResponse:
    """Update an existing business case for an idea.

    Returns 404 Not Found if no business case exists yet.
    """
    bc = business_case_service.update_business_case(
        db=db, caller=current_user, idea_id=idea_id, payload=payload
    )
    return BusinessCaseResponse.model_validate(bc)


@router.get("", response_model=BusinessCaseResponse, status_code=status.HTTP_200_OK)
def get_business_case(
    idea_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BusinessCaseResponse:
    """Retrieve the business case for an idea. Any authenticated user can read."""
    bc = business_case_service.get_business_case(
        db=db, caller=current_user, idea_id=idea_id
    )
    return BusinessCaseResponse.model_validate(bc)
