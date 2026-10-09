"""Pydantic schemas for Portfolio operations (Phase 7)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PortfolioCreateRequest(BaseModel):
    """POST body for creating a new portfolio."""

    name: str = Field(..., min_length=1, max_length=255, description="Portfolio name")
    description: str | None = Field(None, max_length=5000, description="Optional description")


class PortfolioUpdateRequest(BaseModel):
    """PATCH body for updating a portfolio.

    Uses model_fields_set to distinguish omitted fields from explicitly supplied ones:
    - name omitted        → preserve existing name (no change)
    - name: <string>      → update name (must be 1–255 chars)
    - name: null          → rejected with 422 (portfolios.name is NOT NULL in DB)
    - description omitted → preserve existing description (no change)
    - description: null   → clear description (portfolios.description is nullable)
    - description: <str>  → update description
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)

    @field_validator("name", mode="before")
    @classmethod
    def name_must_not_be_null(cls, v: object) -> object:
        """Reject explicit null for name — the DB column is NOT NULL."""
        # This validator fires only when 'name' is present in the payload.
        # If the payload omits 'name', Pydantic uses the default (None) and
        # model_fields_set will NOT contain 'name', so the service can distinguish
        # omit vs. explicit null via model_fields_set.
        # When 'name' IS explicitly present in JSON and set to null, Pydantic
        # passes None here → we reject it.
        if v is None:
            raise ValueError("name cannot be null; omit the field to keep the existing value")
        return v


class PortfolioResponse(BaseModel):
    """Portfolio representation returned by API (list and basic get)."""

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PortfolioDetailResponse(PortfolioResponse):
    """Portfolio representation with active project count (used for GET single)."""

    project_count: int = 0


class PortfolioListResponse(BaseModel):
    """Paginated list of portfolios."""

    items: list[PortfolioResponse]
    total: int
