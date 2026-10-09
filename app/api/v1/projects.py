"""API routes for Project and ProjectMember management (Phase 7)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.project import ProjectStatus
from app.models.user import User
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectMemberCreateRequest,
    ProjectMemberListResponse,
    ProjectMemberResponse,
    ProjectMemberUpdateRequest,
    ProjectResponse,
    ProjectStatusEnum,
    ProjectUpdateRequest,
)
from app.services.project_service import project_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Project Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ProjectListResponse, status_code=status.HTTP_200_OK)
def list_projects(
    portfolio_id: uuid.UUID | None = Query(None, description="Filter by portfolio ID"),
    status_filter: ProjectStatusEnum | None = Query(None, alias="status", description="Filter by project status"),
    limit: int = Query(20, ge=1, le=100, description="Page limit, capped at 100"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectListResponse:
    """List projects with dual-tier visibility filter.

    - org_admin / portfolio_manager: view all projects in the org.
    - project_manager / team_member: view only projects they are a member of.
    """
    domain_status = ProjectStatus(status_filter.value) if status_filter is not None else None
    items, total = project_service.list_projects(
        db=db,
        caller=current_user,
        portfolio_id=portfolio_id,
        filter_status=domain_status,
        limit=limit,
        offset=offset,
    )
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in items],
        total=total,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreateRequest,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Create a project directly (org_admin or portfolio_manager only).

    Initial status is always 'planned'. Atomically assigns the creator as project manager.
    """
    project = project_service.create_project(
        db=db,
        caller=current_user,
        payload=payload,
    )
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectDetailResponse, status_code=status.HTTP_200_OK)
def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectDetailResponse:
    """Retrieve single project with its member list.

    Accessible to org_admin, portfolio_manager, or assigned project members.
    """
    project, members = project_service.get_project(
        db=db,
        caller=current_user,
        project_id=project_id,
    )
    resp = ProjectDetailResponse.model_validate(project)
    resp.members = members
    return resp


@router.patch("/{project_id}", response_model=ProjectResponse, status_code=status.HTTP_200_OK)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Update project attributes.

    Permitted for org_admin, portfolio_manager, or project's assigned manager.
    """
    project = project_service.update_project(
        db=db,
        caller=current_user,
        project_id=project_id,
        payload=payload,
    )
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(require_role("portfolio_manager")),
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete a project (org_admin or portfolio_manager only)."""
    project_service.delete_project(
        db=db,
        caller=current_user,
        project_id=project_id,
    )


# ---------------------------------------------------------------------------
# Project Member Endpoints
# ---------------------------------------------------------------------------


@router.get("/{project_id}/members", response_model=ProjectMemberListResponse, status_code=status.HTTP_200_OK)
def list_project_members(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectMemberListResponse:
    """List all members of a project.

    Accessible to org_admin, portfolio_manager, or assigned project members.
    """
    members = project_service.list_members(
        db=db,
        caller=current_user,
        project_id=project_id,
    )
    return ProjectMemberListResponse(items=members, total=len(members))


@router.post("/{project_id}/members", response_model=ProjectMemberResponse, status_code=status.HTTP_201_CREATED)
def add_project_member(
    project_id: uuid.UUID,
    payload: ProjectMemberCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectMemberResponse:
    """Add a member to a project.

    Permitted for org_admin, portfolio_manager, or project's assigned manager.
    """
    return project_service.add_member(
        db=db,
        caller=current_user,
        project_id=project_id,
        payload=payload,
    )


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberResponse, status_code=status.HTTP_200_OK)
def update_project_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ProjectMemberUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectMemberResponse:
    """Update a project member's role (manager or member).

    Permitted for org_admin, portfolio_manager, or project's assigned manager.
    Guarded against demoting the last manager via row-level lock.
    """
    return project_service.update_member_role(
        db=db,
        caller=current_user,
        project_id=project_id,
        target_user_id=user_id,
        payload=payload,
    )


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Remove a member from a project.

    Permitted for org_admin, portfolio_manager, or project's assigned manager.
    Guarded against removing the last manager via row-level lock.
    """
    project_service.remove_member(
        db=db,
        caller=current_user,
        project_id=project_id,
        target_user_id=user_id,
    )
