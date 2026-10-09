"""Repository for Approval database operations."""

import uuid

from sqlalchemy.orm import Session

from app.models.approval import Approval, ApprovalDecision


class ApprovalRepository:
    """Encapsulates database access for Approval model."""

    @staticmethod
    def list_by_idea(db: Session, idea_id: uuid.UUID) -> list[Approval]:
        """Return approval history for an idea ordered chronologically ascending."""
        return (
            db.query(Approval)
            .filter(Approval.idea_id == idea_id)
            .order_by(Approval.created_at.asc())
            .all()
        )

    @staticmethod
    def create(
        db: Session,
        idea_id: uuid.UUID,
        approver_id: uuid.UUID,
        decision: ApprovalDecision,
        notes: str | None = None,
    ) -> Approval:
        """Create an immutable Approval audit record."""
        approval = Approval(
            idea_id=idea_id,
            approver_id=approver_id,
            decision=decision,
            notes=notes.strip() if isinstance(notes, str) else notes,
        )
        db.add(approval)
        db.flush()
        return approval


approval_repository = ApprovalRepository()
