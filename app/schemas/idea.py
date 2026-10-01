"""Pydantic v2 schemas for Idea request and response."""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IdeaStatusEnum(str, enum.Enum):
    """Lifecycle statuses for an idea."""

    draft = "draft"
    submitted = "submitted"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"


class IdeaCreateRequest(BaseModel):
    """Payload for creating/submitting a new idea."""

    title: str = Field(..., min_length=1, max_length=255, description="Idea title")
    description: str = Field(..., min_length=1, description="Idea description")
    strategic_goal_id: uuid.UUID | None = Field(
        None, description="Optional strategic goal ID to link to"
    )
    status: IdeaStatusEnum | None = Field(
        None,
        description="Optional initial status (draft or submitted, defaults to submitted)",
    )


class IdeaUpdateRequest(BaseModel):
    """Payload for updating an existing idea."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, min_length=1)
    status: IdeaStatusEnum | None = None


class IdeaResponse(BaseModel):
    """Response schema for a single idea."""

    id: uuid.UUID
    organization_id: uuid.UUID
    author_id: uuid.UUID
    title: str
    description: str
    status: IdeaStatusEnum
    strategic_goal_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IdeaListResponse(BaseModel):
    """Paginated list of ideas."""

    items: list[IdeaResponse]
    total: int
