from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, Date, ForeignKey, Enum as SQLEnum
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
from datetime import date
import enum
import uuid

class MilestoneStatus(str, enum.Enum):
    pending = "pending"
    achieved = "achieved"
    missed = "missed"

class Milestone(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "milestones"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[MilestoneStatus] = mapped_column(SQLEnum(MilestoneStatus, native_enum=True), default=MilestoneStatus.pending, nullable=False)
