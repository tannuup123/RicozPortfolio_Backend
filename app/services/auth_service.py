"""Authentication service containing registration, login, and token refresh business logic."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.organization_repository import organization_repository
from app.repositories.user_repository import user_repository


class AuthService:
    """Business logic for authentication and onboarding."""

    @staticmethod
    def register(
        db: Session,
        email: str,
        password: str,
        name: str,
        organization_name: str,
    ) -> tuple[User, str, str]:
        """Register a new organization and administrator user in a single transaction."""
        # 1. Check global email uniqueness (409 Conflict)
        existing_user = user_repository.get_by_email(db, email=email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered.",
            )

        # 2. Hash password
        hashed_password = hash_password(password)

        # 3. Create Organization and User within transaction
        try:
            org = organization_repository.create(db, name=organization_name.strip())
            user = user_repository.create_user_with_org_admin(
                db=db,
                email=email,
                hashed_password=hashed_password,
                name=name,
                organization_id=org.id,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        # 4. Generate tokens
        access_token = create_access_token(user_id=user.id, organization_id=user.organization_id)
        refresh_token = create_refresh_token(user_id=user.id, organization_id=user.organization_id)

        return user, access_token, refresh_token

    @staticmethod
    def login(
        db: Session,
        email: str,
        password: str,
    ) -> tuple[User, str, str]:
        """Authenticate user credentials and issue tokens."""
        invalid_credentials_exc = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

        user = user_repository.get_by_email(db, email=email)
        if not user or not user.is_active:
            raise invalid_credentials_exc

        if not verify_password(password, user.hashed_password):
            raise invalid_credentials_exc

        access_token = create_access_token(user_id=user.id, organization_id=user.organization_id)
        refresh_token = create_refresh_token(user_id=user.id, organization_id=user.organization_id)

        return user, access_token, refresh_token

    @staticmethod
    def refresh_tokens(
        db: Session,
        refresh_token: str,
    ) -> tuple[User, str, str]:
        """Validate an existing refresh token and issue a new access token and rotated refresh token."""
        invalid_token_exc = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

        try:
            payload = decode_token(refresh_token, expected_type="refresh")
            user_id_str = payload.get("sub")
            if not user_id_str:
                raise invalid_token_exc
            user_id = uuid.UUID(user_id_str)
        except Exception:
            raise invalid_token_exc

        user = user_repository.get_by_id(db, user_id=user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive.",
            )

        # Issue new access token and rotated (superseding) refresh token
        new_access_token = create_access_token(user_id=user.id, organization_id=user.organization_id)
        new_refresh_token = create_refresh_token(user_id=user.id, organization_id=user.organization_id)

        return user, new_access_token, new_refresh_token


auth_service = AuthService()
