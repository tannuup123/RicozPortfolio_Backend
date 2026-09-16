from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin

class Role(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
