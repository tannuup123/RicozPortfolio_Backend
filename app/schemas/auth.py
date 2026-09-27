"""Pydantic v2 schemas for authentication requests and responses."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    """Payload for registering a new organization and administrator."""

    email: str = Field(..., pattern=EMAIL_REGEX, max_length=255, description="Valid user email address")
    password: str = Field(..., min_length=8, description="Minimum 8 characters password")
    name: str = Field(..., min_length=1, max_length=255, description="User full display name")
    organization_name: str = Field(..., min_length=1, max_length=255, description="Organization name")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class LoginRequest(BaseModel):
    """Payload for user login."""

    email: str = Field(..., pattern=EMAIL_REGEX, max_length=255)
    password: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    """Response returning an access token."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Profile data for the authenticated user."""

    id: uuid.UUID
    email: str
    name: str
    organization_id: uuid.UUID
    roles: list[str]

    model_config = ConfigDict(from_attributes=True)

    @field_validator("roles", mode="before")
    @classmethod
    def extract_role_names(cls, v: Any) -> list[str]:
        """Convert list of Role model objects or strings into list of string role names."""
        if not v:
            return []
        role_names: list[str] = []
        for role in v:
            if hasattr(role, "name"):
                role_names.append(str(role.name))
            else:
                role_names.append(str(role))
        return role_names


class MessageResponse(BaseModel):
    """Simple confirmation message response."""

    message: str
