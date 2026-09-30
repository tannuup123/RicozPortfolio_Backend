"""FastAPI dependencies for request handling, authentication, and database access."""

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repository import user_repository

http_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate the JWT access token from the Authorization header and return the current User."""
    unauthorized_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise unauthorized_exc
        user_id = uuid.UUID(user_id_str)
    except (jwt.PyJWTError, ValueError):
        raise unauthorized_exc

    user = user_repository.get_by_id(db, user_id=user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_role(*allowed_roles: str):
    """FastAPI dependency factory enforcing Role-Based Access Control (RBAC).

    Requires authentication via get_current_user.
    - If the user possesses the 'org_admin' role, access is always permitted
      (per mvp-requirements 2.4: org_admin can perform all organizational actions).
    - Otherwise, the user must hold at least one role specified in allowed_roles.
    - If neither condition is met, raises HTTPException 403 Forbidden.
    """

    def _role_checker(current_user: User = Depends(get_current_user)) -> User:
        user_role_names = {r.name for r in current_user.roles}
        if "org_admin" in user_role_names:
            return current_user

        if any(role in user_role_names for role in allowed_roles):
            return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Insufficient permissions",
        )

    return _role_checker

