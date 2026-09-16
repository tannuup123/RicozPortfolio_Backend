from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Numeric, Date, ForeignKey
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
from datetime import date
import uuid

class Expense(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "expenses"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
