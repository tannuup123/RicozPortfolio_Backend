"""Comprehensive Multi-Tenant Isolation Test Suite (Phase 11).

Verifies TI-01 through TI-60: across all API resources, nested routes, query filters,
and related foreign IDs, cross-organization data access or tampering is strictly
blocked with 404 Not Found (or filtered out in list operations).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.business_case import BusinessCase
from app.models.idea import Idea, IdeaStatus
from app.models.milestone import Milestone
from app.models.organization import Organization
from app.models.portfolio import Portfolio
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectMemberRole
from app.models.risk import Risk, RiskLevel, RiskStatus
from app.models.role import Role
from app.models.strategic_goal import StrategicGoal
from app.models.task import Task
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


def create_org(db_session, name: str | None = None) -> Organization:
    org = Organization(name=name or f"Org {uuid.uuid4().hex[:6]}")
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


def test_TI_01_to_04_users_tenant_isolation(client, db_session):
    """TI-01 to TI-04: User listing and mutations strictly isolated to caller's org."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    admin_a, token_a = make_user_in_org(db_session, org_a.id, ["org_admin"])
    user_b, _ = make_user_in_org(db_session, org_b.id, ["team_member"])

    # TI-01: List users only returns org A users
    res_list = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token_a}"})
    assert res_list.status_code == 200
    user_ids = [u["id"] for u in res_list.json()["items"]]
    assert str(admin_a.id) in user_ids
    assert str(user_b.id) not in user_ids

    # TI-02: Create user automatically binds to caller's org
    res_create = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "email": f"new_{uuid.uuid4().hex[:6]}@example.com",
            "name": "New User Org A",
            "password": "Password123!",
            "roles": ["team_member"],
        },
    )
    assert res_create.status_code == 201
    created_id = res_create.json()["id"]
    created_db_user = db_session.query(User).filter(User.id == uuid.UUID(created_id)).first()
    assert created_db_user.organization_id == org_a.id

    # TI-03: Update roles of Org B user returns 404
    res_roles = client.patch(
        f"/api/v1/users/{user_b.id}/roles",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"roles": ["project_manager"]},
    )
    assert res_roles.status_code == 404

    # TI-04: Update profile of Org B user returns 404
    res_patch = client.patch(
        f"/api/v1/users/{user_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Hacked Name"},
    )
    assert res_patch.status_code == 404


def test_TI_05_to_08_strategic_goals_tenant_isolation(client, db_session):
    """TI-05 to TI-08: Strategic goals operations strictly isolated."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    pm_a, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    goal_b = StrategicGoal(organization_id=org_b.id, title="Org B Goal")
    db_session.add(goal_b)
    db_session.commit()

    # TI-05: List goals returns only Org A goals
    res_list = client.get("/api/v1/strategic-goals", headers={"Authorization": f"Bearer {token_a}"})
    assert res_list.status_code == 200
    goal_ids = [g["id"] for g in res_list.json()["items"]]
    assert str(goal_b.id) not in goal_ids

    # TI-06: GET Org B goal returns 404
    res_get = client.get(f"/api/v1/strategic-goals/{goal_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_get.status_code == 404

    # TI-07: PATCH Org B goal returns 404
    res_patch = client.patch(
        f"/api/v1/strategic-goals/{goal_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Hacked Goal"},
    )
    assert res_patch.status_code == 404

    # TI-08: DELETE Org B goal returns 404
    res_del = client.delete(f"/api/v1/strategic-goals/{goal_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_del.status_code == 404


def test_TI_09_to_14_ideas_tenant_isolation(client, db_session):
    """TI-09 to TI-14: Ideas operations and foreign goal references strictly isolated."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    user_a, token_a = make_user_in_org(db_session, org_a.id, ["team_member"])
    user_b, _ = make_user_in_org(db_session, org_b.id, ["team_member"])

    goal_b = StrategicGoal(organization_id=org_b.id, title="Org B Goal")
    idea_b = Idea(organization_id=org_b.id, title="Org B Idea", description="Desc B", author_id=user_b.id, status=IdeaStatus.draft)
    db_session.add_all([goal_b, idea_b])
    db_session.commit()

    # TI-09: List ideas does not leak Org B idea
    res_list = client.get("/api/v1/ideas", headers={"Authorization": f"Bearer {token_a}"})
    assert res_list.status_code == 200
    idea_ids = [i["id"] for i in res_list.json()["items"]]
    assert str(idea_b.id) not in idea_ids

    # TI-10: POST idea referencing Org B strategic_goal_id returns 404
    res_post_goal = client.post(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Org A Idea", "description": "Desc A", "strategic_goal_id": str(goal_b.id)},
    )
    assert res_post_goal.status_code == 404

    # TI-11: GET Org B idea returns 404
    res_get = client.get(f"/api/v1/ideas/{idea_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_get.status_code == 404

    # TI-12: PATCH Org B idea returns 404
    res_patch = client.patch(
        f"/api/v1/ideas/{idea_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Hacked Idea"},
    )
    assert res_patch.status_code == 404

    # TI-13: DELETE Org B idea returns 404 (even for PM in Org A)
    _, pm_token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    res_del = client.delete(f"/api/v1/ideas/{idea_b.id}", headers={"Authorization": f"Bearer {pm_token_a}"})
    assert res_del.status_code == 404

    # TI-14: POST submit Org B idea returns 404
    res_sub = client.post(f"/api/v1/ideas/{idea_b.id}/submit", headers={"Authorization": f"Bearer {token_a}"})
    assert res_sub.status_code == 404


def test_TI_15_to_19_business_cases_and_approvals(client, db_session):
    """TI-15 to TI-19: Business cases and approvals on cross-org ideas return 404."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    _, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    user_b, _ = make_user_in_org(db_session, org_b.id, ["portfolio_manager"])

    idea_b = Idea(organization_id=org_b.id, title="Org B Idea", description="Desc B", author_id=user_b.id, status=IdeaStatus.submitted)
    db_session.add(idea_b)
    db_session.flush()

    bc_b = BusinessCase(idea_id=idea_b.id, estimated_cost=Decimal("100"), estimated_benefit=Decimal("200"))
    db_session.add(bc_b)
    db_session.commit()

    # TI-15: GET business case on Org B idea returns 404
    res_bc_get = client.get(f"/api/v1/ideas/{idea_b.id}/business-case", headers={"Authorization": f"Bearer {token_a}"})
    assert res_bc_get.status_code == 404

    # TI-16: POST business case on Org B idea returns 404
    idea_b_no_bc = Idea(organization_id=org_b.id, title="No BC", description="No BC Desc", author_id=user_b.id, status=IdeaStatus.submitted)
    db_session.add(idea_b_no_bc)
    db_session.commit()
    res_bc_post = client.post(
        f"/api/v1/ideas/{idea_b_no_bc.id}/business-case",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"estimated_cost": 10.0, "estimated_benefit": 20.0},
    )
    assert res_bc_post.status_code == 404

    # TI-17: PATCH business case on Org B idea returns 404
    res_bc_patch = client.patch(
        f"/api/v1/ideas/{idea_b.id}/business-case",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"estimated_cost": 50.0, "estimated_benefit": 250.0},
    )
    assert res_bc_patch.status_code == 404

    # TI-18: GET approvals history on Org B idea returns 404
    res_app_get = client.get(f"/api/v1/ideas/{idea_b.id}/approvals", headers={"Authorization": f"Bearer {token_a}"})
    assert res_app_get.status_code == 404

    # TI-19: POST approval on Org B idea returns 404
    res_app_post = client.post(
        f"/api/v1/ideas/{idea_b.id}/approvals",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"decision": "approved", "notes": "Hacked"},
    )
    assert res_app_post.status_code == 404


def test_TI_20_to_25_idea_conversion_and_portfolios(client, db_session):
    """TI-20 to TI-25: Idea conversion and portfolio operations strictly isolated."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    user_a, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    user_b, _ = make_user_in_org(db_session, org_b.id, ["portfolio_manager"])

    idea_a = Idea(organization_id=org_a.id, title="Idea A", description="Desc A", author_id=user_a.id, status=IdeaStatus.approved)
    idea_b = Idea(organization_id=org_b.id, title="Idea B", description="Desc B", author_id=user_b.id, status=IdeaStatus.approved)
    port_b = Portfolio(organization_id=org_b.id, name="Port B")
    db_session.add_all([idea_a, idea_b, port_b])
    db_session.commit()

    # TI-20: Convert Org B idea returns 404
    res_conv_b = client.post(f"/api/v1/ideas/{idea_b.id}/convert", headers={"Authorization": f"Bearer {token_a}"}, json={})
    assert res_conv_b.status_code == 404

    # TI-21: Convert Org A idea with Org B portfolio_id returns 404
    res_conv_port_b = client.post(
        f"/api/v1/ideas/{idea_a.id}/convert",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"portfolio_id": str(port_b.id)},
    )
    assert res_conv_port_b.status_code == 404

    # TI-22: List portfolios does not include Port B
    res_port_list = client.get("/api/v1/portfolios", headers={"Authorization": f"Bearer {token_a}"})
    assert res_port_list.status_code == 200
    port_ids = [p["id"] for p in res_port_list.json()["items"]]
    assert str(port_b.id) not in port_ids

    # TI-23: GET Org B portfolio returns 404
    res_port_get = client.get(f"/api/v1/portfolios/{port_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_port_get.status_code == 404

    # TI-24: PATCH Org B portfolio returns 404
    res_port_patch = client.patch(
        f"/api/v1/portfolios/{port_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Hacked Port"},
    )
    assert res_port_patch.status_code == 404

    # TI-25: DELETE Org B portfolio returns 404
    res_port_del = client.delete(f"/api/v1/portfolios/{port_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_port_del.status_code == 404


def test_TI_26_to_32_projects_tenant_isolation(client, db_session):
    """TI-26 to TI-32: Project listing, creation, and mutation isolation."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    _, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    port_b = Portfolio(organization_id=org_b.id, name="Port B")
    proj_b = Project(organization_id=org_b.id, name="Project B")
    db_session.add_all([port_b, proj_b])
    db_session.commit()

    # TI-26: List projects does not return Project B
    res_list = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token_a}"})
    assert res_list.status_code == 200
    proj_ids = [p["id"] for p in res_list.json()["items"]]
    assert str(proj_b.id) not in proj_ids

    # TI-27: Filter projects by cross-org portfolio returns 404
    res_filter = client.get(f"/api/v1/projects?portfolio_id={port_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_filter.status_code == 404

    # TI-28: Create direct project targeting Org B portfolio returns 404
    res_post_port = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Proj Org A", "portfolio_id": str(port_b.id)},
    )
    assert res_post_port.status_code == 404

    # TI-29: GET Org B project returns 404
    res_get = client.get(f"/api/v1/projects/{proj_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_get.status_code == 404

    # TI-30: PATCH Org B project returns 404
    res_patch = client.patch(
        f"/api/v1/projects/{proj_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Hacked Proj"},
    )
    assert res_patch.status_code == 404

    # TI-31: PATCH Org A project setting Org B portfolio returns 404
    proj_a = Project(organization_id=org_a.id, name="Project A")
    db_session.add(proj_a)
    db_session.commit()
    res_patch_port = client.patch(
        f"/api/v1/projects/{proj_a.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"portfolio_id": str(port_b.id)},
    )
    assert res_patch_port.status_code == 404

    # TI-32: DELETE Org B project returns 404
    res_del = client.delete(f"/api/v1/projects/{proj_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_del.status_code == 404


def test_TI_33_to_37_project_members_tenant_isolation(client, db_session):
    """TI-33 to TI-37: Project member management isolation."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    _, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    user_b, _ = make_user_in_org(db_session, org_b.id, ["team_member"])

    proj_a = Project(organization_id=org_a.id, name="Project A")
    proj_b = Project(organization_id=org_b.id, name="Project B")
    db_session.add_all([proj_a, proj_b])
    db_session.flush()

    member_b = ProjectMember(project_id=proj_b.id, user_id=user_b.id, project_role=ProjectMemberRole.manager)
    db_session.add(member_b)
    db_session.commit()

    # TI-33: GET members on Org B project returns 404
    res_mem_list = client.get(f"/api/v1/projects/{proj_b.id}/members", headers={"Authorization": f"Bearer {token_a}"})
    assert res_mem_list.status_code == 404

    # TI-34: POST member to Org B project returns 404
    res_mem_post = client.post(
        f"/api/v1/projects/{proj_b.id}/members",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"user_id": str(user_b.id), "project_role": "member"},
    )
    assert res_mem_post.status_code == 404

    # TI-35: POST cross-org user to Org A project returns 404
    res_add_b_to_a = client.post(
        f"/api/v1/projects/{proj_a.id}/members",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"user_id": str(user_b.id), "project_role": "member"},
    )
    assert res_add_b_to_a.status_code == 404

    # TI-36: PATCH member role on Org B project returns 404
    res_patch_role = client.patch(
        f"/api/v1/projects/{proj_b.id}/members/{user_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"project_role": "member"},
    )
    assert res_patch_role.status_code == 404

    # TI-37: DELETE member from Org B project returns 404
    res_del_mem = client.delete(
        f"/api/v1/projects/{proj_b.id}/members/{user_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_del_mem.status_code == 404


def test_TI_38_to_44_tasks_tenant_isolation(client, db_session):
    """TI-38 to TI-44: Task operations and cross-org assignee isolation."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    _, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    user_b, _ = make_user_in_org(db_session, org_b.id, ["team_member"])

    proj_a = Project(organization_id=org_a.id, name="Project A")
    proj_b = Project(organization_id=org_b.id, name="Project B")
    db_session.add_all([proj_a, proj_b])
    db_session.flush()

    task_b = Task(project_id=proj_b.id, title="Task B")
    task_a = Task(project_id=proj_a.id, title="Task A")
    db_session.add_all([task_b, task_a])
    db_session.commit()

    # TI-38: GET tasks list on Org B project returns 404
    res_task_list = client.get(f"/api/v1/projects/{proj_b.id}/tasks", headers={"Authorization": f"Bearer {token_a}"})
    assert res_task_list.status_code == 404

    # TI-39: POST task on Org B project returns 404
    res_task_post = client.post(
        f"/api/v1/projects/{proj_b.id}/tasks",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Hacked Task"},
    )
    assert res_task_post.status_code == 404

    # TI-40: POST task on Org A project with Org B assignee returns 404
    res_post_assignee = client.post(
        f"/api/v1/projects/{proj_a.id}/tasks",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Task with B", "assignee_id": str(user_b.id)},
    )
    assert res_post_assignee.status_code == 404

    # TI-41: GET Org B task directly returns 404
    res_task_get = client.get(f"/api/v1/tasks/{task_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_task_get.status_code == 404

    # TI-42: PATCH Org B task returns 404
    res_task_patch = client.patch(
        f"/api/v1/tasks/{task_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Hacked Title"},
    )
    assert res_task_patch.status_code == 404

    # TI-43: PATCH Org A task setting Org B assignee returns 404
    res_patch_assignee = client.patch(
        f"/api/v1/tasks/{task_a.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"assignee_id": str(user_b.id)},
    )
    assert res_patch_assignee.status_code == 404

    # TI-44: DELETE Org B task returns 404
    res_task_del = client.delete(f"/api/v1/tasks/{task_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_task_del.status_code == 404


def test_TI_45_to_49_milestones_tenant_isolation(client, db_session):
    """TI-45 to TI-49: Milestone operations isolation."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    _, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])

    proj_b = Project(organization_id=org_b.id, name="Project B")
    db_session.add(proj_b)
    db_session.flush()

    m_b = Milestone(project_id=proj_b.id, title="Milestone B")
    db_session.add(m_b)
    db_session.commit()

    # TI-45: GET milestones list on Org B project returns 404
    res_m_list = client.get(f"/api/v1/projects/{proj_b.id}/milestones", headers={"Authorization": f"Bearer {token_a}"})
    assert res_m_list.status_code == 404

    # TI-46: POST milestone on Org B project returns 404
    res_m_post = client.post(
        f"/api/v1/projects/{proj_b.id}/milestones",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Hacked Milestone"},
    )
    assert res_m_post.status_code == 404

    # TI-47: GET Org B milestone directly returns 404
    res_m_get = client.get(f"/api/v1/milestones/{m_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_m_get.status_code == 404

    # TI-48: PATCH Org B milestone returns 404
    res_m_patch = client.patch(
        f"/api/v1/milestones/{m_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Hacked Title"},
    )
    assert res_m_patch.status_code == 404

    # TI-49: DELETE Org B milestone returns 404
    res_m_del = client.delete(f"/api/v1/milestones/{m_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_m_del.status_code == 404


def test_TI_50_to_58_budgets_expenses_risks_isolation(client, db_session):
    """TI-50 to TI-58: Budget, expense, and risk operations isolation."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    _, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])

    proj_b = Project(organization_id=org_b.id, name="Project B")
    db_session.add(proj_b)
    db_session.flush()

    risk_b = Risk(project_id=proj_b.id, title="Risk B", probability=RiskLevel.medium, impact=RiskLevel.medium, status=RiskStatus.open)
    db_session.add(risk_b)
    db_session.commit()

    # TI-50: GET budget on Org B project returns 404
    assert client.get(f"/api/v1/projects/{proj_b.id}/budget", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # TI-51: PUT budget on Org B project returns 404
    assert client.put(
        f"/api/v1/projects/{proj_b.id}/budget",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"amount": 1000.0, "currency": "USD"},
    ).status_code == 404

    # TI-52: GET expenses on Org B project returns 404
    assert client.get(f"/api/v1/projects/{proj_b.id}/expenses", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # TI-53: POST expense on Org B project returns 404
    assert client.post(
        f"/api/v1/projects/{proj_b.id}/expenses",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"amount": 50.0, "description": "Hacked", "date": str(date.today())},
    ).status_code == 404

    # TI-54: GET risks on Org B project returns 404
    assert client.get(f"/api/v1/projects/{proj_b.id}/risks", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # TI-55: POST risk on Org B project returns 404
    assert client.post(
        f"/api/v1/projects/{proj_b.id}/risks",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Hacked Risk"},
    ).status_code == 404

    # TI-56: GET Org B risk directly returns 404
    assert client.get(f"/api/v1/risks/{risk_b.id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # TI-57: PATCH Org B risk returns 404
    assert client.patch(
        f"/api/v1/risks/{risk_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Hacked Title"},
    ).status_code == 404

    # TI-58: DELETE Org B risk returns 404
    assert client.delete(f"/api/v1/risks/{risk_b.id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404


def test_TI_59_to_60_dashboards_tenant_isolation(client, db_session):
    """TI-59 to TI-60: Project and portfolio dashboards isolation."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    _, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])

    port_b = Portfolio(organization_id=org_b.id, name="Port B")
    proj_b = Project(organization_id=org_b.id, name="Project B")
    db_session.add_all([port_b, proj_b])
    db_session.commit()

    # TI-59: GET Org B project dashboard returns 404
    assert client.get(f"/api/v1/projects/{proj_b.id}/dashboard", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # TI-60: GET Org B portfolio dashboard returns 404
    assert client.get(f"/api/v1/portfolios/{port_b.id}/dashboard", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404
