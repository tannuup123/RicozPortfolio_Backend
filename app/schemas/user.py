"""Pydantic v2 schemas for user management."""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import EMAIL_REGEX, UserResponse


class RoleName(str, Enum):
    """Allowed system roles per MVP specifications."""

    ORG_ADMIN = "org_admin"
    PORTFOLIO_MANAGER = "portfolio_manager"
    PROJECT_MANAGER = "project_manager"
    TEAM_MEMBER = "team_member"


class UserCreateRequest(BaseModel):
    """Payload for creating a new user within caller's organization."""

    email: str = Field(..., pattern=EMAIL_REGEX, max_length=255, description="Unique email address")
    password: str = Field(..., min_length=8, description="Initial password, minimum 8 characters")
    name: str = Field(..., min_length=1, max_length=255, description="Display name of the user")
    roles: Annotated[list[RoleName], Field(min_length=1)] = [RoleName.TEAM_MEMBER]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Name cannot be empty")
        return cleaned


class UserUpdateRolesRequest(BaseModel):
    """Payload for replacing a user's entire role set."""

    roles: Annotated[list[RoleName], Field(min_length=1)]


class UserUpdateRequest(BaseModel):
    """Payload for updating user profile attributes."""

    name: str | None = Field(None, min_length=1, max_length=255)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Name cannot be empty")
            return cleaned
        return v


class UserListResponse(BaseModel):
    """Paginated list of users response."""

    items: list[UserResponse]
    total: int
