"""Repository for User database operations."""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.role import Role
from app.models.user import User, UserRole


class UserRepository:
    """Encapsulates database access for User and UserRole models."""

    @staticmethod
    def get_by_email(db: Session, email: str) -> User | None:
        """Look up a user globally by email address (case-insensitive), eagerly loading roles."""
        return (
            db.query(User)
            .options(selectinload(User.roles))
            .filter(func.lower(User.email) == email.strip().lower())
            .first()
        )

    @staticmethod
    def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
        """Retrieve a user by primary key ID, eagerly loading roles."""
        return (
            db.query(User)
            .options(selectinload(User.roles))
            .filter(User.id == user_id)
            .first()
        )

    @staticmethod
    def get_role_by_name(db: Session, role_name: str) -> Role | None:
        """Look up a role by its unique name."""
        return db.query(Role).filter(Role.name == role_name).first()

    @staticmethod
    def create_user_with_org_admin(
        db: Session,
        email: str,
        hashed_password: str,
        name: str,
        organization_id: uuid.UUID,
    ) -> User:
        """Create a new user and assign the org_admin role within the session."""
        user = User(
            email=email.strip().lower(),
            hashed_password=hashed_password,
            name=name.strip(),
            organization_id=organization_id,
            is_active=True,
        )
        db.add(user)
        db.flush()

        admin_role = (
            db.query(Role).filter(Role.name == "org_admin").first()
        )
        if not admin_role:
            raise RuntimeError("Seed data missing: 'org_admin' role not found in database.")

        user_role = UserRole(user_id=user.id, role_id=admin_role.id)
        db.add(user_role)
        db.flush()

        # Refresh user roles relationship to reflect the newly inserted UserRole
        db.expire(user, ["roles"])
        _ = user.roles

        return user


user_repository = UserRepository()
