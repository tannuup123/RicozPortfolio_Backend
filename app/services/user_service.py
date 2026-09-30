"""User service encapsulating business rules for user management and RBAC."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.repositories.role_repository import role_repository
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreateRequest, UserUpdateRequest


class UserService:
    """Service layer managing users, tenant isolation, and administrative controls."""

    @staticmethod
    def list_users(
        db: Session,
        organization_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """List users belonging strictly to the specified organization."""
        return user_repository.list_by_org(
            db, organization_id=organization_id, limit=limit, offset=offset
        )

    @staticmethod
    def create_user(
        db: Session,
        caller_organization_id: uuid.UUID,
        payload: UserCreateRequest,
    ) -> User:
        """Create a user within the caller's organization.

        Ensures global email uniqueness and maps roles.
        """
        existing_user = user_repository.get_by_email(db, email=payload.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered.",
            )

        # Resolve role objects from database
        role_names = [r.value for r in payload.roles]
        roles = role_repository.get_by_names(db, names=role_names)
        if len(roles) != len(role_names):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more specified roles do not exist.",
            )

        hashed_pwd = hash_password(payload.password)
        try:
            user = user_repository.create_user_in_org(
                db=db,
                email=payload.email,
                hashed_password=hashed_pwd,
                name=payload.name,
                organization_id=caller_organization_id,
                role_ids=[r.id for r in roles],
            )
            db.commit()
            return user
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def update_user_roles(
        db: Session,
        caller: User,
        target_user_id: uuid.UUID,
        new_role_names: list[str],
    ) -> User:
        """Replace the complete role set of a user within the caller's organization.

        Enforces tenant isolation and lockout protection.
        """
        target_user = user_repository.get_by_id_within_org(
            db, user_id=target_user_id, organization_id=caller.organization_id
        )
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        # Lockout protection: Cannot remove org_admin role if this user is the last active org_admin
        target_current_roles = {r.name for r in target_user.roles}
        is_currently_admin = "org_admin" in target_current_roles
        is_retaining_admin = "org_admin" in new_role_names

        if target_user.is_active and is_currently_admin and not is_retaining_admin:
            active_admin_count = user_repository.count_active_org_admins(
                db, organization_id=caller.organization_id
            )
            if active_admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove org_admin role from the last active organization administrator.",
                )

        roles = role_repository.get_by_names(db, names=new_role_names)
        if len(roles) != len(new_role_names):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more specified roles do not exist.",
            )

        try:
            user_repository.set_user_roles(
                db, user_id=target_user.id, role_ids=[r.id for r in roles]
            )
            db.commit()
            db.expire(target_user, ["roles"])
            _ = target_user.roles
            return target_user
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def update_user(
        db: Session,
        caller: User,
        target_user_id: uuid.UUID,
        payload: UserUpdateRequest,
    ) -> User:
        """Update user profile attributes (name, is_active).

        Enforces tenant isolation, self-service permission restrictions, and lockout protection.
        """
        target_user = user_repository.get_by_id_within_org(
            db, user_id=target_user_id, organization_id=caller.organization_id
        )
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        caller_roles = {r.name for r in caller.roles}
        is_caller_admin = "org_admin" in caller_roles

        # Permission checks
        if not is_caller_admin:
            if caller.id != target_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: Cannot update other users.",
                )
            if payload.is_active is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: Only administrators can modify active status.",
                )

        # Lockout protection: Cannot deactivate the last active org_admin
        target_roles = {r.name for r in target_user.roles}
        if payload.is_active is False and "org_admin" in target_roles and target_user.is_active:
            active_admin_count = user_repository.count_active_org_admins(
                db, organization_id=caller.organization_id
            )
            if active_admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot deactivate the last active organization administrator.",
                )

        try:
            updated_user = user_repository.update_user(
                db,
                user=target_user,
                name=payload.name,
                is_active=payload.is_active,
            )
            db.commit()
            return updated_user
        except Exception:
            db.rollback()
            raise


user_service = UserService()
