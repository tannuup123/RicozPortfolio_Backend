"""Targeted unit tests for service layer branches and error handling (Phase 11)."""

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.approval import ApprovalDecision
from app.models.idea import Idea, IdeaStatus
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User, UserRole
from app.schemas.approval import ApprovalCreateRequest
from app.schemas.user import UserUpdateRequest
from app.services.approval_service import approval_service
from app.services.business_case_service import business_case_service
from app.services.user_service import user_service
from tests.conftest_db import db_engine, db_session  # noqa: F401


def create_org(db_session) -> Organization:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


def make_user(db_session, org_id: uuid.UUID, roles: list[str]) -> User:
    u = User(
        email=f"u_{uuid.uuid4().hex[:8]}@example.com",
        name="User",
        hashed_password="pw",
        organization_id=org_id,
        is_active=True,
    )
    db_session.add(u)
    db_session.flush()
    db_roles = db_session.query(Role).filter(Role.name.in_(roles)).all()
    for r in db_roles:
        db_session.add(UserRole(user_id=u.id, role_id=r.id))
    db_session.commit()
    db_session.refresh(u)
    return u


def test_user_service_invalid_roles_raises_400(db_session):
    """Attempting to assign non-existent roles in user_service raises 400 Bad Request."""
    org = create_org(db_session)
    admin = make_user(db_session, org.id, ["org_admin"])
    target = make_user(db_session, org.id, ["team_member"])

    with pytest.raises(HTTPException) as exc:
        user_service.update_user_roles(
            db=db_session,
            caller=admin,
            target_user_id=target.id,
            new_role_names=["non_existent_role_xyz"],
        )
    assert exc.value.status_code == 400
    assert "roles do not exist" in exc.value.detail


def test_user_service_admin_demotion_lockout_protection(db_session):
    """Removing org_admin from the sole active admin raises 400 Bad Request."""
    org = create_org(db_session)
    sole_admin = make_user(db_session, org.id, ["org_admin"])

    with pytest.raises(HTTPException) as exc:
        user_service.update_user_roles(
            db=db_session,
            caller=sole_admin,
            target_user_id=sole_admin.id,
            new_role_names=["team_member"],
        )
    assert exc.value.status_code == 400
    assert "last active organization administrator" in exc.value.detail


def test_user_service_deactivate_sole_admin_lockout_protection(db_session):
    """Deactivating the sole active org_admin raises 400 Bad Request."""
    org = create_org(db_session)
    sole_admin = make_user(db_session, org.id, ["org_admin"])

    with pytest.raises(HTTPException) as exc:
        user_service.update_user(
            db=db_session,
            caller=sole_admin,
            target_user_id=sole_admin.id,
            payload=UserUpdateRequest(is_active=False),
        )
    assert exc.value.status_code == 400
    assert "last active organization administrator" in exc.value.detail


def test_approval_service_missing_business_case_raises_400(db_session):
    """Approving an idea without an attached business case raises 400."""
    org = create_org(db_session)
    pm = make_user(db_session, org.id, ["portfolio_manager"])
    idea = Idea(
        organization_id=org.id,
        title="Idea Without BC",
        description="Desc",
        author_id=pm.id,
        status=IdeaStatus.submitted,
    )
    db_session.add(idea)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        approval_service.create_approval(
            db=db_session,
            caller=pm,
            idea_id=idea.id,
            payload=ApprovalCreateRequest(decision=ApprovalDecision.approved),
        )
    assert exc.value.status_code == 400
    assert "business case must exist" in exc.value.detail


def test_approval_service_invalid_idea_status_raises_400(db_session):
    """Approving an idea that is already approved raises 400."""
    from app.models.business_case import BusinessCase

    org = create_org(db_session)
    pm = make_user(db_session, org.id, ["portfolio_manager"])
    idea = Idea(
        organization_id=org.id,
        title="Already Approved Idea",
        description="Desc",
        author_id=pm.id,
        status=IdeaStatus.approved,
    )
    db_session.add(idea)
    db_session.flush()

    bc = BusinessCase(idea_id=idea.id, estimated_cost=Decimal("100"), estimated_benefit=Decimal("200"))
    db_session.add(bc)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        approval_service.create_approval(
            db=db_session,
            caller=pm,
            idea_id=idea.id,
            payload=ApprovalCreateRequest(decision=ApprovalDecision.approved),
        )
    assert exc.value.status_code == 400
    assert "submitted" in exc.value.detail or "in_review" in exc.value.detail


def test_business_case_roi_calculation_edge_cases():
    """Verify ROI calculation returns None for zero cost and quantized Decimals otherwise."""
    roi_zero = business_case_service._compute_roi(cost_val=0.0, benefit_val=100.0)
    assert roi_zero is None

    roi_normal = business_case_service._compute_roi(cost_val=100.0, benefit_val=250.0)
    assert roi_normal == Decimal("1.50")
