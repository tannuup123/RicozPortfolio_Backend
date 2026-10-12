"""Automated End-to-End Integration Tests for MVP User Journeys (Phase 11).

Covers:
- AUT-J01: Full Golden Path (Register -> Strategic Goal -> Idea -> Business Case
  -> Approval -> Portfolio -> Convert to Project -> Tasks -> Milestones
  -> Budget -> Expenses -> Risks -> Project & Portfolio Dashboards)
- AUT-J02: Rejection Branch (Submit Idea -> Business Case -> Reject -> Verify Project Conversion blocked with 400)
- AUT-J03: Direct Project Path (Direct Project Creation without Idea -> Tasks & Milestones -> Budget -> Dashboards)
- AUT-J04: Multi-Project Portfolio Aggregation (Projects with on_track, at_risk, off_track health flags)
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


def make_user_in_org(
    db_session,
    org_id: uuid.UUID,
    role_names: list[str],
    email: str | None = None,
    name: str = "Journey User",
) -> tuple[User, str]:
    user = User(
        email=email or f"user_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("Password123!"),
        name=name,
        organization_id=org_id,
        is_active=True,
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


def test_AUT_J01_full_governance_golden_path(client, db_session):
    """AUT-J01: Execute complete end-to-end MVP governance and execution journey."""
    # 1. Register organization and admin
    admin_email = f"alice_{uuid.uuid4().hex[:6]}@acme.com"
    res_reg = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Acme Global",
            "name": "Alice Admin",
            "email": admin_email,
            "password": "Password123!",
        },
    )
    assert res_reg.status_code == 201
    admin_token = res_reg.json()["access_token"]

    # Retrieve created organization_id via /auth/me
    res_me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_me.status_code == 200
    org_id = uuid.UUID(res_me.json()["organization_id"])

    # 2. Create Portfolio Manager and Team Member users
    pm_user, pm_token = make_user_in_org(db_session, org_id, ["portfolio_manager"], name="Bob PM")
    dev_user, dev_token = make_user_in_org(db_session, org_id, ["team_member"], name="Charlie Dev")

    # 3. Create Strategic Goal as Admin
    res_goal = client.post(
        "/api/v1/strategic-goals",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Accelerate Digital Transformation", "description": "FY26 Core Objective"},
    )
    assert res_goal.status_code == 201
    goal_id = res_goal.json()["id"]

    # 4. Team Member creates and submits an Idea
    res_idea = client.post(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {dev_token}"},
        json={
            "title": "Cloud Migration Accelerator",
            "description": "Standardized templates for AWS/Azure deployment",
            "strategic_goal_id": goal_id,
        },
    )
    assert res_idea.status_code == 201
    assert res_idea.json()["status"] == "submitted"
    idea_id = res_idea.json()["id"]

    # 5. Portfolio Manager creates Business Case
    res_bc = client.post(
        f"/api/v1/ideas/{idea_id}/business-case",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"estimated_cost": 50000.0, "estimated_benefit": 125000.0},
    )
    assert res_bc.status_code == 201
    assert Decimal(str(res_bc.json()["roi"])) == Decimal("1.50")

    # 6. Portfolio Manager approves Idea
    res_app = client.post(
        f"/api/v1/ideas/{idea_id}/approvals",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"decision": "approved", "notes": "Approved for Q1 budget"},
    )
    assert res_app.status_code == 201

    # 7. Portfolio Manager creates Portfolio
    res_port = client.post(
        "/api/v1/portfolios",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"name": "Enterprise Cloud 2026", "description": "Core Cloud Modernization"},
    )
    assert res_port.status_code == 201
    portfolio_id = res_port.json()["id"]

    # 8. Convert Idea into Project within Portfolio
    res_conv = client.post(
        f"/api/v1/ideas/{idea_id}/convert",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"portfolio_id": portfolio_id},
    )
    assert res_conv.status_code == 201
    project_id = res_conv.json()["id"]
    assert res_conv.json()["source_idea_id"] == idea_id
    assert res_conv.json()["status"] == "planned"

    # Add Charlie as team member on project
    res_mem = client.post(
        f"/api/v1/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"user_id": str(dev_user.id), "project_role": "member"},
    )
    assert res_mem.status_code == 201

    # 9. Create Milestones and Tasks
    res_m = client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"title": "Architecture Sign-off", "target_date": str(date.today())},
    )
    assert res_m.status_code == 201

    res_task = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"title": "Draft Terraform Modules", "assignee_id": str(dev_user.id)},
    )
    assert res_task.status_code == 201
    task_id = res_task.json()["id"]

    # 10. Team Member updates task status
    res_task_patch = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {dev_token}"},
        json={"status": "done"},
    )
    assert res_task_patch.status_code == 200
    assert res_task_patch.json()["status"] == "done"

    # 11. Budget & Expenses
    res_b = client.put(
        f"/api/v1/projects/{project_id}/budget",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"amount": 10000.0, "currency": "USD"},
    )
    assert res_b.status_code == 200

    res_exp = client.post(
        f"/api/v1/projects/{project_id}/expenses",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"amount": 8500.0, "description": "Cloud infra licensing", "date": str(date.today())},
    )
    assert res_exp.status_code == 201

    # 12. Risks
    res_r = client.post(
        f"/api/v1/projects/{project_id}/risks",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"title": "Vendor Lock-in", "probability": "medium", "impact": "high", "status": "open"},
    )
    assert res_r.status_code == 201

    # 13. Verify Project Dashboard
    res_proj_dash = client.get(
        f"/api/v1/projects/{project_id}/dashboard",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_proj_dash.status_code == 200
    p_dash = res_proj_dash.json()
    assert p_dash["task_total"] == 1
    assert p_dash["task_done"] == 1
    assert Decimal(str(p_dash["task_completion_pct"])) == Decimal("100.0")
    assert Decimal(str(p_dash["budget_planned"])) == Decimal("10000.0")
    assert Decimal(str(p_dash["budget_actual"])) == Decimal("8500.0")
    assert Decimal(str(p_dash["budget_utilization_pct"])) == Decimal("85.0")
    assert p_dash["has_high_impact_open_risk"] is True
    assert p_dash["health_flag"] == "at_risk"

    # 14. Verify Portfolio Dashboard
    res_port_dash = client.get(
        f"/api/v1/portfolios/{portfolio_id}/dashboard",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_port_dash.status_code == 200
    port_dash = res_port_dash.json()
    assert port_dash["project_count"] == 1
    assert port_dash["projects"][0]["project_id"] == str(project_id)
    assert port_dash["projects"][0]["health_flag"] == "at_risk"


def test_AUT_J02_rejection_branch_blocks_conversion(client, db_session):
    """AUT-J02: Rejection decision blocks idea conversion to project."""
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()

    pm_user, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    # Create Idea
    res_idea = client.post(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"title": "High Risk Speculative Idea", "description": "Uncertain ROI"},
    )
    idea_id = res_idea.json()["id"]

    # Submit Idea
    client.post(f"/api/v1/ideas/{idea_id}/submit", headers={"Authorization": f"Bearer {pm_token}"})

    # Attach Business Case
    client.post(
        f"/api/v1/ideas/{idea_id}/business-case",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"estimated_cost": 200000.0, "estimated_benefit": 50000.0},
    )

    # Reject Idea
    res_app = client.post(
        f"/api/v1/ideas/{idea_id}/approvals",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"decision": "rejected", "notes": "Negative expected ROI"},
    )
    assert res_app.status_code == 201

    # Attempt to convert rejected idea -> 400
    res_conv = client.post(
        f"/api/v1/ideas/{idea_id}/convert",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={},
    )
    assert res_conv.status_code == 400
    assert "approved" in res_conv.json()["detail"].lower()


def test_AUT_J03_direct_project_creation_path(client, db_session):
    """AUT-J03: Create project directly without idea and execute metrics lifecycle."""
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()

    pm_user, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    res_proj = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"name": "Direct Maintenance Initiative", "description": "Routine upkeep"},
    )
    assert res_proj.status_code == 201
    proj_id = res_proj.json()["id"]
    assert res_proj.json()["source_idea_id"] is None

    # Verify project dashboard initializes healthy
    res_dash = client.get(
        f"/api/v1/projects/{proj_id}/dashboard",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_dash.status_code == 200
    assert res_dash.json()["health_flag"] == "on_track"


def test_AUT_J04_multi_project_portfolio_health_aggregation(client, db_session):
    """AUT-J04: Portfolio dashboard correctly aggregates multiple projects with distinct health statuses."""
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()

    pm_user, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    res_port = client.post(
        "/api/v1/portfolios",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"name": "Consolidated Portfolio"},
    )
    port_id = res_port.json()["id"]

    # 1. On Track Project (40% spend)
    p1 = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"name": "Project Alpha", "portfolio_id": port_id},
    ).json()["id"]
    client.put(f"/api/v1/projects/{p1}/budget", headers={"Authorization": f"Bearer {pm_token}"}, json={"amount": 1000.0, "currency": "USD"})
    client.post(f"/api/v1/projects/{p1}/expenses", headers={"Authorization": f"Bearer {pm_token}"}, json={"amount": 400.0, "description": "e", "date": str(date.today())})

    # 2. At Risk Project (85% spend)
    p2 = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"name": "Project Beta", "portfolio_id": port_id},
    ).json()["id"]
    client.put(f"/api/v1/projects/{p2}/budget", headers={"Authorization": f"Bearer {pm_token}"}, json={"amount": 1000.0, "currency": "USD"})
    client.post(f"/api/v1/projects/{p2}/expenses", headers={"Authorization": f"Bearer {pm_token}"}, json={"amount": 850.0, "description": "e", "date": str(date.today())})

    # 3. Off Track Project (120% spend)
    p3 = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"name": "Project Gamma", "portfolio_id": port_id},
    ).json()["id"]
    client.put(
        f"/api/v1/projects/{p3}/budget",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"amount": 1000.0, "currency": "USD"},
    )
    client.post(
        f"/api/v1/projects/{p3}/expenses",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"amount": 1200.0, "description": "e", "date": str(date.today())},
    )

    res_dash = client.get(
        f"/api/v1/portfolios/{port_id}/dashboard",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_dash.status_code == 200
    projects = res_dash.json()["projects"]
    assert len(projects) == 3
    # Sorted alphabetically
    assert projects[0]["project_name"] == "Project Alpha"
    assert projects[0]["health_flag"] == "on_track"

    assert projects[1]["project_name"] == "Project Beta"
    assert projects[1]["health_flag"] == "at_risk"

    assert projects[2]["project_name"] == "Project Gamma"
    assert projects[2]["health_flag"] == "off_track"
