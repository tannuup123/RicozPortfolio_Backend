"""Pydantic schemas for Project and ProjectMember operations (Phase 6 + Phase 7).

IMPORTANT: ProjectConvertRequest and ProjectResponse are Phase 6 schemas used by
app/api/v1/ideas.py. They must be preserved exactly to avoid breaking Phase 6 tests.
"""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProjectStatusEnum(str, enum.Enum):
    planned = "planned"
    active = "active"
    on_hold = "on_hold"
    completed = "completed"
    cancelled = "cancelled"


class ProjectMemberRoleEnum(str, enum.Enum):
    manager = "manager"
    member = "member"


# ---------------------------------------------------------------------------
# Phase 7: Project schemas
# ---------------------------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    """Payload for creating a project directly.

    Status is intentionally NOT accepted from the client: per mvp-requirements.md §7.1,
    new projects are ALWAYS created with initial status 'planned'.
    """

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    portfolio_id: uuid.UUID | None = Field(None, description="Optional target portfolio ID")


class ProjectUpdateRequest(BaseModel):
    """PATCH payload for updating project attributes.

    Distinguishes omitted fields from explicit null via model_fields_set:
    - portfolio_id omitted         → current portfolio assignment preserved
    - portfolio_id: null explicitly → project unassigned from portfolio (set to NULL)
    - portfolio_id: <valid UUID>   → project assigned to target portfolio
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    status: ProjectStatusEnum | None = None
    portfolio_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Phase 7: ProjectMember schemas
# ---------------------------------------------------------------------------


class ProjectMemberCreateRequest(BaseModel):
    """Payload for adding a member to a project."""

    user_id: uuid.UUID
    project_role: ProjectMemberRoleEnum = ProjectMemberRoleEnum.member


class ProjectMemberUpdateRequest(BaseModel):
    """Payload for updating a project member's role."""

    project_role: ProjectMemberRoleEnum


class ProjectMemberResponse(BaseModel):
    """Representation of a project membership entry."""

    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    user_email: str
    project_role: ProjectMemberRoleEnum
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectMemberListResponse(BaseModel):
    """Paginated list of project members."""

    items: list[ProjectMemberResponse]
    total: int


# ---------------------------------------------------------------------------
# Phase 7: Project response schemas
# ---------------------------------------------------------------------------


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""

    items: list["ProjectResponse"]
    total: int


class ProjectDetailResponse(BaseModel):
    """Full project details including member list."""

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    status: str
    portfolio_id: uuid.UUID | None
    source_idea_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    members: list[ProjectMemberResponse] = []

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# PRESERVED FROM PHASE 6 — DO NOT MODIFY (used by app/api/v1/ideas.py)
# ---------------------------------------------------------------------------


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
