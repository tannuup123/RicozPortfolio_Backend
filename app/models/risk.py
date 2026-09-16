from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, ForeignKey, Enum as SQLEnum
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
import enum
import uuid

class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"

class RiskStatus(str, enum.Enum):
    open = "open"
    mitigated = "mitigated"
    closed = "closed"

class Risk(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "risks"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    probability: Mapped[RiskLevel] = mapped_column(SQLEnum(RiskLevel, name="risk_probability_enum", native_enum=True), default=RiskLevel.medium, nullable=False)
    impact: Mapped[RiskLevel] = mapped_column(SQLEnum(RiskLevel, name="risk_impact_enum", native_enum=True), default=RiskLevel.medium, nullable=False)
    status: Mapped[RiskStatus] = mapped_column(SQLEnum(RiskStatus, native_enum=True), default=RiskStatus.open, nullable=False)
