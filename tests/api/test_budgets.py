"""Automated tests for Budget API endpoints (Phase 9: BG-01 to BG-18)."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.expense import Expense
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectMemberRole
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


def test_get_budget_default_zero_when_unset(client, db_session):
    """BG-01: GET budget for a project with no budget returns zero defaults (200)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] is None
    assert data["project_id"] == str(prj.id)
    assert float(data["amount"]) == 0.0
    assert data["currency"] == "USD"
    assert float(data["actual_spend"]) == 0.0
    assert data["created_at"] is None
    assert data["updated_at"] is None


def test_upsert_budget_as_assigned_pm_succeeds(client, db_session):
    """BG-02: Assigned PM sets planned budget for project (200)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    payload = {"amount": 50000.00, "currency": "USD"}
    res = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] is not None
    assert data["project_id"] == str(prj.id)
    assert float(data["amount"]) == 50000.00
    assert data["currency"] == "USD"
    assert float(data["actual_spend"]) == 0.0
    assert data["created_at"] is not None
    assert data["updated_at"] is not None


def test_upsert_budget_as_admin_succeeds(client, db_session):
    """BG-03: Org Admin sets budget without explicit membership (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 12500.50, "currency": "USD"},
    )
    assert res.status_code == 200
    assert float(res.json()["amount"]) == 12500.50


def test_upsert_budget_as_portfolio_manager_succeeds(client, db_session):
    """BG-04: Portfolio Manager sets budget without explicit membership (200)."""
    org = create_org(db_session)
    pfm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 75000.00, "currency": "EUR"},
    )
    assert res.status_code == 200
    data = res.json()
    assert float(data["amount"]) == 75000.00
    assert data["currency"] == "EUR"


def test_upsert_budget_as_team_member_forbidden(client, db_session):
    """BG-05: Team member cannot set budget (403)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    res = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 1000.00, "currency": "USD"},
    )
    assert res.status_code == 403
    assert "Insufficient permissions" in res.json()["detail"]


def test_upsert_budget_as_unassigned_pm_forbidden(client, db_session):
    """BG-06: Unassigned PM cannot set budget for non-member project (403)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 5000.00, "currency": "USD"},
    )
    assert res.status_code == 403


def test_upsert_budget_update_idempotent(client, db_session):
    """BG-07: Updating budget replaces amount and currency without creating duplicate rows (200)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    # Initial creation
    res1 = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 10000.00, "currency": "USD"},
    )
    assert res1.status_code == 200
    budget_id = res1.json()["id"]

    # Update
    res2 = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 15000.00, "currency": "GBP"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["id"] == budget_id
    assert float(data2["amount"]) == 15000.00
    assert data2["currency"] == "GBP"


def test_upsert_budget_currency_normalized_to_uppercase(client, db_session):
    """BG-08: Lowercase currency is normalized to uppercase (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 3000.00, "currency": "eur"},
    )
    assert res.status_code == 200
    assert res.json()["currency"] == "EUR"


def test_upsert_budget_validation_negative_amount_rejected(client, db_session):
    """BG-09: Negative budget amount rejected (422)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": -100.00, "currency": "USD"},
    )
    assert res.status_code == 422


def test_upsert_budget_validation_invalid_currency_rejected(client, db_session):
    """BG-10: Invalid currency codes (length != 3 or non-alpha) rejected (422)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    # Too short
    res1 = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 100.00, "currency": "US"},
    )
    assert res1.status_code == 422

    # Non-alpha
    res2 = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 100.00, "currency": "123"},
    )
    assert res2.status_code == 422


def test_get_budget_as_assigned_team_member_succeeds(client, db_session):
    """BG-11: Assigned team member can view project budget (200)."""
    org = create_org(db_session)
    admin, admin_token = make_user_in_org(db_session, org.id, ["org_admin"])
    member, member_token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    # Admin sets budget
    client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"amount": 20000.00, "currency": "USD"},
    )

    # Team member views budget
    res = client.get(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 200
    assert float(res.json()["amount"]) == 20000.00


def test_get_budget_as_unassigned_user_forbidden(client, db_session):
    """BG-12: Unassigned same-org user cannot view budget (403)."""
    org = create_org(db_session)
    member, member_token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 403
    assert "Forbidden: You are not a member of this project." in res.json()["detail"]


def test_budget_tenant_isolation_cross_org(client, db_session):
    """BG-13: Cross-organization budget access returns 404."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    admin_a, token_a = make_user_in_org(db_session, org_a.id, ["org_admin"])

    prj_b = Project(organization_id=org_b.id, name="Org B Prj")
    db_session.add(prj_b)
    db_session.commit()

    # GET budget of other org
    res_get = client.get(
        f"/api/v1/projects/{prj_b.id}/budget",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_get.status_code == 404

    # PUT budget of other org
    res_put = client.put(
        f"/api/v1/projects/{prj_b.id}/budget",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"amount": 9999.00, "currency": "USD"},
    )
    assert res_put.status_code == 404


def test_budget_unauthenticated_returns_401(client, db_session):
    """BG-14: Missing Authorization header returns 401."""
    org = create_org(db_session)
    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    assert client.get(f"/api/v1/projects/{prj.id}/budget").status_code == 401
    assert client.put(f"/api/v1/projects/{prj.id}/budget", json={"amount": 1000.00}).status_code == 401


def test_budget_non_existent_project_returns_404(client, db_session):
    """BG-15: Non-existent project ID returns 404."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    fake_id = uuid.uuid4()

    assert client.get(f"/api/v1/projects/{fake_id}/budget", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.put(
        f"/api/v1/projects/{fake_id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 1000.00, "currency": "USD"},
    ).status_code == 404


def test_budget_soft_deleted_project_returns_404(client, db_session):
    """BG-16: Soft-deleted project returns 404."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(
        organization_id=org.id,
        name="Deleted Prj",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(prj)
    db_session.commit()

    assert client.get(f"/api/v1/projects/{prj.id}/budget", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 5000.00, "currency": "USD"},
    ).status_code == 404


def test_budget_actual_spend_reflects_expenses_when_budget_unset(client, db_session):
    """BG-17: GET budget computes actual spend from expenses even before planned budget is set (200)."""
    from datetime import date
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()

    exp1 = Expense(project_id=prj.id, amount=Decimal("150.25"), description="Software", date=date.today())
    exp2 = Expense(project_id=prj.id, amount=Decimal("349.75"), description="Hardware", date=date.today())
    db_session.add_all([exp1, exp2])
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] is None
    assert float(data["amount"]) == 0.0
    assert float(data["actual_spend"]) == 500.00


def test_upsert_budget_with_zero_amount(client, db_session):
    """BG-18: Setting planned budget amount to 0.00 is valid (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.put(
        f"/api/v1/projects/{prj.id}/budget",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 0.00, "currency": "USD"},
    )
    assert res.status_code == 200
    assert float(res.json()["amount"]) == 0.0
