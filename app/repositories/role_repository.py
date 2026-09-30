"""Repository for Role database operations."""

from sqlalchemy.orm import Session

from app.models.role import Role


class RoleRepository:
    """Encapsulates database access for Role model."""

    @staticmethod
    def get_by_name(db: Session, name: str) -> Role | None:
        """Retrieve a role by its unique name."""
        return db.query(Role).filter(Role.name == name).first()

    @staticmethod
    def get_by_names(db: Session, names: list[str]) -> list[Role]:
        """Retrieve a list of roles matching given names."""
        return db.query(Role).filter(Role.name.in_(names)).all()


role_repository = RoleRepository()
