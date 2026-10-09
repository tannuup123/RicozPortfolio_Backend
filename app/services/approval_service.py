"""Business logic for Approval operations."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.approval import Approval, ApprovalDecision
from app.models.idea import Idea, IdeaStatus
from app.models.user import User
from app.repositories.approval_repository import approval_repository
from app.repositories.business_case_repository import business_case_repository
from app.repositories.idea_repository import idea_repository
from app.schemas.approval import ApprovalCreateRequest


class ApprovalService:
    """Orchestrates business logic and workflows for Idea approvals."""

    @staticmethod
    def create_approval(
        db: Session,
        caller: User,
        idea_id: uuid.UUID,
        payload: ApprovalCreateRequest,
    ) -> tuple[Approval, Idea]:
        """Record an approval or rejection decision and atomically update Idea status.

        Preconditions:
        - Idea must exist within caller's organization.
        - BusinessCase must exist for this idea (400 if missing).
        - Idea status must be 'submitted' or 'in_review' (400 if not).
        """
        idea = idea_repository.get_by_id_within_org(
            db, idea_id=idea_id, organization_id=caller.organization_id
        )
        if not idea:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Idea not found.",
            )

        bc = business_case_repository.get_by_idea_id(db, idea_id=idea_id)
        if not bc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A business case must exist before approving or rejecting an idea.",
            )

        if idea.status not in (IdeaStatus.submitted, IdeaStatus.in_review):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Idea must be in 'submitted' or 'in_review' status to be approved or rejected.",
            )

        model_decision = ApprovalDecision(payload.decision.value)
        target_status = IdeaStatus(payload.decision.value)

        try:
            approval = approval_repository.create(
                db,
                idea_id=idea_id,
                approver_id=caller.id,
                decision=model_decision,
                notes=payload.notes,
            )
            idea.status = target_status
            db.flush()
            db.commit()
            db.refresh(approval)
            db.refresh(idea)
            return approval, idea
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def list_approvals(
        db: Session,
        caller: User,
        idea_id: uuid.UUID,
    ) -> list[Approval]:
        """List chronological approval history for an idea within caller's organization."""
        idea = idea_repository.get_by_id_within_org(
            db, idea_id=idea_id, organization_id=caller.organization_id
        )
        if not idea:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Idea not found.",
            )

        return approval_repository.list_by_idea(db, idea_id=idea_id)


approval_service = ApprovalService()
