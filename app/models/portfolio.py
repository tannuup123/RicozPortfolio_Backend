from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin, TenantMixin, SoftDeleteMixin

class Portfolio(Base, UUIDMixin, TenantMixin, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "portfolios"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
