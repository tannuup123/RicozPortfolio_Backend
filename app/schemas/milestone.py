"""Pydantic schemas for Milestone operations (Phase 8)."""

import enum
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MilestoneStatusEnum(str, enum.Enum):
    pending = "pending"
    achieved = "achieved"
    missed = "missed"


class MilestoneCreateRequest(BaseModel):
    """Payload for creating a milestone in a project."""

    title: str = Field(..., min_length=1, max_length=255, description="Milestone title")
    description: str | None = Field(None, max_length=5000, description="Optional milestone description")
    due_date: date | None = Field(None, description="Optional due date (YYYY-MM-DD)")
    status: MilestoneStatusEnum = Field(MilestoneStatusEnum.pending, description="Milestone status")


class MilestoneUpdateRequest(BaseModel):
    """Payload for updating milestone attributes.

    Uses model_fields_set to distinguish omitted fields from explicit nulls:
    - title omitted         → preserve existing title
    - title: null           → rejected with 422 (milestones.title is NOT NULL)
    - description omitted   → preserve existing description
    - description: null     → clear description
    - due_date omitted      → preserve existing due date
    - due_date: null        → clear due date
    - status omitted        → preserve existing status
    """

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    due_date: date | None = None
    status: MilestoneStatusEnum | None = None

    @field_validator("title", mode="before")
    @classmethod
    def title_must_not_be_null(cls, v: object) -> object:
        if v is None:
            raise ValueError("title cannot be null; omit the field to keep the existing value")
        return v


class MilestoneResponse(BaseModel):
    """Representation of a milestone."""

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    due_date: date | None
    status: MilestoneStatusEnum
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MilestoneListResponse(BaseModel):
    """Paginated list of milestones."""

    items: list[MilestoneResponse]
    total: int
