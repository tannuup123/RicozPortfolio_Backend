"""Pydantic schemas for Budget operations (Phase 9)."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BudgetUpsertRequest(BaseModel):
    """Payload for setting (creating or updating) a project's planned budget."""

    amount: Decimal = Field(
        ...,
        ge=Decimal("0"),
        decimal_places=2,
        description="Planned budget amount (non-negative, 2 decimal places)",
    )
    currency: str = Field(
        "USD",
        min_length=3,
        max_length=3,
        description="ISO 4217 3-letter currency code",
    )

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        s = v.strip().upper()
        if not s.isalpha() or len(s) != 3:
            raise ValueError("currency must be a 3-letter alphabetic ISO currency code")
        return s


class BudgetResponse(BaseModel):
    """Full budget representation including computed actual spend.

    id is None when no budget record has been set yet (GET returns zero defaults).
    """

    id: uuid.UUID | None
    project_id: uuid.UUID
    amount: Decimal
    currency: str
    actual_spend: Decimal
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
