from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, ForeignKey, Enum as SQLEnum
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin, TenantMixin, SoftDeleteMixin
import enum
import uuid

class ProjectStatus(str, enum.Enum):
    planned = "planned"
    active = "active"
    on_hold = "on_hold"
    completed = "completed"
    cancelled = "cancelled"

class Project(Base, UUIDMixin, TenantMixin, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(SQLEnum(ProjectStatus, native_enum=True), default=ProjectStatus.planned, nullable=False)
    
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True)
    source_idea_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ideas.id", ondelete="SET NULL"), unique=True, nullable=True)
