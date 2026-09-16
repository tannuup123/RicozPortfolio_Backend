import enum
import uuid

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDMixin


class IdeaStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"

class Idea(Base, UUIDMixin, TenantMixin, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "ideas"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[IdeaStatus] = mapped_column(SQLEnum(IdeaStatus, native_enum=True), default=IdeaStatus.draft, nullable=False)

    strategic_goal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("strategic_goals.id", ondelete="SET NULL"), nullable=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
