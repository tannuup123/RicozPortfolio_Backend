"""Service layer for Task operations (Phase 8)."""

import uuid
from typing import Sequence

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_member import ProjectMemberRole
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.repositories.project_member_repository import project_member_repository
from app.repositories.project_repository import project_repository
from app.repositories.task_repository import task_repository
from app.repositories.user_repository import user_repository
from app.schemas.task import (
    TaskCreateRequest,
    TaskPriorityEnum,
    TaskStatusEnum,
    TaskUpdateRequest,
)


def _get_caller_role_names(caller: User) -> set[str]:
    return {r.name for r in caller.roles}


def _caller_is_broad_manager(caller: User) -> bool:
    roles = _get_caller_role_names(caller)
    return bool(roles & {"org_admin", "portfolio_manager"})


def _require_project_in_org(
    db: Session,
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> Project:
    project = project_repository.get_by_id_within_org(
        db, project_id=project_id, organization_id=organization_id
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return project


def _caller_can_manage_project(
    db: Session,
    caller: User,
    project_id: uuid.UUID,
) -> bool:
    if _caller_is_broad_manager(caller):
        return True
    membership = project_member_repository.get_membership(
        db, project_id=project_id, user_id=caller.id
    )
    return bool(membership and membership.project_role == ProjectMemberRole.manager)


def _caller_can_view_project(
    db: Session,
    caller: User,
    project_id: uuid.UUID,
) -> bool:
    if _caller_is_broad_manager(caller):
        return True
    membership = project_member_repository.get_membership(
        db, project_id=project_id, user_id=caller.id
    )
    return membership is not None


class TaskService:
    """Orchestrates business logic, permissions, and validation for tasks."""

    @staticmethod
    def list_tasks(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        status_filter: TaskStatusEnum | None = None,
        priority_filter: TaskPriorityEnum | None = None,
        assignee_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[Task], int]:
        """List tasks for a project.

        Viewers must have project visibility: org_admin / portfolio_manager or assigned project members.
        """
        _require_project_in_org(db, project_id=project_id, organization_id=caller.organization_id)

        if not _caller_can_view_project(db, caller=caller, project_id=project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You are not a member of this project.",
            )

        domain_status = TaskStatus(status_filter.value) if status_filter is not None else None
        domain_priority = TaskPriority(priority_filter.value) if priority_filter is not None else None

        return task_repository.list_by_project(
            db=db,
            project_id=project_id,
            status=domain_status,
            priority=domain_priority,
            assignee_id=assignee_id,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def get_task(
        db: Session,
        caller: User,
        task_id: uuid.UUID,
    ) -> Task:
        """Retrieve a single task by ID.

        Accessible to anyone with project visibility.
        """
        task = task_repository.get_by_id(db, task_id=task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found.",
            )

        # Enforce org isolation and project visibility
        _require_project_in_org(db, project_id=task.project_id, organization_id=caller.organization_id)
        if not _caller_can_view_project(db, caller=caller, project_id=task.project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You are not a member of this project.",
            )

        return task

    @staticmethod
    def create_task(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        payload: TaskCreateRequest,
    ) -> Task:
        """Create a new task within a project.

        Permitted for org_admin, portfolio_manager, or assigned project manager.
        Validates assignee belongs to the same org and is active (if assignee provided).
        """
        _require_project_in_org(db, project_id=project_id, organization_id=caller.organization_id)

        if not _caller_can_manage_project(db, caller=caller, project_id=project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions to create tasks for this project.",
            )

        if payload.assignee_id is not None:
            assignee = user_repository.get_by_id_within_org(
                db, user_id=payload.assignee_id, organization_id=caller.organization_id
            )
            if not assignee or not assignee.is_active:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assignee user not found in your organization.",
                )

        task = task_repository.create(
            db=db,
            project_id=project_id,
            title=payload.title,
            description=payload.description,
            status=TaskStatus(payload.status.value),
            priority=TaskPriority(payload.priority.value),
            assignee_id=payload.assignee_id,
        )
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def update_task(
        db: Session,
        caller: User,
        task_id: uuid.UUID,
        payload: TaskUpdateRequest,
    ) -> Task:
        """Update task attributes.

        Permissions:
        - org_admin, portfolio_manager, or project's manager: full edit rights.
        - team_member assigned to this task: may ONLY update status.
          If a team_member attempts to modify title, description, priority, or assignee, raise 403 Forbidden.
        - Any other user: 403 Forbidden.
        """
        task = task_repository.get_by_id(db, task_id=task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found.",
            )

        _require_project_in_org(db, project_id=task.project_id, organization_id=caller.organization_id)

        can_manage = _caller_can_manage_project(db, caller=caller, project_id=task.project_id)
        is_assigned = (task.assignee_id == caller.id)

        if not can_manage:
            if not is_assigned:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: You can only update tasks assigned to you.",
                )

            # Assignee team member: verify only status is being changed
            disallowed_fields = {"title", "description", "priority", "assignee_id"} & payload.model_fields_set
            if disallowed_fields:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: Team members may only update task status.",
                )

        # Handle full/partial updates
        new_title = payload.title if "title" in payload.model_fields_set else None
        clear_desc = ("description" in payload.model_fields_set and payload.description is None)
        new_description = (
            payload.description
            if "description" in payload.model_fields_set and payload.description is not None
            else None
        )
        new_status = TaskStatus(payload.status.value) if payload.status is not None else None
        new_priority = TaskPriority(payload.priority.value) if payload.priority is not None else None

        clear_assignee = False
        new_assignee_id: uuid.UUID | None = None
        if "assignee_id" in payload.model_fields_set:
            if payload.assignee_id is None:
                clear_assignee = True
            else:
                assignee = user_repository.get_by_id_within_org(
                    db, user_id=payload.assignee_id, organization_id=caller.organization_id
                )
                if not assignee or not assignee.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Assignee user not found in your organization.",
                    )
                new_assignee_id = payload.assignee_id

        task_repository.update(
            db=db,
            task=task,
            title=new_title,
            description=new_description,
            status=new_status,
            priority=new_priority,
            assignee_id=new_assignee_id,
            clear_description=clear_desc,
            clear_assignee=clear_assignee,
        )
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def delete_task(
        db: Session,
        caller: User,
        task_id: uuid.UUID,
    ) -> None:
        """Delete a task.

        Permitted for org_admin, portfolio_manager, or project's manager.
        """
        task = task_repository.get_by_id(db, task_id=task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found.",
            )

        _require_project_in_org(db, project_id=task.project_id, organization_id=caller.organization_id)

        if not _caller_can_manage_project(db, caller=caller, project_id=task.project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions to delete tasks for this project.",
            )

        task_repository.delete(db, task=task)
        db.commit()


task_service = TaskService()
