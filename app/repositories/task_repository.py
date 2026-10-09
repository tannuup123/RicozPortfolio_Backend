"""Repository for Task database operations (Phase 8)."""

import uuid
from typing import Sequence

from sqlalchemy.orm import Session

from app.models.task import Task, TaskPriority, TaskStatus


class TaskRepository:
    """Encapsulates database access for Task model."""

    @staticmethod
    def get_by_id(db: Session, task_id: uuid.UUID) -> Task | None:
        """Retrieve task by ID."""
        return db.query(Task).filter(Task.id == task_id).first()

    @staticmethod
    def list_by_project(
        db: Session,
        project_id: uuid.UUID,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[Task], int]:
        """List tasks for a project ordered by created_at DESC with filters and pagination."""
        base_query = db.query(Task).filter(Task.project_id == project_id)
        if status is not None:
            base_query = base_query.filter(Task.status == status)
        if priority is not None:
            base_query = base_query.filter(Task.priority == priority)
        if assignee_id is not None:
            base_query = base_query.filter(Task.assignee_id == assignee_id)

        total = base_query.count()
        items = (
            base_query.order_by(Task.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def create(
        db: Session,
        project_id: uuid.UUID,
        title: str,
        description: str | None,
        status: TaskStatus = TaskStatus.todo,
        priority: TaskPriority = TaskPriority.medium,
        assignee_id: uuid.UUID | None = None,
    ) -> Task:
        """Create a new task."""
        task = Task(
            project_id=project_id,
            title=title.strip(),
            description=description.strip() if isinstance(description, str) else description,
            status=status,
            priority=priority,
            assignee_id=assignee_id,
        )
        db.add(task)
        db.flush()
        return task

    @staticmethod
    def update(
        db: Session,
        task: Task,
        title: str | None = None,
        description: str | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: uuid.UUID | None = None,
        clear_description: bool = False,
        clear_assignee: bool = False,
    ) -> Task:
        """Update task fields based on caller mutations."""
        if title is not None:
            task.title = title.strip()
        if clear_description:
            task.description = None
        elif description is not None:
            task.description = description.strip()
        if status is not None:
            task.status = status
        if priority is not None:
            task.priority = priority
        if clear_assignee:
            task.assignee_id = None
        elif assignee_id is not None:
            task.assignee_id = assignee_id

        db.flush()
        return task

    @staticmethod
    def delete(db: Session, task: Task) -> None:
        """Hard-delete a task (no soft-delete column on tasks)."""
        db.delete(task)
        db.flush()


task_repository = TaskRepository()
