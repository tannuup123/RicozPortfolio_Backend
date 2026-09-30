"""API routes for User management and RBAC."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.user import (
    UserCreateRequest,
    UserListResponse,
    UserUpdateRequest,
    UserUpdateRolesRequest,
)
from app.services.user_service import user_service

router = APIRouter()


@router.get("", response_model=UserListResponse, status_code=status.HTTP_200_OK)
def list_users(
    limit: int = Query(20, ge=1, le=100, description="Page limit, capped at 100"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserListResponse:
    """Retrieve users belonging to the caller's organization."""
    users, total = user_service.list_users(
        db=db,
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
    )
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    current_user: User = Depends(require_role("org_admin")),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Create a new user within the caller's organization (org_admin only)."""
    user = user_service.create_user(
        db=db,
        caller_organization_id=current_user.organization_id,
        payload=payload,
    )
    return UserResponse.model_validate(user)


@router.patch("/{user_id}/roles", response_model=UserResponse, status_code=status.HTTP_200_OK)
def update_user_roles(
    user_id: uuid.UUID,
    payload: UserUpdateRolesRequest,
    current_user: User = Depends(require_role("org_admin")),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Replace a user's full role set (org_admin only)."""
    user = user_service.update_user_roles(
        db=db,
        caller=current_user,
        target_user_id=user_id,
        new_role_names=[r.value for r in payload.roles],
    )
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Update user profile. org_admin can update anyone's name/is_active; non-admin can only update own name."""
    user = user_service.update_user(
        db=db,
        caller=current_user,
        target_user_id=user_id,
        payload=payload,
    )
    return UserResponse.model_validate(user)
