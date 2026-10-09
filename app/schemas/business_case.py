"""Pydantic schemas for BusinessCase operations."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BusinessCaseCreateRequest(BaseModel):
    """POST body — CREATE ONLY. Returns 409 if a BusinessCase already exists."""

    estimated_cost: float = Field(..., ge=0, description="Estimated cost (≥ 0)")
    estimated_benefit: float = Field(..., ge=0, description="Estimated benefit (≥ 0)")


class BusinessCaseUpdateRequest(BaseModel):
    """PATCH body — UPDATE EXISTING. Returns 404 if no BusinessCase exists yet."""

    estimated_cost: float = Field(..., ge=0, description="Estimated cost (≥ 0)")
    estimated_benefit: float = Field(..., ge=0, description="Estimated benefit (≥ 0)")


class BusinessCaseResponse(BaseModel):
    """Business case representation returned by API."""

    id: uuid.UUID
    idea_id: uuid.UUID
    estimated_cost: float
    estimated_benefit: float
    roi: Decimal | float | None = Field(
        None, description="Quantized ROI to 2 decimal places (None if estimated_cost == 0)"
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
