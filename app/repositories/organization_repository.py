"""Repository for Organization database operations."""

import uuid

from sqlalchemy.orm import Session

from app.models.organization import Organization


class OrganizationRepository:
    """Encapsulates database access for Organization models."""

    @staticmethod
    def create(db: Session, name: str) -> Organization:
        """Create and persist a new Organization."""
        org = Organization(name=name)
        db.add(org)
        db.flush()
        return org

    @staticmethod
    def get_by_id(db: Session, org_id: uuid.UUID) -> Organization | None:
        """Retrieve an organization by its primary key ID."""
        return db.query(Organization).filter(Organization.id == org_id).first()


organization_repository = OrganizationRepository()
