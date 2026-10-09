"""API routes for Idea management."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.idea import (
    IdeaCreateRequest,
    IdeaListResponse,
    IdeaResponse,
    IdeaUpdateRequest,
)
from app.schemas.project import ProjectConvertRequest, ProjectResponse
from app.services.idea_service import idea_service

router = APIRouter()


@router.get("", response_model=IdeaListResponse, status_code=status.HTTP_200_OK)
def list_ideas(
    limit: int = Query(20, ge=1, le=100, description="Page limit, capped at 100"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IdeaListResponse:
    """Retrieve active ideas belonging to the caller's organization. All roles permitted."""
    ideas, total = idea_service.list_ideas(
        db=db,
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
    )
    return IdeaListResponse(
        items=[IdeaResponse.model_validate(item) for item in ideas],
        total=total,
    )


@router.post("", response_model=IdeaResponse, status_code=status.HTTP_201_CREATED)
def create_idea(
    payload: IdeaCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IdeaResponse:
    """Submit a new idea. Any authenticated user can submit."""
    idea = idea_service.create_idea(db=db, caller=current_user, payload=payload)
    return IdeaResponse.model_validate(idea)


@router.get("/{idea_id}", response_model=IdeaResponse, status_code=status.HTTP_200_OK)
def get_idea(
    idea_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IdeaResponse:
    """Retrieve an active idea by ID within caller's organization. All roles permitted."""
    idea = idea_service.get_idea(
        db=db,
        idea_id=idea_id,
        organization_id=current_user.organization_id,
    )
    return IdeaResponse.model_validate(idea)


@router.patch("/{idea_id}", response_model=IdeaResponse, status_code=status.HTTP_200_OK)
def update_idea(
    idea_id: uuid.UUID,
    payload: IdeaUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IdeaResponse:
    """Update an idea. Granular permissions enforced by service."""
    idea = idea_service.update_idea(
        db=db,
        caller=current_user,
        idea_id=idea_id,
        payload=payload,
    )
    return IdeaResponse.model_validate(idea)


@router.delete("/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_idea(
    idea_id: uuid.UUID,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> None:
    """Soft delete an idea (portfolio_manager or org_admin only)."""
    idea_service.delete_idea(db=db, caller=current_user, idea_id=idea_id)


@router.post("/{idea_id}/convert", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def convert_idea_to_project(
    idea_id: uuid.UUID,
    payload: ProjectConvertRequest,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Convert an approved idea into a planned Project.

    Only portfolio_manager or org_admin can convert.
    """
    project = idea_service.convert_to_project(
        db=db, caller=current_user, idea_id=idea_id, payload=payload
    )
    return ProjectResponse.model_validate(project)
