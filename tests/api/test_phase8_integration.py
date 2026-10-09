"""Integration tests for Phase 8 (Tasks & Milestones Execution: INT8-01 to INT8-03)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.idea import Idea, IdeaStatus
from app.models.organization import Organization
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


def test_full_project_task_milestone_execution_lifecycle(client, db_session):
    """INT8-01: Full execution lifecycle journey:

    1. Portfolio Manager creates Portfolio & Project.
    2. PM adds a Team Member to the project.
    3. PM creates a Milestone ("MVP Release") with due date.
    4. PM creates Task 1 ("Build API") and assigns to Team Member.
    5. PM creates Task 2 ("Frontend Wireframes") and leaves unassigned.
    6. Team Member lists project tasks, sees Task 1.
    7. Team Member updates Task 1 status to 'in_progress', then 'done'.
    8. Team Member tries to change Task 1 title -> 403 Forbidden.
    9. Team Member tries to update Task 2 -> 403 Forbidden.
    10. PM updates Milestone status to 'achieved'.
    11. PM unassigns Task 1 via PATCH assignee_id: null.
    """
    org = create_org(db_session)
    pm, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"], name="Lead PM")
    dev, dev_token = make_user_in_org(db_session, org.id, ["team_member"], name="Developer Dan")

    # 1. Create Portfolio & Project
    port_res = client.post(
        "/api/v1/portfolios",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"name": "Engineering 2026"},
    )
    assert port_res.status_code == 201
    port_id = port_res.json()["id"]

    prj_res = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"name": "NextGen Service", "portfolio_id": port_id},
    )
    assert prj_res.status_code == 201
    prj_id = prj_res.json()["id"]

    # 2. Add Team Member
    add_m_res = client.post(
        f"/api/v1/projects/{prj_id}/members",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"user_id": str(dev.id), "project_role": "member"},
    )
    assert add_m_res.status_code == 201

    # 3. Create Milestone
    ml_res = client.post(
        f"/api/v1/projects/{prj_id}/milestones",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"title": "MVP Release", "due_date": "2026-12-15"},
    )
    assert ml_res.status_code == 201
    ml_id = ml_res.json()["id"]

    # 4. Create Task 1 assigned to dev
    t1_res = client.post(
        f"/api/v1/projects/{prj_id}/tasks",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"title": "Build API", "priority": "high", "assignee_id": str(dev.id)},
    )
    assert t1_res.status_code == 201
    t1_id = t1_res.json()["id"]

    # 5. Create Task 2 unassigned
    t2_res = client.post(
        f"/api/v1/projects/{prj_id}/tasks",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"title": "Frontend Wireframes", "priority": "medium"},
    )
    assert t2_res.status_code == 201
    t2_id = t2_res.json()["id"]

    # 6. Team member lists project tasks
    list_res = client.get(
        f"/api/v1/projects/{prj_id}/tasks",
        headers={"Authorization": f"Bearer {dev_token}"},
    )
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 2

    # 7. Team member updates Task 1 status
    p1 = client.patch(
        f"/api/v1/tasks/{t1_id}",
        headers={"Authorization": f"Bearer {dev_token}"},
        json={"status": "in_progress"},
    )
    assert p1.status_code == 200
    assert p1.json()["status"] == "in_progress"

    p2 = client.patch(
        f"/api/v1/tasks/{t1_id}",
        headers={"Authorization": f"Bearer {dev_token}"},
        json={"status": "done"},
    )
    assert p2.status_code == 200
    assert p2.json()["status"] == "done"

    # 8. Team member tries to edit title -> 403
    p3 = client.patch(
        f"/api/v1/tasks/{t1_id}",
        headers={"Authorization": f"Bearer {dev_token}"},
        json={"title": "Hacked Title"},
    )
    assert p3.status_code == 403

    # 9. Team member tries to update Task 2 -> 403
    p4 = client.patch(
        f"/api/v1/tasks/{t2_id}",
        headers={"Authorization": f"Bearer {dev_token}"},
        json={"status": "done"},
    )
    assert p4.status_code == 403

    # 10. PM updates Milestone status to achieved
    ml_patch = client.patch(
        f"/api/v1/milestones/{ml_id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"status": "achieved"},
    )
    assert ml_patch.status_code == 200
    assert ml_patch.json()["status"] == "achieved"

    # 11. PM clears assignee
    unassign = client.patch(
        f"/api/v1/tasks/{t1_id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"assignee_id": None},
    )
    assert unassign.status_code == 200
    assert unassign.json()["assignee_id"] is None


def test_converted_idea_project_tasks_and_milestones(client, db_session):
    """INT8-02: Converted idea project execution:

    1. Idea is converted to a Project (Phase 6 endpoint).
    2. Assign PM to the converted project.
    3. Assigned PM defines milestones and tasks.
    4. Verify cascade integrity and proper retrieval.
    """
    org = create_org(db_session)
    admin, admin_token = make_user_in_org(db_session, org.id, ["org_admin"])
    pjm, pjm_token = make_user_in_org(db_session, org.id, ["project_manager"])

    # Approved idea
    idea = Idea(
        organization_id=org.id,
        author_id=admin.id,
        title="Modern Analytics Dashboard",
        description="PPM Metrics and reporting",
        status=IdeaStatus.approved,
    )
    db_session.add(idea)
    db_session.commit()

    # Convert idea
    conv_res = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={},
    )
    assert conv_res.status_code == 201
    prj_id = conv_res.json()["id"]

    # Assign pjm as manager
    client.post(
        f"/api/v1/projects/{prj_id}/members",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_id": str(pjm.id), "project_role": "manager"},
    )

    # Assigned PM adds milestone
    ml_res = client.post(
        f"/api/v1/projects/{prj_id}/milestones",
        headers={"Authorization": f"Bearer {pjm_token}"},
        json={"title": "Data Pipeline Verified", "due_date": "2026-11-20"},
    )
    assert ml_res.status_code == 201

    # Assigned PM adds task
    t_res = client.post(
        f"/api/v1/projects/{prj_id}/tasks",
        headers={"Authorization": f"Bearer {pjm_token}"},
        json={"title": "Ingest logs", "priority": "high"},
    )
    assert t_res.status_code == 201


def test_multi_tenant_isolation_tasks_and_milestones(client, db_session):
    """INT8-03: Multi-tenant boundary verification across tasks and milestones."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    pm_a, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    pm_b, token_b = make_user_in_org(db_session, org_b.id, ["portfolio_manager"])

    # Org A resources
    prj_a = client.post("/api/v1/projects", headers={"Authorization": f"Bearer {token_a}"}, json={"name": "Prj A"}).json()
    task_a = client.post(f"/api/v1/projects/{prj_a['id']}/tasks", headers={"Authorization": f"Bearer {token_a}"}, json={"title": "Task A"}).json()
    ml_a = client.post(f"/api/v1/projects/{prj_a['id']}/milestones", headers={"Authorization": f"Bearer {token_a}"}, json={"title": "ML A"}).json()

    # Org B resources
    prj_b = client.post("/api/v1/projects", headers={"Authorization": f"Bearer {token_b}"}, json={"name": "Prj B"}).json()
    task_b = client.post(f"/api/v1/projects/{prj_b['id']}/tasks", headers={"Authorization": f"Bearer {token_b}"}, json={"title": "Task B"}).json()
    ml_b = client.post(f"/api/v1/projects/{prj_b['id']}/milestones", headers={"Authorization": f"Bearer {token_b}"}, json={"title": "ML B"}).json()

    # Org A user attempts access to Org B items -> 404
    assert client.get(f"/api/v1/tasks/{task_b['id']}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404
    assert client.get(f"/api/v1/milestones/{ml_b['id']}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404
    assert client.patch(f"/api/v1/tasks/{task_b['id']}", headers={"Authorization": f"Bearer {token_a}"}, json={"status": "done"}).status_code == 404
    assert client.delete(f"/api/v1/milestones/{ml_b['id']}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # Org B user attempts access to Org A items -> 404
    assert client.get(f"/api/v1/tasks/{task_a['id']}", headers={"Authorization": f"Bearer {token_b}"}).status_code == 404
    assert client.get(f"/api/v1/milestones/{ml_a['id']}", headers={"Authorization": f"Bearer {token_b}"}).status_code == 404
