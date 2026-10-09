"""Pydantic schemas for Task operations (Phase 8)."""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskStatusEnum(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class TaskPriorityEnum(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TaskCreateRequest(BaseModel):
    """Payload for creating a task in a project."""

    title: str = Field(..., min_length=1, max_length=255, description="Task title")
    description: str | None = Field(None, max_length=5000, description="Optional task description")
    status: TaskStatusEnum = Field(TaskStatusEnum.todo, description="Task status")
    priority: TaskPriorityEnum = Field(TaskPriorityEnum.medium, description="Task priority")
    assignee_id: uuid.UUID | None = Field(None, description="Optional assignee user ID")


class TaskUpdateRequest(BaseModel):
    """Payload for updating task attributes.

    Uses model_fields_set to distinguish omitted fields from explicit nulls:
    - title omitted         → preserve existing title
    - title: null           → rejected with 422 (tasks.title is NOT NULL)
    - description omitted   → preserve existing description
    - description: null     → clear description
    - status omitted        → preserve existing status
    - priority omitted      → preserve existing priority
    - assignee_id omitted   → preserve existing assignee
    - assignee_id: null     → clear assignee
    """

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    status: TaskStatusEnum | None = None
    priority: TaskPriorityEnum | None = None
    assignee_id: uuid.UUID | None = None

    @field_validator("title", mode="before")
    @classmethod
    def title_must_not_be_null(cls, v: object) -> object:
        if v is None:
            raise ValueError("title cannot be null; omit the field to keep the existing value")
        return v


class TaskResponse(BaseModel):
    """Representation of a task."""

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    status: TaskStatusEnum
    priority: TaskPriorityEnum
    assignee_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    """Paginated list of tasks."""

    items: list[TaskResponse]
    total: int
