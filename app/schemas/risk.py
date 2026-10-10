"""Pydantic schemas for Risk operations (Phase 9)."""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskLevelEnum(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class RiskStatusEnum(str, enum.Enum):
    open = "open"
    mitigated = "mitigated"
    closed = "closed"


class RiskCreateRequest(BaseModel):
    """Payload for creating a new risk entry."""

    title: str = Field(..., min_length=1, max_length=255, description="Risk title")
    description: str | None = Field(None, max_length=5000, description="Optional risk description")
    probability: RiskLevelEnum = Field(RiskLevelEnum.medium, description="Likelihood of occurrence")
    impact: RiskLevelEnum = Field(RiskLevelEnum.medium, description="Severity if it occurs")
    status: RiskStatusEnum = Field(RiskStatusEnum.open, description="Current risk status")

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("title cannot be blank")
        return s


class RiskUpdateRequest(BaseModel):
    """Payload for partially updating a risk.

    Uses model_fields_set to distinguish omitted from explicit null:
    - title omitted       → preserve existing title
    - title: null         → rejected with 422
    - description omitted → preserve existing description
    - description: null   → clears the description
    - Other fields omitted → preserved; explicit value → updated
    """

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    probability: RiskLevelEnum | None = None
    impact: RiskLevelEnum | None = None
    status: RiskStatusEnum | None = None

    @field_validator("title", mode="before")
    @classmethod
    def title_must_not_be_null(cls, v: object) -> object:
        if v is None:
            raise ValueError("title cannot be null; omit the field to keep the existing value")
        if isinstance(v, str) and not v.strip():
            raise ValueError("title cannot be blank")
        return v

    @field_validator("probability", "impact", "status", mode="before")
    @classmethod
    def enum_fields_must_not_be_null(cls, v: object, info) -> object:
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null; omit the field to keep the existing value")
        return v


class RiskResponse(BaseModel):
    """Full representation of a risk entry."""

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    probability: RiskLevelEnum
    impact: RiskLevelEnum
    status: RiskStatusEnum
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RiskListResponse(BaseModel):
    """Paginated list of risks."""

    items: list[RiskResponse]
    total: int
