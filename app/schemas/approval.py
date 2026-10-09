"""Pydantic schemas for Approval operations."""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApprovalDecisionEnum(str, enum.Enum):
    """Allowed approval decisions."""

    approved = "approved"
    rejected = "rejected"


class ApprovalCreateRequest(BaseModel):
    """POST body for creating an approval decision."""

    decision: ApprovalDecisionEnum
    notes: str | None = Field(None, max_length=2000, description="Optional reviewer notes")


class ApprovalResponse(BaseModel):
    """Approval decision record representation."""

    id: uuid.UUID
    idea_id: uuid.UUID
    approver_id: uuid.UUID
    decision: ApprovalDecisionEnum
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApprovalListResponse(BaseModel):
    """List response for approval history."""

    items: list[ApprovalResponse]
    total: int
