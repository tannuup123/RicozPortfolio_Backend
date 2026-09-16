from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Numeric, ForeignKey
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
import uuid

class BusinessCase(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "business_cases"
    idea_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ideas.id", ondelete="CASCADE"), unique=True, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    estimated_benefit: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    roi: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
