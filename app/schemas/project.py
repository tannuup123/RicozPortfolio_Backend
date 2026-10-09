"""Pydantic schemas for Project operations (Phase 6 minimal scope)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectConvertRequest(BaseModel):
    """POST body for converting an approved idea to a project."""

    portfolio_id: uuid.UUID | None = Field(
        None, description="Target portfolio ID (optional, must belong to caller's org)"
    )


class ProjectResponse(BaseModel):
    """Project representation returned by API."""

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    status: str
    portfolio_id: uuid.UUID | None
    source_idea_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
