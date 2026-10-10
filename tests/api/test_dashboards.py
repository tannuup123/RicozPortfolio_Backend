"""API tests for Dashboard endpoints (Phase 10): DB-01 to DB-30."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.budget import ProjectBudget
from app.models.expense import Expense
from app.models.organization import Organization
from app.models.portfolio import Portfolio
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectMemberRole
from app.models.risk import Risk, RiskLevel, RiskStatus
from app.models.role import Role
from app.models.task import Task, TaskPriority, TaskStatus
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


def _add_task(db_session, project_id, status: TaskStatus) -> Task:
    t = Task(
        project_id=project_id,
        title=f"Task {uuid.uuid4().hex[:6]}",
        status=status,
        priority=TaskPriority.medium,
    )
    db_session.add(t)
    db_session.flush()
    return t


def _add_risk(db_session, project_id, impact: RiskLevel, status: RiskStatus = RiskStatus.open) -> Risk:
    r = Risk(
        project_id=project_id,
        title=f"Risk {uuid.uuid4().hex[:6]}",
        probability=RiskLevel.medium,
        impact=impact,
        status=status,
    )
    db_session.add(r)
    db_session.flush()
    return r


def _set_budget(db_session, project_id, amount: Decimal) -> ProjectBudget:
    b = ProjectBudget(project_id=project_id, amount=amount, currency="USD")
    db_session.add(b)
    db_session.flush()
    return b


def _add_expense(db_session, project_id, amount: Decimal) -> Expense:
    e = Expense(
        project_id=project_id,
        amount=amount,
        description="Test expense",
        date=date.today(),
    )
    db_session.add(e)
    db_session.flush()
    return e


# ============================================================
# Project Dashboard — Happy Path
# ============================================================


def test_DB01_project_dashboard_empty_project(client, db_session):
    """DB-01: Empty project returns all-zero metrics and on_track."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    project = Project(organization_id=org.id, name="Empty Project")
    db_session.add(project)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    d = res.json()
    assert d["project_id"] == str(project.id)
    assert d["task_total"] == 0
    assert d["task_done"] == 0
    assert Decimal(str(d["task_completion_pct"])) == Decimal("0.00")
    assert Decimal(str(d["budget_planned"])) == Decimal("0.00")
    assert Decimal(str(d["budget_actual"])) == Decimal("0.00")
    assert Decimal(str(d["budget_utilization_pct"])) == Decimal("0.00")
    assert d["open_risk_count"] == 0
    assert d["has_high_impact_open_risk"] is False
    assert d["health_flag"] == "on_track"


def test_DB02_project_dashboard_task_completion_pct(client, db_session):
    """DB-02: 3 done / 5 total → 60.00% completion."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    project = Project(organization_id=org.id, name="Task Project")
    db_session.add(project)
    db_session.flush()

    _add_task(db_session, project.id, TaskStatus.done)
    _add_task(db_session, project.id, TaskStatus.done)
    _add_task(db_session, project.id, TaskStatus.done)
    _add_task(db_session, project.id, TaskStatus.in_progress)
    _add_task(db_session, project.id, TaskStatus.todo)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    d = res.json()
    assert d["task_total"] == 5
    assert d["task_done"] == 3
    assert Decimal(str(d["task_completion_pct"])) == Decimal("60.0")


def test_DB03_project_dashboard_budget_utilization(client, db_session):
    """DB-03: 8000 actual / 10000 planned → 80% utilization → at_risk."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    project = Project(organization_id=org.id, name="Budget Project")
    db_session.add(project)
    db_session.flush()

    _set_budget(db_session, project.id, Decimal("10000"))
    _add_expense(db_session, project.id, Decimal("8000"))
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    d = res.json()
    assert Decimal(str(d["budget_planned"])) == Decimal("10000")
    assert Decimal(str(d["budget_actual"])) == Decimal("8000")
    assert Decimal(str(d["budget_utilization_pct"])) == Decimal("80.0")
    assert d["health_flag"] == "at_risk"


def test_DB04_project_dashboard_off_track_overspend(client, db_session):
    """DB-04: actual > planned → off_track."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    project = Project(organization_id=org.id, name="Overspent Project")
    db_session.add(project)
    db_session.flush()

    _set_budget(db_session, project.id, Decimal("1000"))
    _add_expense(db_session, project.id, Decimal("1500"))
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    d = res.json()
    assert d["health_flag"] == "off_track"


def test_DB05_project_dashboard_at_risk_high_impact_risk(client, db_session):
    """DB-05: High-impact open risk → at_risk even with good budget."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    project = Project(organization_id=org.id, name="High Risk Project")
    db_session.add(project)
    db_session.flush()

    _set_budget(db_session, project.id, Decimal("10000"))
    _add_expense(db_session, project.id, Decimal("1000"))  # only 10%
    _add_risk(db_session, project.id, RiskLevel.high, RiskStatus.open)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    d = res.json()
    assert d["has_high_impact_open_risk"] is True
    assert d["open_risk_count"] == 1
    assert d["health_flag"] == "at_risk"


def test_DB06_project_dashboard_mitigated_high_risk_is_ignored(client, db_session):
    """DB-06: High-impact mitigated risk should NOT trigger at_risk."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    project = Project(organization_id=org.id, name="Mitigated Risk Project")
    db_session.add(project)
    db_session.flush()

    _set_budget(db_session, project.id, Decimal("10000"))
    _add_expense(db_session, project.id, Decimal("2000"))  # 20%
    _add_risk(db_session, project.id, RiskLevel.high, RiskStatus.mitigated)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    d = res.json()
    assert d["has_high_impact_open_risk"] is False
    assert d["open_risk_count"] == 0
    assert d["health_flag"] == "on_track"


def test_DB07_project_dashboard_zero_budget_no_spend_on_track(client, db_session):
    """DB-07: No budget row and no expenses → on_track."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    project = Project(organization_id=org.id, name="No Budget Project")
    db_session.add(project)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    d = res.json()
    assert Decimal(str(d["budget_planned"])) == Decimal("0")
    assert Decimal(str(d["budget_actual"])) == Decimal("0")
    assert Decimal(str(d["budget_utilization_pct"])) == Decimal("0")
    assert d["health_flag"] == "on_track"


def test_DB08_project_dashboard_zero_budget_with_spend_off_track(client, db_session):
    """DB-08: No budget row but expenses exist → actual > 0 == planned → off_track."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    project = Project(organization_id=org.id, name="No Budget Spend Project")
    db_session.add(project)
    db_session.flush()

    _add_expense(db_session, project.id, Decimal("500"))
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    d = res.json()
    assert Decimal(str(d["budget_planned"])) == Decimal("0")
    assert Decimal(str(d["budget_actual"])) == Decimal("500")
    assert d["health_flag"] == "off_track"


def test_DB09_project_dashboard_all_tasks_done(client, db_session):
    """DB-09: All tasks done → 100% completion."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    project = Project(organization_id=org.id, name="Completed Project")
    db_session.add(project)
    db_session.flush()

    _add_task(db_session, project.id, TaskStatus.done)
    _add_task(db_session, project.id, TaskStatus.done)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    d = res.json()
    assert d["task_total"] == 2
    assert d["task_done"] == 2
    assert Decimal(str(d["task_completion_pct"])) == Decimal("100.0")


def test_DB10_project_dashboard_mixed_risk_statuses(client, db_session):
    """DB-10: Mix of open and closed risks — only open ones count."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    project = Project(organization_id=org.id, name="Mixed Risks")
    db_session.add(project)
    db_session.flush()

    _add_risk(db_session, project.id, RiskLevel.medium, RiskStatus.open)
    _add_risk(db_session, project.id, RiskLevel.high, RiskStatus.closed)   # closed → ignored
    _add_risk(db_session, project.id, RiskLevel.high, RiskStatus.mitigated)  # mitigated → ignored
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    d = res.json()
    assert d["open_risk_count"] == 1
    assert d["has_high_impact_open_risk"] is False
    assert d["health_flag"] == "on_track"


# ============================================================
# Project Dashboard — Permissions
# ============================================================


def test_DB11_project_dashboard_accessible_to_member(client, db_session):
    """DB-11: Project member can view project dashboard."""
    org = create_org(db_session)
    pm, pm_token = make_user_in_org(db_session, org.id, ["project_manager"])
    member, member_token = make_user_in_org(db_session, org.id, ["team_member"])
    project = Project(organization_id=org.id, name="Member Project")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=member.id, project_role=ProjectMemberRole.member))
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 200


def test_DB12_project_dashboard_forbidden_for_non_member(client, db_session):
    """DB-12: User who is not a member gets 403."""
    org = create_org(db_session)
    stranger, stranger_token = make_user_in_org(db_session, org.id, ["team_member"])
    project = Project(organization_id=org.id, name="Private Project")
    db_session.add(project)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert res.status_code == 403


def test_DB13_project_dashboard_accessible_to_portfolio_manager(client, db_session):
    """DB-13: portfolio_manager can view any project in the org without membership."""
    org = create_org(db_session)
    pm, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    project = Project(organization_id=org.id, name="PM View Project")
    db_session.add(project)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res.status_code == 200


def test_DB14_project_dashboard_requires_auth(client, db_session):
    """DB-14: Unauthenticated request returns 401."""
    org = create_org(db_session)
    project = Project(organization_id=org.id, name="Auth Test")
    db_session.add(project)
    db_session.commit()

    res = client.get(f"/api/v1/projects/{project.id}/dashboard")
    assert res.status_code == 401


def test_DB15_project_dashboard_cross_tenant_returns_404(client, db_session):
    """DB-15: Cross-org project access returns 404 (tenant isolation)."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    _, token_a = make_user_in_org(db_session, org_a.id, ["org_admin"])
    project_b = Project(organization_id=org_b.id, name="Org B Project")
    db_session.add(project_b)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project_b.id}/dashboard",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 404


def test_DB16_project_dashboard_nonexistent_project_returns_404(client, db_session):
    """DB-16: Non-existent project ID returns 404."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, ["org_admin"])

    res = client.get(
        f"/api/v1/projects/{uuid.uuid4()}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


# ============================================================
# Portfolio Dashboard — Happy Path
# ============================================================


def test_DB17_portfolio_dashboard_empty_portfolio(client, db_session):
    """DB-17: Portfolio with no projects returns empty list."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    portfolio = Portfolio(organization_id=org.id, name="Empty Portfolio")
    db_session.add(portfolio)
    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    d = res.json()
    assert d["portfolio_id"] == str(portfolio.id)
    assert d["portfolio_name"] == "Empty Portfolio"
    assert d["project_count"] == 0
    assert d["projects"] == []


def test_DB18_portfolio_dashboard_project_summaries(client, db_session):
    """DB-18: Portfolio with multiple projects returns correct summaries."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    portfolio = Portfolio(organization_id=org.id, name="Main Portfolio")
    db_session.add(portfolio)
    db_session.flush()

    # Project 1 — on_track: 50% budget, no high risk
    p1 = Project(organization_id=org.id, portfolio_id=portfolio.id, name="Alpha")
    db_session.add(p1)
    db_session.flush()
    _set_budget(db_session, p1.id, Decimal("1000"))
    _add_expense(db_session, p1.id, Decimal("500"))

    # Project 2 — off_track: over budget
    p2 = Project(organization_id=org.id, portfolio_id=portfolio.id, name="Beta")
    db_session.add(p2)
    db_session.flush()
    _set_budget(db_session, p2.id, Decimal("1000"))
    _add_expense(db_session, p2.id, Decimal("1500"))

    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    d = res.json()
    assert d["project_count"] == 2

    # Projects sorted by name ascending
    assert d["projects"][0]["project_name"] == "Alpha"
    assert d["projects"][0]["health_flag"] == "on_track"
    assert d["projects"][1]["project_name"] == "Beta"
    assert d["projects"][1]["health_flag"] == "off_track"


def test_DB19_portfolio_dashboard_sorted_by_name(client, db_session):
    """DB-19: Projects in portfolio dashboard are sorted by name ascending."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    portfolio = Portfolio(organization_id=org.id, name="Sort Portfolio")
    db_session.add(portfolio)
    db_session.flush()

    for name in ["Zebra", "Apple", "Mango"]:
        p = Project(organization_id=org.id, portfolio_id=portfolio.id, name=name)
        db_session.add(p)
    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    names = [p["project_name"] for p in res.json()["projects"]]
    assert names == ["Apple", "Mango", "Zebra"]


def test_DB20_portfolio_dashboard_excludes_other_portfolio_projects(client, db_session):
    """DB-20: Only projects belonging to the requested portfolio are shown."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    portfolio_a = Portfolio(organization_id=org.id, name="Portfolio A")
    portfolio_b = Portfolio(organization_id=org.id, name="Portfolio B")
    db_session.add_all([portfolio_a, portfolio_b])
    db_session.flush()

    pa_proj = Project(organization_id=org.id, portfolio_id=portfolio_a.id, name="In A")
    pb_proj = Project(organization_id=org.id, portfolio_id=portfolio_b.id, name="In B")
    db_session.add_all([pa_proj, pb_proj])
    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio_a.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.json()["project_count"] == 1
    assert res.json()["projects"][0]["project_name"] == "In A"


def test_DB21_portfolio_dashboard_utilization_values(client, db_session):
    """DB-21: budget_utilization_pct in portfolio summary matches exact calculation."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    portfolio = Portfolio(organization_id=org.id, name="Util Portfolio")
    db_session.add(portfolio)
    db_session.flush()

    p = Project(organization_id=org.id, portfolio_id=portfolio.id, name="Util Project")
    db_session.add(p)
    db_session.flush()
    _set_budget(db_session, p.id, Decimal("200"))
    _add_expense(db_session, p.id, Decimal("150"))  # 75%
    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    project_data = res.json()["projects"][0]
    assert Decimal(str(project_data["budget_utilization_pct"])) == Decimal("75.0")
    assert project_data["health_flag"] == "on_track"


# ============================================================
# Portfolio Dashboard — Permissions
# ============================================================


def test_DB22_portfolio_dashboard_requires_broad_manager(client, db_session):
    """DB-22: project_manager is forbidden from portfolio dashboard."""
    org = create_org(db_session)
    pm, pm_token = make_user_in_org(db_session, org.id, ["project_manager"])
    portfolio = Portfolio(organization_id=org.id, name="PM Blocked")
    db_session.add(portfolio)
    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio.id}/dashboard",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res.status_code == 403


def test_DB23_portfolio_dashboard_requires_broad_manager_team_member_blocked(client, db_session):
    """DB-23: team_member is forbidden from portfolio dashboard."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])
    portfolio = Portfolio(organization_id=org.id, name="TM Blocked")
    db_session.add(portfolio)
    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_DB24_portfolio_dashboard_portfolio_manager_allowed(client, db_session):
    """DB-24: portfolio_manager can access portfolio dashboard."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    portfolio = Portfolio(organization_id=org.id, name="PM Portfolio")
    db_session.add(portfolio)
    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200


def test_DB25_portfolio_dashboard_cross_tenant_returns_404(client, db_session):
    """DB-25: Cross-org portfolio access returns 404."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    _, token_a = make_user_in_org(db_session, org_a.id, ["org_admin"])
    portfolio_b = Portfolio(organization_id=org_b.id, name="Org B Portfolio")
    db_session.add(portfolio_b)
    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio_b.id}/dashboard",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 404


def test_DB26_portfolio_dashboard_nonexistent_returns_404(client, db_session):
    """DB-26: Non-existent portfolio ID returns 404."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, ["org_admin"])

    res = client.get(
        f"/api/v1/portfolios/{uuid.uuid4()}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


def test_DB27_portfolio_dashboard_requires_auth(client, db_session):
    """DB-27: Unauthenticated request returns 401."""
    org = create_org(db_session)
    portfolio = Portfolio(organization_id=org.id, name="Auth Portfolio")
    db_session.add(portfolio)
    db_session.commit()

    res = client.get(f"/api/v1/portfolios/{portfolio.id}/dashboard")
    assert res.status_code == 401


# ============================================================
# Edge cases
# ============================================================


def test_DB28_project_dashboard_exact_spend_equals_planned(client, db_session):
    """DB-28: actual == planned is NOT off_track (> is the condition). But
    utilization == 100 >= 80 → at_risk."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    project = Project(organization_id=org.id, name="Exact Budget Project")
    db_session.add(project)
    db_session.flush()

    _set_budget(db_session, project.id, Decimal("1000"))
    _add_expense(db_session, project.id, Decimal("1000"))
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{project.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    d = res.json()
    assert Decimal(str(d["budget_utilization_pct"])) == Decimal("100.0")
    assert d["health_flag"] == "at_risk"  # 100 >= 80 triggers at_risk, not off_track


def test_DB29_portfolio_dashboard_deleted_projects_excluded(client, db_session):
    """DB-29: Soft-deleted projects do not appear in portfolio dashboard."""
    from datetime import datetime, timezone
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    portfolio = Portfolio(organization_id=org.id, name="Delete Test Portfolio")
    db_session.add(portfolio)
    db_session.flush()

    active = Project(organization_id=org.id, portfolio_id=portfolio.id, name="Active")
    deleted = Project(
        organization_id=org.id,
        portfolio_id=portfolio.id,
        name="Deleted",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add_all([active, deleted])
    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.json()["project_count"] == 1
    assert res.json()["projects"][0]["project_name"] == "Active"


def test_DB30_portfolio_dashboard_open_risk_count_in_summary(client, db_session):
    """DB-30: Portfolio summary correctly reports open_risk_count per project."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    portfolio = Portfolio(organization_id=org.id, name="Risk Summary Portfolio")
    db_session.add(portfolio)
    db_session.flush()

    p = Project(organization_id=org.id, portfolio_id=portfolio.id, name="Risky Project")
    db_session.add(p)
    db_session.flush()

    _add_risk(db_session, p.id, RiskLevel.medium, RiskStatus.open)
    _add_risk(db_session, p.id, RiskLevel.high, RiskStatus.open)
    _add_risk(db_session, p.id, RiskLevel.low, RiskStatus.closed)
    db_session.commit()

    res = client.get(
        f"/api/v1/portfolios/{portfolio.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    summary = res.json()["projects"][0]
    assert summary["open_risk_count"] == 2
    assert summary["health_flag"] == "at_risk"  # high-impact open risk
