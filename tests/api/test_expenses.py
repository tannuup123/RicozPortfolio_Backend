"""Automated tests for Expense API endpoints (Phase 9: EX-01 to EX-19)."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
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


def test_list_expenses_initially_empty(client, db_session):
    """EX-01: List expenses for a project with no expenses returns empty list (200)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_create_expense_as_assigned_pm_succeeds(client, db_session):
    """EX-02: Assigned PM logs expense against project (201)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    today_str = date.today().isoformat()
    payload = {
        "amount": 250.75,
        "description": "Cloud hosting subscription",
        "date": today_str,
    }
    res = client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["id"] is not None
    assert data["project_id"] == str(prj.id)
    assert float(data["amount"]) == 250.75
    assert data["description"] == "Cloud hosting subscription"
    assert data["date"] == today_str
    assert data["created_at"] is not None
    assert data["updated_at"] is not None


def test_create_expense_as_admin_succeeds(client, db_session):
    """EX-03: Org Admin logs expense without explicit membership (201)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    payload = {
        "amount": 1000.00,
        "description": "Annual domain renewal",
        "date": date.today().isoformat(),
    }
    res = client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201
    assert float(res.json()["amount"]) == 1000.00


def test_create_expense_as_portfolio_manager_succeeds(client, db_session):
    """EX-04: Portfolio Manager logs expense without explicit membership (201)."""
    org = create_org(db_session)
    pfm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    payload = {
        "amount": 450.00,
        "description": "Design contractor retainer",
        "date": date.today().isoformat(),
    }
    res = client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201
    assert float(res.json()["amount"]) == 450.00


def test_create_expense_as_team_member_forbidden(client, db_session):
    """EX-05: Team member cannot log expenses (403)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    payload = {
        "amount": 50.00,
        "description": "Stationery",
        "date": date.today().isoformat(),
    }
    res = client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 403
    assert "Insufficient permissions" in res.json()["detail"]


def test_create_expense_as_unassigned_pm_forbidden(client, db_session):
    """EX-06: Unassigned PM cannot log expenses on non-member project (403)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    payload = {
        "amount": 75.00,
        "description": "Office supplies",
        "date": date.today().isoformat(),
    }
    res = client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 403


def test_create_expense_validation_zero_or_negative_amount_rejected(client, db_session):
    """EX-07: Zero or negative amount rejected (422)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    # Zero amount
    res_zero = client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 0.00, "description": "Free item", "date": date.today().isoformat()},
    )
    assert res_zero.status_code == 422

    # Negative amount
    res_neg = client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": -25.00, "description": "Refund", "date": date.today().isoformat()},
    )
    assert res_neg.status_code == 422


def test_create_expense_validation_blank_description_rejected(client, db_session):
    """EX-08: Blank or whitespace-only description rejected (422)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 100.00, "description": "   ", "date": date.today().isoformat()},
    )
    assert res.status_code == 422


def test_create_expense_validation_invalid_date_rejected(client, db_session):
    """EX-09: Invalid date string rejected (422)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 100.00, "description": "Valid item", "date": "not-a-date"},
    )
    assert res.status_code == 422


def test_list_expenses_pagination(client, db_session):
    """EX-10: Pagination parameters limit and offset return correct slices (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    today = date.today()
    for i in range(5):
        client.post(
            f"/api/v1/projects/{prj.id}/expenses",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 10.00 * (i + 1), "description": f"Expense {i}", "date": today.isoformat()},
        )

    # Page 1 (limit 2, offset 0)
    res_p1 = client.get(
        f"/api/v1/projects/{prj.id}/expenses?limit=2&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_p1.status_code == 200
    data_p1 = res_p1.json()
    assert len(data_p1["items"]) == 2
    assert data_p1["total"] == 5

    # Page 2 (limit 2, offset 2)
    res_p2 = client.get(
        f"/api/v1/projects/{prj.id}/expenses?limit=2&offset=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_p2.status_code == 200
    data_p2 = res_p2.json()
    assert len(data_p2["items"]) == 2
    assert data_p2["total"] == 5

    # IDs do not overlap
    ids_p1 = {e["id"] for e in data_p1["items"]}
    ids_p2 = {e["id"] for e in data_p2["items"]}
    assert ids_p1.isdisjoint(ids_p2)


def test_list_expenses_ordering_by_date_desc(client, db_session):
    """EX-11: Expenses are ordered newest-first by date (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    base_date = date.today()
    d_older = (base_date - timedelta(days=5)).isoformat()
    d_newer = base_date.isoformat()

    client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 100.00, "description": "Older expense", "date": d_older},
    )
    client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 200.00, "description": "Newer expense", "date": d_newer},
    )

    res = client.get(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 2
    assert items[0]["description"] == "Newer expense"
    assert items[1]["description"] == "Older expense"


def test_list_expenses_as_assigned_team_member_succeeds(client, db_session):
    """EX-12: Assigned team member can view expenses list (200)."""
    org = create_org(db_session)
    admin, admin_token = make_user_in_org(db_session, org.id, ["org_admin"])
    member, member_token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"amount": 500.00, "description": "Tools license", "date": date.today().isoformat()},
    )

    res = client.get(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 200
    assert len(res.json()["items"]) == 1


def test_list_expenses_as_unassigned_user_forbidden(client, db_session):
    """EX-13: Unassigned same-org user cannot view expenses (403)."""
    org = create_org(db_session)
    member, member_token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 403
    assert "Forbidden: You are not a member of this project." in res.json()["detail"]


def test_expense_tenant_isolation_cross_org(client, db_session):
    """EX-14: Cross-org expense list and creation returns 404."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    admin_a, token_a = make_user_in_org(db_session, org_a.id, ["org_admin"])

    prj_b = Project(organization_id=org_b.id, name="Org B Prj")
    db_session.add(prj_b)
    db_session.commit()

    # List cross-org
    res_list = client.get(
        f"/api/v1/projects/{prj_b.id}/expenses",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_list.status_code == 404

    # Create cross-org
    res_create = client.post(
        f"/api/v1/projects/{prj_b.id}/expenses",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"amount": 100.00, "description": "Cross-org hack", "date": date.today().isoformat()},
    )
    assert res_create.status_code == 404


def test_expense_unauthenticated_returns_401(client, db_session):
    """EX-15: Missing Authorization header returns 401."""
    org = create_org(db_session)
    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    assert client.get(f"/api/v1/projects/{prj.id}/expenses").status_code == 401
    assert client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        json={"amount": 10.00, "description": "X", "date": date.today().isoformat()},
    ).status_code == 401


def test_expense_non_existent_project_returns_404(client, db_session):
    """EX-16: Non-existent project ID returns 404."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    fake_id = uuid.uuid4()

    assert client.get(f"/api/v1/projects/{fake_id}/expenses", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.post(
        f"/api/v1/projects/{fake_id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 10.00, "description": "X", "date": date.today().isoformat()},
    ).status_code == 404


def test_expense_soft_deleted_project_returns_404(client, db_session):
    """EX-17: Soft-deleted project returns 404."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(
        organization_id=org.id,
        name="Deleted Prj",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(prj)
    db_session.commit()

    assert client.get(f"/api/v1/projects/{prj.id}/expenses", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 10.00, "description": "X", "date": date.today().isoformat()},
    ).status_code == 404


def test_expense_two_decimal_places_preserved(client, db_session):
    """EX-18: Expense amounts with two decimal places are accurately stored and returned (201)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 1234.56, "description": "Decimal check", "date": date.today().isoformat()},
    )
    assert res.status_code == 201
    assert Decimal(str(res.json()["amount"])) == Decimal("1234.56")


def test_expense_description_whitespace_trimmed(client, db_session):
    """EX-19: Leading and trailing whitespace on description is trimmed (201)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/expenses",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 50.00, "description": "   Trimmed Description   ", "date": date.today().isoformat()},
    )
    assert res.status_code == 201
    assert res.json()["description"] == "Trimmed Description"
