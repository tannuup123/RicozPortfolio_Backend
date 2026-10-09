"""API routes for Task management (Phase 8)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.task import (
    TaskCreateRequest,
    TaskListResponse,
    TaskPriorityEnum,
    TaskResponse,
    TaskStatusEnum,
    TaskUpdateRequest,
)
from app.services.task_service import task_service

project_tasks_router = APIRouter()
tasks_router = APIRouter()


# ---------------------------------------------------------------------------
# Project-nested Task Endpoints (/api/v1/projects/{project_id}/tasks)
# ---------------------------------------------------------------------------


@project_tasks_router.get("", response_model=TaskListResponse, status_code=status.HTTP_200_OK)
def list_project_tasks(
    project_id: uuid.UUID,
    status_filter: TaskStatusEnum | None = Query(None, alias="status", description="Filter by task status"),
    priority_filter: TaskPriorityEnum | None = Query(None, alias="priority", description="Filter by task priority"),
    assignee_id: uuid.UUID | None = Query(None, description="Filter by assignee user ID"),
    limit: int = Query(20, ge=1, le=100, description="Page limit, capped at 100"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskListResponse:
    """List tasks in a project. Accessible to authorized project viewers."""
    items, total = task_service.list_tasks(
        db=db,
        caller=current_user,
        project_id=project_id,
        status_filter=status_filter,
        priority_filter=priority_filter,
        assignee_id=assignee_id,
        limit=limit,
        offset=offset,
    )
    return TaskListResponse(
        items=[TaskResponse.model_validate(t) for t in items],
        total=total,
    )


@project_tasks_router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_project_task(
    project_id: uuid.UUID,
    payload: TaskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Create a task in a project. Accessible to project managers / org admin."""
    task = task_service.create_task(
        db=db,
        caller=current_user,
        project_id=project_id,
        payload=payload,
    )
    return TaskResponse.model_validate(task)


# ---------------------------------------------------------------------------
# Direct Task Endpoints (/api/v1/tasks/{task_id})
# ---------------------------------------------------------------------------


@tasks_router.get("/{task_id}", response_model=TaskResponse, status_code=status.HTTP_200_OK)
def get_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Retrieve a single task by ID. Accessible to authorized project viewers."""
    task = task_service.get_task(
        db=db,
        caller=current_user,
        task_id=task_id,
    )
    return TaskResponse.model_validate(task)


@tasks_router.patch("/{task_id}", response_model=TaskResponse, status_code=status.HTTP_200_OK)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Update task attributes.

    - Project managers / org admins: full update.
    - Assigned team members: status update only (other fields reject with 403).
    """
    task = task_service.update_task(
        db=db,
        caller=current_user,
        task_id=task_id,
        payload=payload,
    )
    return TaskResponse.model_validate(task)


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a task. Accessible to project managers / org admin."""
    task_service.delete_task(
        db=db,
        caller=current_user,
        task_id=task_id,
    )
