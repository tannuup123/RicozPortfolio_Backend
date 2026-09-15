"""SQLAlchemy 2.0 declarative base.

All models (Phase 2+) will import Base from here.
No models are defined in Phase 1.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass
