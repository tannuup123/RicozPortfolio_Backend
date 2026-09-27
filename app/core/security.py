"""Security utilities: password hashing, JWT encoding/decoding, and cookie helpers."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import Response

from app.core.config import settings

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(user_id: uuid.UUID | str, organization_id: uuid.UUID | str) -> str:
    """Generate a signed JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org_id": str(organization_id),
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: uuid.UUID | str, organization_id: uuid.UUID | str) -> str:
    """Generate a signed JWT refresh token with unique jti."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org_id": str(organization_id),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """Decode and validate a JWT token, optionally verifying its token type."""
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    if expected_type and payload.get("type") != expected_type:
        raise jwt.PyJWTError(f"Invalid token type: expected {expected_type}")
    return payload


def get_cookie_secure() -> bool:
    """Determine Secure flag for cookies based on environment config."""
    if settings.ENVIRONMENT == "local":
        return settings.COOKIE_SECURE
    return True


def get_cookie_samesite() -> str:
    """Determine SameSite flag for cookies based on environment config."""
    if settings.ENVIRONMENT == "local":
        return settings.COOKIE_SAMESITE.lower() if settings.COOKIE_SAMESITE else "lax"
    return "none"


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set the httpOnly refresh token cookie on a response."""
    max_age_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=max_age_seconds,
        expires=max_age_seconds,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=get_cookie_secure(),
        samesite=get_cookie_samesite(),
    )


def clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie by setting Max-Age=0 with identical flags."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value="",
        max_age=0,
        expires=0,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=get_cookie_secure(),
        samesite=get_cookie_samesite(),
    )
