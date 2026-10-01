"""Pydantic v2 schemas for Strategic Goal request and response."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrategicGoalCreateRequest(BaseModel):
    """Payload for creating a new strategic goal."""

    title: str = Field(..., min_length=1, max_length=255, description="Goal title")
    description: str | None = Field(None, description="Optional goal description")


class StrategicGoalUpdateRequest(BaseModel):
    """Payload for updating a strategic goal's attributes."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None


class StrategicGoalResponse(BaseModel):
    """Response schema for a single strategic goal."""

    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategicGoalListResponse(BaseModel):
    """Paginated list of strategic goals."""

    items: list[StrategicGoalResponse]
    total: int
