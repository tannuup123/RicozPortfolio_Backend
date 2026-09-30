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

    @staticmethod
    def get_by_id_within_org(
        db: Session,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> User | None:
        """Retrieve a user by ID strictly within an organization, eagerly loading roles."""
        return (
            db.query(User)
            .options(selectinload(User.roles))
            .filter(User.id == user_id, User.organization_id == organization_id)
            .first()
        )

    @staticmethod
    def list_by_org(
        db: Session,
        organization_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """List users belonging to an organization with pagination and total count."""
        base_query = db.query(User).filter(User.organization_id == organization_id)
        total = base_query.count()
        users = (
            base_query.options(selectinload(User.roles))
            .order_by(User.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return users, total

    @staticmethod
    def create_user_in_org(
        db: Session,
        email: str,
        hashed_password: str,
        name: str,
        organization_id: uuid.UUID,
        role_ids: list[uuid.UUID],
    ) -> User:
        """Create a user within the specified organization and assign role IDs."""
        user = User(
            email=email.strip().lower(),
            hashed_password=hashed_password,
            name=name.strip(),
            organization_id=organization_id,
            is_active=True,
        )
        db.add(user)
        db.flush()

        for role_id in role_ids:
            db.add(UserRole(user_id=user.id, role_id=role_id))
        db.flush()

        db.expire(user, ["roles"])
        _ = user.roles
        return user

    @staticmethod
    def set_user_roles(
        db: Session,
        user_id: uuid.UUID,
        role_ids: list[uuid.UUID],
    ) -> None:
        """Replace all roles for a user with the provided role IDs."""
        db.query(UserRole).filter(UserRole.user_id == user_id).delete(synchronize_session=False)
        db.flush()

        for role_id in role_ids:
            db.add(UserRole(user_id=user_id, role_id=role_id))
        db.flush()

    @staticmethod
    def update_user(
        db: Session,
        user: User,
        name: str | None = None,
        is_active: bool | None = None,
    ) -> User:
        """Update scalar attributes on user model and flush."""
        if name is not None:
            user.name = name.strip()
        if is_active is not None:
            user.is_active = is_active
        db.flush()
        return user

    @staticmethod
    def count_active_org_admins(
        db: Session,
        organization_id: uuid.UUID,
    ) -> int:
        """Count active users holding the 'org_admin' role within an organization."""
        return (
            db.query(func.count(func.distinct(User.id)))
            .join(UserRole, User.id == UserRole.user_id)
            .join(Role, UserRole.role_id == Role.id)
            .filter(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                Role.name == "org_admin",
            )
            .scalar()
            or 0
        )


user_repository = UserRepository()

