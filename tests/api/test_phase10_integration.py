"""Integration tests for Phase 10 Dashboards (INT10-01 to INT10-04).

End-to-end tests using the real API stack (no mocks) to verify that
dashboard values computed by the service exactly match the data seeded
through other API calls.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.portfolio import Portfolio
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectMemberRole
from app.models.role import Role
from app.models.user import User, UserRole
from tests.conftest_db import db_engine, db_session  # noqa: F401


@pytest.fixture
def client(db_session):  # noqa: F811
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


def test_INT10_01_project_dashboard_matches_api_seeded_data(client, db_session):
    """INT10-01: Project dashboard values exactly match data inserted via real API calls.

    Scenario:
      - 4 tasks: 2 done, 1 in_progress, 1 todo  → completion 50%
      - Budget: $10,000
      - Expenses: $4,000 + $2,000 = $6,000       → utilization 60%
      - 1 open high-impact risk                   → at_risk
      - 2 open medium-impact risks
    """
    org = create_org(db_session)
    pm, pm_token = make_user_in_org(db_session, org.id, ["project_manager"], name="PM")
    portfolio = Portfolio(organization_id=org.id, name="INT Portfolio")
    db_session.add(portfolio)
    db_session.flush()

    project = Project(organization_id=org.id, portfolio_id=portfolio.id, name="Integration Project")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=pm.id, project_role=ProjectMemberRole.manager))
    db_session.commit()

    today = date.today().isoformat()

    # Tasks via API
    for status in ["done", "done", "in_progress", "todo"]:
        client.post(
            f"/api/v1/projects/{project.id}/tasks",
            headers={"Authorization": f"Bearer {pm_token}"},
            json={"title": f"Task {status}", "status": status},
        )

    # Budget via API
    client.put(
        f"/api/v1/projects/{project.id}/budget",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"amount": 10000.00, "currency": "USD"},
    )

    # Expenses via API
    for amount in [4000.00, 2000.00]:
        client.post(
            f"/api/v1/projects/{project.id}/expenses",
            headers={"Authorization": f"Bearer {pm_token}"},
            json={"amount": amount, "description": "Test", "date": today},
        )

    # Risks via API
    client.post(
        f"/api/v1/projects/{project.id}/risks",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"title": "High risk", "impact": "high", "status": "open"},
    )
    for _ in range(2):
        client.post(
            f"/api/v1/projects/{project.id}/risks",
            headers={"Authorization": f"Bearer {pm_token}"},
            json={"title": f"Med risk {uuid.uuid4().hex[:4]}", "impact": "medium", "status": "open"},
        )

    # Now check dashboard
    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res.status_code == 200
    d = res.json()

    # Task metrics
    assert d["task_total"] == 4
    assert d["task_done"] == 2
    assert Decimal(str(d["task_completion_pct"])) == Decimal("50.0")

    # Budget metrics
    assert Decimal(str(d["budget_planned"])) == Decimal("10000.0")
    assert Decimal(str(d["budget_actual"])) == Decimal("6000.0")
    assert Decimal(str(d["budget_utilization_pct"])) == Decimal("60.0")

    # Risk metrics
    assert d["open_risk_count"] == 3
    assert d["has_high_impact_open_risk"] is True
    assert d["health_flag"] == "at_risk"


def test_INT10_02_portfolio_dashboard_aggregates_multiple_projects(client, db_session):
    """INT10-02: Portfolio dashboard correctly aggregates 3 projects with known values.

    Projects:
      Alpha: 50% budget used, no high risk → on_track
      Beta:  120% budget used (overspent)  → off_track
      Gamma: 85% budget used, no high risk → at_risk
    """
    org = create_org(db_session)
    admin, admin_token = make_user_in_org(db_session, org.id, ["org_admin"], name="Admin")
    portfolio = Portfolio(organization_id=org.id, name="Multi Project Portfolio")
    db_session.add(portfolio)
    db_session.flush()

    def make_project(name, planned, actual):
        p = Project(organization_id=org.id, portfolio_id=portfolio.id, name=name)
        db_session.add(p)
        db_session.flush()
        from app.models.budget import ProjectBudget
        from app.models.expense import Expense
        budget = ProjectBudget(project_id=p.id, amount=planned, currency="USD")
        expense = Expense(project_id=p.id, amount=actual, description="x", date=date.today())
        db_session.add_all([budget, expense])
        return p

    make_project("Alpha", Decimal("1000"), Decimal("500"))   # 50% → on_track
    make_project("Beta", Decimal("1000"), Decimal("1200"))   # 120% → off_track
    make_project("Gamma", Decimal("1000"), Decimal("850"))   # 85% → at_risk
    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio.id}/dashboard",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    d = res.json()
    assert d["project_count"] == 3

    by_name = {p["project_name"]: p for p in d["projects"]}
    assert by_name["Alpha"]["health_flag"] == "on_track"
    assert Decimal(str(by_name["Alpha"]["budget_utilization_pct"])) == Decimal("50.0")

    assert by_name["Beta"]["health_flag"] == "off_track"
    assert Decimal(str(by_name["Beta"]["budget_utilization_pct"])) == Decimal("120.0")

    assert by_name["Gamma"]["health_flag"] == "at_risk"
    assert Decimal(str(by_name["Gamma"]["budget_utilization_pct"])) == Decimal("85.0")


def test_INT10_03_dashboard_reflects_risk_status_change(client, db_session):
    """INT10-03: Mitigating the only high-impact risk flips health from at_risk → on_track.

    This verifies that the dashboard is computed live, not cached.
    """
    org = create_org(db_session)
    pm, pm_token = make_user_in_org(db_session, org.id, ["project_manager"], name="PM")
    project = Project(organization_id=org.id, name="Live Risk Project")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=pm.id, project_role=ProjectMemberRole.manager))
    db_session.commit()

    # Create budget at 50% utilization
    client.put(
        f"/api/v1/projects/{project.id}/budget",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"amount": 1000.00, "currency": "USD"},
    )
    client.post(
        f"/api/v1/projects/{project.id}/expenses",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"amount": 500.00, "description": "Expense", "date": date.today().isoformat()},
    )

    # Create high-impact open risk
    res_r = client.post(
        f"/api/v1/projects/{project.id}/risks",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"title": "Critical Risk", "impact": "high", "status": "open"},
    )
    risk_id = res_r.json()["id"]

    # Dashboard should be at_risk
    res1 = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res1.json()["health_flag"] == "at_risk"
    assert res1.json()["has_high_impact_open_risk"] is True

    # Mitigate the risk
    client.patch(
        f"/api/v1/risks/{risk_id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"status": "mitigated"},
    )

    # Dashboard should now be on_track (50% util, no open high risk)
    res2 = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res2.json()["health_flag"] == "on_track"
    assert res2.json()["has_high_impact_open_risk"] is False
    assert res2.json()["open_risk_count"] == 0


def test_INT10_04_cross_tenant_dashboard_isolation(client, db_session):
    """INT10-04: Org A cannot access Org B's project or portfolio dashboards."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    _, token_a = make_user_in_org(db_session, org_a.id, ["org_admin"], name="Admin A")
    _, token_b = make_user_in_org(db_session, org_b.id, ["org_admin"], name="Admin B")

    portfolio_b = Portfolio(organization_id=org_b.id, name="B Portfolio")
    db_session.add(portfolio_b)
    db_session.flush()
    project_b = Project(organization_id=org_b.id, portfolio_id=portfolio_b.id, name="B Project")
    db_session.add(project_b)
    db_session.commit()

    # Org A cannot see Org B's project dashboard
    res_proj = client.get(
        f"/api/v1/projects/{project_b.id}/dashboard",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_proj.status_code == 404

    # Org A cannot see Org B's portfolio dashboard
    res_port = client.get(
        f"/api/v1/portfolios/{portfolio_b.id}/dashboard",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_port.status_code == 404
