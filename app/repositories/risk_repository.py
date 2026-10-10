"""Repository for Risk database operations (Phase 9)."""

import uuid
from typing import Sequence

from sqlalchemy.orm import Session

from app.models.risk import Risk, RiskLevel, RiskStatus


class RiskRepository:
    """Encapsulates database access for Risk model."""

    @staticmethod
    def get_by_id(db: Session, risk_id: uuid.UUID) -> Risk | None:
        """Retrieve a risk by its primary key."""
        return db.query(Risk).filter(Risk.id == risk_id).first()

    @staticmethod
    def list_by_project(
        db: Session,
        project_id: uuid.UUID,
        status_filter: RiskStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[Risk], int]:
        """List risks for a project ordered by created_at DESC."""
        base = db.query(Risk).filter(Risk.project_id == project_id)
        if status_filter is not None:
            base = base.filter(Risk.status == status_filter)
        total = base.count()
        items = (
            base.order_by(Risk.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def create(
        db: Session,
        project_id: uuid.UUID,
        title: str,
        description: str | None,
        probability: RiskLevel,
        impact: RiskLevel,
        status: RiskStatus,
    ) -> Risk:
        """Create a new risk record."""
        risk = Risk(
            project_id=project_id,
            title=title.strip(),
            description=description.strip() if isinstance(description, str) else description,
            probability=probability,
            impact=impact,
            status=status,
        )
        db.add(risk)
        db.flush()
        return risk

    @staticmethod
    def update(
        db: Session,
        risk: Risk,
        title: str | None = None,
        description: str | None = None,
        clear_description: bool = False,
        probability: RiskLevel | None = None,
        impact: RiskLevel | None = None,
        status: RiskStatus | None = None,
    ) -> Risk:
        """Update risk fields selectively."""
        if title is not None:
            risk.title = title.strip()
        if clear_description:
            risk.description = None
        elif description is not None:
            risk.description = description.strip()
        if probability is not None:
            risk.probability = probability
        if impact is not None:
            risk.impact = impact
        if status is not None:
            risk.status = status
        db.flush()
        return risk

    @staticmethod
    def delete(db: Session, risk: Risk) -> None:
        """Hard-delete a risk record."""
        db.delete(risk)
        db.flush()


risk_repository = RiskRepository()
