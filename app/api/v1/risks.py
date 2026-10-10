"""API routes for Risk management (Phase 9)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.risk import (
    RiskCreateRequest,
    RiskListResponse,
    RiskResponse,
    RiskStatusEnum,
    RiskUpdateRequest,
)
from app.services.risk_service import risk_service

project_risks_router = APIRouter()
risks_router = APIRouter()


# ---------------------------------------------------------------------------
# Project-nested Risk Endpoints (/api/v1/projects/{project_id}/risks)
# ---------------------------------------------------------------------------


@project_risks_router.get("", response_model=RiskListResponse, status_code=status.HTTP_200_OK)
def list_project_risks(
    project_id: uuid.UUID,
    status_filter: RiskStatusEnum | None = Query(None, alias="status", description="Filter by risk status"),
    limit: int = Query(20, ge=1, le=100, description="Page limit, capped at 100"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RiskListResponse:
    """List risks for a project (newest-first).

    Accessible to any project member or broad manager.
    """
    items, total = risk_service.list_risks(
        db=db,
        caller=current_user,
        project_id=project_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return RiskListResponse(
        items=[RiskResponse.model_validate(r) for r in items],
        total=total,
    )


@project_risks_router.post("", response_model=RiskResponse, status_code=status.HTTP_201_CREATED)
def create_project_risk(
    project_id: uuid.UUID,
    payload: RiskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RiskResponse:
    """Create a new risk entry for a project.

    Permitted for project managers or broad managers.
    """
    risk = risk_service.create_risk(
        db=db,
        caller=current_user,
        project_id=project_id,
        payload=payload,
    )
    return RiskResponse.model_validate(risk)


# ---------------------------------------------------------------------------
# Direct Risk Endpoints (/api/v1/risks/{risk_id})
# ---------------------------------------------------------------------------


@risks_router.get("/{risk_id}", response_model=RiskResponse, status_code=status.HTTP_200_OK)
def get_risk(
    risk_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RiskResponse:
    """Retrieve a single risk by ID. Accessible to project viewers."""
    risk = risk_service.get_risk(
        db=db,
        caller=current_user,
        risk_id=risk_id,
    )
    return RiskResponse.model_validate(risk)


@risks_router.patch("/{risk_id}", response_model=RiskResponse, status_code=status.HTTP_200_OK)
def update_risk(
    risk_id: uuid.UUID,
    payload: RiskUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RiskResponse:
    """Partially update a risk.

    Permitted for project managers or broad managers.
    Omitted fields are preserved; explicit null on description clears it.
    """
    risk = risk_service.update_risk(
        db=db,
        caller=current_user,
        risk_id=risk_id,
        payload=payload,
    )
    return RiskResponse.model_validate(risk)


@risks_router.delete("/{risk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_risk(
    risk_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Hard-delete a risk.

    Permitted for project managers or broad managers.
    """
    risk_service.delete_risk(
        db=db,
        caller=current_user,
        risk_id=risk_id,
    )
