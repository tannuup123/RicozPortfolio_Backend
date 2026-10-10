"""Automated tests for Risk API endpoints (Phase 9: RK-01 to RK-26)."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectMemberRole
from app.models.risk import Risk, RiskLevel, RiskStatus
from app.models.role import Role
from app.models.user import User, UserRole
from tests.conftest_db import db_engine, db_session  # noqa: F401


@pytest.fixture
def client(db_session):  # noqa: F811
    """FastAPI TestClient with overridden get_db pointing to test DB."""
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_org(db_session) -> Organization:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


def make_user_in_org(
    db_session,
    org_id: uuid.UUID,
    role_names: list[str],
    is_active: bool = True,
    name: str = "Test User",
) -> tuple[User, str]:
    user = User(
        email=f"usr_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("Password123!"),
        name=name,
        organization_id=org_id,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.flush()

    roles = db_session.query(Role).filter(Role.name.in_(role_names)).all()
    for role in roles:
        db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token(user_id=user.id, organization_id=org_id)
    return user, token


def test_list_risks_initially_empty(client, db_session):
    """RK-01: List risks for a project with no risks returns empty list (200)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/risks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_create_risk_as_assigned_pm_succeeds(client, db_session):
    """RK-02: Assigned PM logs risk in project with default/custom values (201)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    payload = {
        "title": "Vendor API deprecation",
        "description": "Provider announced v1 shutdown",
        "probability": "high",
        "impact": "high",
        "status": "open",
    }
    res = client.post(
        f"/api/v1/projects/{prj.id}/risks",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["id"] is not None
    assert data["project_id"] == str(prj.id)
    assert data["title"] == "Vendor API deprecation"
    assert data["description"] == "Provider announced v1 shutdown"
    assert data["probability"] == "high"
    assert data["impact"] == "high"
    assert data["status"] == "open"
    assert data["created_at"] is not None
    assert data["updated_at"] is not None


def test_create_risk_as_admin_succeeds(client, db_session):
    """RK-03: Org Admin creates risk without explicit membership (201)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    payload = {
        "title": "Infrastructure cost spike",
        "probability": "medium",
        "impact": "medium",
    }
    res = client.post(
        f"/api/v1/projects/{prj.id}/risks",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201
    assert res.json()["title"] == "Infrastructure cost spike"
    assert res.json()["status"] == "open"


def test_create_risk_as_portfolio_manager_succeeds(client, db_session):
    """RK-04: Portfolio Manager creates risk without explicit membership (201)."""
    org = create_org(db_session)
    pfm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    payload = {"title": "Regulatory compliance deadline"}
    res = client.post(
        f"/api/v1/projects/{prj.id}/risks",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201
    assert res.json()["title"] == "Regulatory compliance deadline"


def test_create_risk_as_team_member_forbidden(client, db_session):
    """RK-05: Team member cannot create risks (403)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/risks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Team Member Risk"},
    )
    assert res.status_code == 403
    assert "Insufficient permissions" in res.json()["detail"]


def test_create_risk_as_unassigned_pm_forbidden(client, db_session):
    """RK-06: Unassigned PM cannot create risk for non-member project (403)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/risks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Unassigned PM Risk"},
    )
    assert res.status_code == 403


def test_create_risk_validation_blank_or_missing_title_rejected(client, db_session):
    """RK-07: Blank or missing title rejected (422)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    # Missing title
    res1 = client.post(
        f"/api/v1/projects/{prj.id}/risks",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": "No title"},
    )
    assert res1.status_code == 422

    # Blank title
    res2 = client.post(
        f"/api/v1/projects/{prj.id}/risks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "   "},
    )
    assert res2.status_code == 422


def test_create_risk_validation_invalid_enum_rejected(client, db_session):
    """RK-08: Invalid probability, impact, or status rejected (422)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/risks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Valid Title", "probability": "extreme"},
    )
    assert res.status_code == 422


def test_get_risk_direct_as_pm_succeeds(client, db_session):
    """RK-09: PM retrieves single risk directly by ID (200)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    risk = Risk(project_id=prj.id, title="Single Risk Test", probability=RiskLevel.low, impact=RiskLevel.high)
    db_session.add_all([m, risk])
    db_session.commit()

    res = client.get(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(risk.id)
    assert data["title"] == "Single Risk Test"
    assert data["probability"] == "low"
    assert data["impact"] == "high"


def test_get_risk_direct_as_assigned_team_member_succeeds(client, db_session):
    """RK-10: Assigned team member can view single risk (200)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    risk = Risk(project_id=prj.id, title="Member Viewable Risk")
    db_session.add_all([m, risk])
    db_session.commit()

    res = client.get(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "Member Viewable Risk"


def test_get_risk_direct_as_unassigned_user_forbidden(client, db_session):
    """RK-11: Unassigned same-org user cannot view single risk (403)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    risk = Risk(project_id=prj.id, title="Secret Risk")
    db_session.add(risk)
    db_session.commit()

    res = client.get(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert "Forbidden: You are not a member of this project." in res.json()["detail"]


def test_patch_risk_as_pm_succeeds(client, db_session):
    """RK-12: PM updates title, probability, impact, and status (200)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    risk = Risk(
        project_id=prj.id,
        title="Initial Title",
        probability=RiskLevel.low,
        impact=RiskLevel.low,
        status=RiskStatus.open,
    )
    db_session.add_all([m, risk])
    db_session.commit()

    patch_payload = {
        "title": "Escalated Title",
        "probability": "high",
        "impact": "high",
        "status": "mitigated",
    }
    res = client.patch(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
        json=patch_payload,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Escalated Title"
    assert data["probability"] == "high"
    assert data["impact"] == "high"
    assert data["status"] == "mitigated"


def test_patch_risk_status_transitions(client, db_session):
    """RK-13: Status moves through open -> mitigated -> closed (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    risk = Risk(project_id=prj.id, title="Status Cycle Risk", status=RiskStatus.open)
    db_session.add(risk)
    db_session.commit()

    # open -> mitigated
    res1 = client.patch(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "mitigated"},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "mitigated"

    # mitigated -> closed
    res2 = client.patch(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "closed"},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "closed"


def test_patch_risk_clear_description_via_null(client, db_session):
    """RK-14: Explicit null on description clears it; omitting keeps it (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    risk = Risk(project_id=prj.id, title="Desc Risk", description="Original description text")
    db_session.add(risk)
    db_session.commit()

    # Omit description -> keeps existing
    res_omit = client.patch(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "mitigated"},
    )
    assert res_omit.status_code == 200
    assert res_omit.json()["description"] == "Original description text"

    # Explicit null -> cleared
    res_null = client.patch(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": None},
    )
    assert res_null.status_code == 200
    assert res_null.json()["description"] is None


def test_patch_risk_validation_explicit_null_or_blank_title_rejected(client, db_session):
    """RK-15: Explicit null or blank title in patch payload rejected (422)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    risk = Risk(project_id=prj.id, title="Immutable Title")
    db_session.add(risk)
    db_session.commit()

    # Explicit null
    res1 = client.patch(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": None},
    )
    assert res1.status_code == 422

    # Blank title
    res2 = client.patch(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "   "},
    )
    assert res2.status_code == 422


def test_patch_risk_validation_explicit_null_enum_rejected(client, db_session):
    """RK-16: Explicit null on probability, impact, or status rejected (422)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    risk = Risk(project_id=prj.id, title="Enum Test Risk")
    db_session.add(risk)
    db_session.commit()

    for field in ["probability", "impact", "status"]:
        res = client.patch(
            f"/api/v1/risks/{risk.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={field: None},
        )
        assert res.status_code == 422


def test_patch_risk_as_team_member_forbidden(client, db_session):
    """RK-17: Team member cannot update risk (403)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    risk = Risk(project_id=prj.id, title="Protected Risk")
    db_session.add_all([m, risk])
    db_session.commit()

    res = client.patch(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "closed"},
    )
    assert res.status_code == 403


def test_delete_risk_as_pm_succeeds(client, db_session):
    """RK-18: Assigned PM deletes risk (204, hard deleted)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    risk = Risk(project_id=prj.id, title="To Be Deleted")
    db_session.add_all([m, risk])
    db_session.commit()

    res = client.delete(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 204

    # Verify deleted from DB
    deleted = db_session.query(Risk).filter(Risk.id == risk.id).first()
    assert deleted is None


def test_delete_risk_as_team_member_forbidden(client, db_session):
    """RK-19: Team member cannot delete risk (403)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    risk = Risk(project_id=prj.id, title="Undeletable Risk")
    db_session.add_all([m, risk])
    db_session.commit()

    res = client.delete(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_delete_risk_as_unassigned_pm_forbidden(client, db_session):
    """RK-20: Unassigned PM cannot delete risk (403)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    risk = Risk(project_id=prj.id, title="Other PM Risk")
    db_session.add(risk)
    db_session.commit()

    res = client.delete(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_list_risks_status_filter(client, db_session):
    """RK-21: Filter risks by status query param (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()

    r1 = Risk(project_id=prj.id, title="Risk 1", status=RiskStatus.open)
    r2 = Risk(project_id=prj.id, title="Risk 2", status=RiskStatus.mitigated)
    r3 = Risk(project_id=prj.id, title="Risk 3", status=RiskStatus.closed)
    db_session.add_all([r1, r2, r3])
    db_session.commit()

    # Filter open
    res_open = client.get(
        f"/api/v1/projects/{prj.id}/risks?status=open",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_open.status_code == 200
    assert len(res_open.json()["items"]) == 1
    assert res_open.json()["items"][0]["title"] == "Risk 1"

    # Filter mitigated
    res_mit = client.get(
        f"/api/v1/projects/{prj.id}/risks?status=mitigated",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_mit.status_code == 200
    assert len(res_mit.json()["items"]) == 1
    assert res_mit.json()["items"][0]["title"] == "Risk 2"

    # All without filter
    res_all = client.get(
        f"/api/v1/projects/{prj.id}/risks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_all.status_code == 200
    assert res_all.json()["total"] == 3


def test_risk_tenant_isolation_cross_org(client, db_session):
    """RK-22: Cross-org risk access returns 404."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    admin_a, token_a = make_user_in_org(db_session, org_a.id, ["org_admin"])

    prj_b = Project(organization_id=org_b.id, name="Org B Prj")
    db_session.add(prj_b)
    db_session.flush()
    risk_b = Risk(project_id=prj_b.id, title="Org B Risk")
    db_session.add(risk_b)
    db_session.commit()

    # List risks cross-org
    assert client.get(f"/api/v1/projects/{prj_b.id}/risks", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # Create risk cross-org
    assert client.post(
        f"/api/v1/projects/{prj_b.id}/risks",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Hacked Risk"},
    ).status_code == 404

    # Get single risk cross-org
    assert client.get(f"/api/v1/risks/{risk_b.id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # Patch risk cross-org
    assert client.patch(
        f"/api/v1/risks/{risk_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Hacked Title"},
    ).status_code == 404

    # Delete risk cross-org
    assert client.delete(f"/api/v1/risks/{risk_b.id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404


def test_risk_unauthenticated_returns_401(client, db_session):
    """RK-23: Missing Authorization header returns 401."""
    org = create_org(db_session)
    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    risk = Risk(project_id=prj.id, title="Risk")
    db_session.add(risk)
    db_session.commit()

    assert client.get(f"/api/v1/projects/{prj.id}/risks").status_code == 401
    assert client.post(f"/api/v1/projects/{prj.id}/risks", json={"title": "X"}).status_code == 401
    assert client.get(f"/api/v1/risks/{risk.id}").status_code == 401
    assert client.patch(f"/api/v1/risks/{risk.id}", json={"status": "closed"}).status_code == 401
    assert client.delete(f"/api/v1/risks/{risk.id}").status_code == 401


def test_risk_non_existent_returns_404(client, db_session):
    """RK-24: Non-existent risk or project ID returns 404."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    fake_id = uuid.uuid4()

    assert client.get(f"/api/v1/projects/{fake_id}/risks", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.post(
        f"/api/v1/projects/{fake_id}/risks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "X"},
    ).status_code == 404
    assert client.get(f"/api/v1/risks/{fake_id}", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.patch(
        f"/api/v1/risks/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Y"},
    ).status_code == 404
    assert client.delete(f"/api/v1/risks/{fake_id}", headers={"Authorization": f"Bearer {token}"}).status_code == 404


def test_risk_soft_deleted_project_returns_404(client, db_session):
    """RK-25: Risk operations against a soft-deleted project return 404."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(
        organization_id=org.id,
        name="Deleted Prj",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(prj)
    db_session.flush()
    risk = Risk(project_id=prj.id, title="Ghost Risk")
    db_session.add(risk)
    db_session.commit()

    assert client.get(f"/api/v1/projects/{prj.id}/risks", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.post(
        f"/api/v1/projects/{prj.id}/risks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "New Ghost"},
    ).status_code == 404
    assert client.get(f"/api/v1/risks/{risk.id}", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.patch(
        f"/api/v1/risks/{risk.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "closed"},
    ).status_code == 404
    assert client.delete(f"/api/v1/risks/{risk.id}", headers={"Authorization": f"Bearer {token}"}).status_code == 404


def test_risk_pagination(client, db_session):
    """RK-26: Pagination parameters limit and offset return correct slices for risks (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    for i in range(5):
        client.post(
            f"/api/v1/projects/{prj.id}/risks",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": f"Risk {i}"},
        )

    res = client.get(
        f"/api/v1/projects/{prj.id}/risks?limit=2&offset=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
