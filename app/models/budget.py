from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Numeric, ForeignKey
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
import uuid

class ProjectBudget(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "project_budgets"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
