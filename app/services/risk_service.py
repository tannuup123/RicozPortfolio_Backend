"""Service layer for Risk operations (Phase 9)."""

import uuid
from typing import Sequence

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_member import ProjectMemberRole
from app.models.risk import Risk, RiskLevel, RiskStatus
from app.models.user import User
from app.repositories.project_member_repository import project_member_repository
from app.repositories.project_repository import project_repository
from app.repositories.risk_repository import risk_repository
from app.schemas.risk import RiskCreateRequest, RiskStatusEnum, RiskUpdateRequest


def _get_caller_role_names(caller: User) -> set[str]:
    return {r.name for r in caller.roles}


def _caller_is_broad_manager(caller: User) -> bool:
    return bool(_get_caller_role_names(caller) & {"org_admin", "portfolio_manager"})


def _require_project_in_org(
    db: Session,
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> Project:
    project = project_repository.get_by_id_within_org(
        db, project_id=project_id, organization_id=organization_id
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return project


def _caller_can_manage_project(
    db: Session,
    caller: User,
    project_id: uuid.UUID,
) -> bool:
    if _caller_is_broad_manager(caller):
        return True
    membership = project_member_repository.get_membership(
        db, project_id=project_id, user_id=caller.id
    )
    return bool(membership and membership.project_role == ProjectMemberRole.manager)


def _caller_can_view_project(
    db: Session,
    caller: User,
    project_id: uuid.UUID,
) -> bool:
    if _caller_is_broad_manager(caller):
        return True
    membership = project_member_repository.get_membership(
        db, project_id=project_id, user_id=caller.id
    )
    return membership is not None


class RiskService:
    """Orchestrates business logic, permissions, and validation for project risks."""

    @staticmethod
    def list_risks(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        status_filter: RiskStatusEnum | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[Risk], int]:
        """List risks for a project.

        Accessible to any project member or broad manager.
        """
        _require_project_in_org(db, project_id=project_id, organization_id=caller.organization_id)

        if not _caller_can_view_project(db, caller=caller, project_id=project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You are not a member of this project.",
            )

        domain_status = RiskStatus(status_filter.value) if status_filter is not None else None
        return risk_repository.list_by_project(
            db=db,
            project_id=project_id,
            status_filter=domain_status,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def get_risk(
        db: Session,
        caller: User,
        risk_id: uuid.UUID,
    ) -> Risk:
        """Retrieve a single risk by ID.

        Accessible to anyone with project visibility.
        """
        risk = risk_repository.get_by_id(db, risk_id=risk_id)
        if not risk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Risk not found.",
            )

        _require_project_in_org(db, project_id=risk.project_id, organization_id=caller.organization_id)

        if not _caller_can_view_project(db, caller=caller, project_id=risk.project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You are not a member of this project.",
            )

        return risk

    @staticmethod
    def create_risk(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        payload: RiskCreateRequest,
    ) -> Risk:
        """Create a new risk entry for a project.

        Permitted for project managers or broad managers.
        """
        project = _require_project_in_org(db, project_id=project_id, organization_id=caller.organization_id)

        if not _caller_can_manage_project(db, caller=caller, project_id=project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions to create risks for this project.",
            )

        risk = risk_repository.create(
            db=db,
            project_id=project.id,
            title=payload.title,
            description=payload.description,
            probability=RiskLevel(payload.probability.value),
            impact=RiskLevel(payload.impact.value),
            status=RiskStatus(payload.status.value),
        )
        db.commit()
        db.refresh(risk)
        return risk

    @staticmethod
    def update_risk(
        db: Session,
        caller: User,
        risk_id: uuid.UUID,
        payload: RiskUpdateRequest,
    ) -> Risk:
        """Partially update a risk.

        Permitted for project managers or broad managers.
        Uses model_fields_set to detect explicitly sent fields.
        """
        risk = risk_repository.get_by_id(db, risk_id=risk_id)
        if not risk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Risk not found.",
            )

        # Tenant isolation: risk's project must belong to caller's org
        _require_project_in_org(db, project_id=risk.project_id, organization_id=caller.organization_id)

        if not _caller_can_manage_project(db, caller=caller, project_id=risk.project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions to update risks for this project.",
            )

        new_title = payload.title if "title" in payload.model_fields_set else None
        clear_desc = "description" in payload.model_fields_set and payload.description is None
        new_description = (
            payload.description
            if "description" in payload.model_fields_set and payload.description is not None
            else None
        )
        new_probability = RiskLevel(payload.probability.value) if payload.probability is not None else None
        new_impact = RiskLevel(payload.impact.value) if payload.impact is not None else None
        new_status = RiskStatus(payload.status.value) if payload.status is not None else None

        risk_repository.update(
            db=db,
            risk=risk,
            title=new_title,
            description=new_description,
            clear_description=clear_desc,
            probability=new_probability,
            impact=new_impact,
            status=new_status,
        )
        db.commit()
        db.refresh(risk)
        return risk

    @staticmethod
    def delete_risk(
        db: Session,
        caller: User,
        risk_id: uuid.UUID,
    ) -> None:
        """Hard-delete a risk.

        Permitted for project managers or broad managers.
        """
        risk = risk_repository.get_by_id(db, risk_id=risk_id)
        if not risk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Risk not found.",
            )

        _require_project_in_org(db, project_id=risk.project_id, organization_id=caller.organization_id)

        if not _caller_can_manage_project(db, caller=caller, project_id=risk.project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions to delete risks for this project.",
            )

        risk_repository.delete(db, risk=risk)
        db.commit()


risk_service = RiskService()
