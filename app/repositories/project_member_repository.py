"""Repository for ProjectMember database operations (Phase 7)."""

import uuid

from sqlalchemy.orm import Session

from app.models.project_member import ProjectMember, ProjectMemberRole
from app.models.user import User


class ProjectMemberRepository:
    """Encapsulates database access for ProjectMember model."""

    @staticmethod
    def get_membership(
        db: Session,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ProjectMember | None:
        """Retrieve a specific project membership row."""
        return (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
            .first()
        )

    @staticmethod
    def list_by_project(
        db: Session,
        project_id: uuid.UUID,
    ) -> list[tuple[ProjectMember, User]]:
        """Return all (ProjectMember, User) pairs for a project, ordered by join date."""
        return (
            db.query(ProjectMember, User)
            .join(User, ProjectMember.user_id == User.id)
            .filter(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.created_at.asc())
            .all()
        )

    @staticmethod
    def create_member(
        db: Session,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        project_role: ProjectMemberRole,
    ) -> ProjectMember:
        """Create a new project membership record."""
        member = ProjectMember(
            project_id=project_id,
            user_id=user_id,
            project_role=project_role,
        )
        db.add(member)
        db.flush()
        return member

    @staticmethod
    def update_role(
        db: Session,
        member: ProjectMember,
        project_role: ProjectMemberRole,
    ) -> ProjectMember:
        """Update the role of an existing project membership."""
        member.project_role = project_role
        db.flush()
        return member

    @staticmethod
    def delete_member(db: Session, member: ProjectMember) -> None:
        """Hard-delete a project membership record (no soft-delete on project_members)."""
        db.delete(member)
        db.flush()

    @staticmethod
    def count_project_managers(db: Session, project_id: uuid.UUID) -> int:
        """Return the number of members with project_role == 'manager' on a project."""
        from sqlalchemy import func

        return (
            db.query(func.count(ProjectMember.id))
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.project_role == ProjectMemberRole.manager,
            )
            .scalar()
            or 0
        )


project_member_repository = ProjectMemberRepository()
