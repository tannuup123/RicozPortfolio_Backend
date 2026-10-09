"""Repository for Project database operations (Phase 6 + Phase 7)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.project import Project, ProjectStatus
from app.models.project_member import ProjectMember


class ProjectRepository:
    """Encapsulates database access for Project model."""

    @staticmethod
    def get_by_source_idea_id(db: Session, idea_id: uuid.UUID) -> Project | None:
        """Check if an idea has already been converted to an active project."""
        return (
            db.query(Project)
            .filter(
                Project.source_idea_id == idea_id,
                Project.deleted_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def get_by_id_within_org(
        db: Session,
        project_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Project | None:
        """Retrieve an active project by ID strictly within an organization."""
        return (
            db.query(Project)
            .filter(
                Project.id == project_id,
                Project.organization_id == organization_id,
                Project.deleted_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def get_by_id_within_org_locked(
        db: Session,
        project_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Project | None:
        """Retrieve an active project with a row-level exclusive lock (SELECT FOR UPDATE).

        Used to serialize concurrent manager-altering operations (role update / member removal).
        Callers must be inside an open transaction; the lock is released on commit/rollback.
        """
        return (
            db.query(Project)
            .filter(
                Project.id == project_id,
                Project.organization_id == organization_id,
                Project.deleted_at.is_(None),
            )
            .with_for_update()
            .first()
        )

    @staticmethod
    def create_from_idea(
        db: Session,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        portfolio_id: uuid.UUID | None,
        source_idea_id: uuid.UUID,
    ) -> Project:
        """Create a new project from an approved idea."""
        project = Project(
            organization_id=organization_id,
            name=name.strip(),
            description=description.strip() if isinstance(description, str) else description,
            status=ProjectStatus.planned,
            portfolio_id=portfolio_id,
            source_idea_id=source_idea_id,
        )
        db.add(project)
        db.flush()
        return project

    @staticmethod
    def create(
        db: Session,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        portfolio_id: uuid.UUID | None,
        status: ProjectStatus = ProjectStatus.planned,
    ) -> Project:
        """Create a new direct project (not from idea conversion)."""
        project = Project(
            organization_id=organization_id,
            name=name.strip(),
            description=description.strip() if isinstance(description, str) else description,
            status=status,
            portfolio_id=portfolio_id,
        )
        db.add(project)
        db.flush()
        return project

    @staticmethod
    def list_all_within_org(
        db: Session,
        organization_id: uuid.UUID,
        portfolio_id: uuid.UUID | None = None,
        status: ProjectStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Project], int]:
        """List all active projects in an org (for org_admin / portfolio_manager)."""
        base_query = db.query(Project).filter(
            Project.organization_id == organization_id,
            Project.deleted_at.is_(None),
        )
        if portfolio_id is not None:
            base_query = base_query.filter(Project.portfolio_id == portfolio_id)
        if status is not None:
            base_query = base_query.filter(Project.status == status)
        total = base_query.count()
        items = (
            base_query.order_by(Project.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def list_user_member_projects(
        db: Session,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        portfolio_id: uuid.UUID | None = None,
        status: ProjectStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Project], int]:
        """List active projects a user is a member of (for project_manager / team_member)."""
        base_query = (
            db.query(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .filter(
                Project.organization_id == organization_id,
                Project.deleted_at.is_(None),
                ProjectMember.user_id == user_id,
            )
        )
        if portfolio_id is not None:
            base_query = base_query.filter(Project.portfolio_id == portfolio_id)
        if status is not None:
            base_query = base_query.filter(Project.status == status)
        total = base_query.with_entities(func.count(Project.id)).scalar() or 0
        items = (
            base_query.order_by(Project.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def update(
        db: Session,
        project: Project,
        name: str | None = None,
        description: str | None = None,
        status: ProjectStatus | None = None,
        portfolio_id: uuid.UUID | None = None,
        clear_portfolio: bool = False,
    ) -> Project:
        """Update project fields. clear_portfolio=True sets portfolio_id to None."""
        if name is not None:
            project.name = name.strip()
        if description is not None:
            project.description = description.strip()
        if status is not None:
            project.status = status
        if clear_portfolio:
            project.portfolio_id = None
        elif portfolio_id is not None:
            project.portfolio_id = portfolio_id
        db.flush()
        return project

    @staticmethod
    def soft_delete(db: Session, project: Project) -> Project:
        """Soft-delete a project by setting deleted_at to now."""
        project.deleted_at = datetime.now(timezone.utc)
        db.flush()
        return project


project_repository = ProjectRepository()
