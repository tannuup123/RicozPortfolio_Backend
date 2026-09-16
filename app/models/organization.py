from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin

class Organization(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
