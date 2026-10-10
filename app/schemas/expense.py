"""Pydantic schemas for Expense operations (Phase 9)."""

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExpenseCreateRequest(BaseModel):
    """Payload for creating a new expense entry against a project."""

    amount: Decimal = Field(
        ...,
        gt=Decimal("0"),
        decimal_places=2,
        description="Expense amount (must be positive, 2 decimal places)",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Short description of the expense",
    )
    date: dt.date = Field(..., description="Date the expense was incurred (YYYY-MM-DD)")

    @field_validator("description")
    @classmethod
    def description_not_blank(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("description cannot be blank")
        return s


class ExpenseResponse(BaseModel):
    """Representation of a single expense."""

    id: uuid.UUID
    project_id: uuid.UUID
    amount: Decimal
    description: str
    date: dt.date
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseListResponse(BaseModel):
    """Paginated list of expenses."""

    items: list[ExpenseResponse]
    total: int
