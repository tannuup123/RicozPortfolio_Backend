import enum
import uuid

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDMixin


class ApprovalStatus(str, enum.Enum):
    approved = "approved"
    rejected = "rejected"

class Approval(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "approvals"
    idea_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False)
    approver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(SQLEnum(ApprovalStatus, native_enum=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
