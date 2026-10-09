"""Repository for Project database operations (Phase 6 minimal scope)."""

import uuid

from sqlalchemy.orm import Session

from app.models.project import Project, ProjectStatus


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


project_repository = ProjectRepository()
