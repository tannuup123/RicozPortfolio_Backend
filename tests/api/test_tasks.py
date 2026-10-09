"""Automated tests for Task API endpoints (Phase 8: TK-01 to TK-20)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectMemberRole
from app.models.role import Role
from app.models.task import Task, TaskPriority, TaskStatus
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


def test_create_task_as_pm_succeeds(client, db_session):
    """TK-01: Assigned PM creates task in project (201)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    payload = {
        "title": "Set up CI/CD pipeline",
        "description": "Configure GitHub Actions",
        "priority": "high",
        "status": "todo",
    }
    res = client.post(
        f"/api/v1/projects/{prj.id}/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Set up CI/CD pipeline"
    assert data["priority"] == "high"
    assert data["status"] == "todo"
    assert data["project_id"] == str(prj.id)
    assert data["assignee_id"] is None


def test_create_task_as_admin_succeeds(client, db_session):
    """TK-02: Org Admin creates task without explicit project membership (201)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj Admin")
    db_session.add(prj)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Admin Task"},
    )
    assert res.status_code == 201
    assert res.json()["title"] == "Admin Task"


def test_create_task_as_team_member_forbidden(client, db_session):
    """TK-03: Team member (assigned as member) cannot create task (403)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Member Attempt"},
    )
    assert res.status_code == 403


def test_create_task_with_valid_assignee_succeeds(client, db_session):
    """TK-04: PM creates task and assigns to org user (201)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    dev, _ = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Assigned Task", "assignee_id": str(dev.id)},
    )
    assert res.status_code == 201
    assert res.json()["assignee_id"] == str(dev.id)


def test_create_task_with_cross_org_assignee_returns_404(client, db_session):
    """TK-05: Assigning task to user in another org returns 404."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    pm_a, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    dev_b, _ = make_user_in_org(db_session, org_b.id, ["team_member"])

    prj_a = Project(organization_id=org_a.id, name="Prj A")
    db_session.add(prj_a)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj_a.id}/tasks",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Cross Org Task", "assignee_id": str(dev_b.id)},
    )
    assert res.status_code == 404


def test_list_tasks_as_assigned_member(client, db_session):
    """TK-06: Member on project can list tasks (200)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    t1 = Task(project_id=prj.id, title="Task 1", status=TaskStatus.todo)
    t2 = Task(project_id=prj.id, title="Task 2", status=TaskStatus.done)
    db_session.add_all([m, t1, t2])
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_tasks_as_unassigned_member_forbidden(client, db_session):
    """TK-07: Unassigned team member receives 403."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_list_tasks_filter_by_status_and_priority(client, db_session):
    """TK-08: Filter tasks by status and priority query params."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()

    t1 = Task(project_id=prj.id, title="T1", status=TaskStatus.in_progress, priority=TaskPriority.high)
    t2 = Task(project_id=prj.id, title="T2", status=TaskStatus.done, priority=TaskPriority.high)
    t3 = Task(project_id=prj.id, title="T3", status=TaskStatus.in_progress, priority=TaskPriority.low)
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/tasks?status=in_progress&priority=high",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "T1"


def test_get_task_by_id(client, db_session):
    """TK-09: Retrieve single task by ID (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    task = Task(project_id=prj.id, title="Specific Task")
    db_session.add(task)
    db_session.commit()

    res = client.get(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "Specific Task"


def test_get_task_not_found(client, db_session):
    """TK-10: Non-existent task returns 404."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    res = client.get(
        f"/api/v1/tasks/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


def test_update_task_as_pm_full_edit(client, db_session):
    """TK-11: PM can perform full edit of task attributes (200)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    dev, _ = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    task = Task(project_id=prj.id, title="Old Title", description="Old Desc", status=TaskStatus.todo)
    db_session.add(task)
    db_session.commit()

    res = client.patch(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "New Title",
            "description": "New Desc",
            "status": "in_progress",
            "priority": "high",
            "assignee_id": str(dev.id),
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "New Title"
    assert data["description"] == "New Desc"
    assert data["status"] == "in_progress"
    assert data["priority"] == "high"
    assert data["assignee_id"] == str(dev.id)


def test_team_member_can_update_own_assigned_task_status(client, db_session):
    """TK-12: Assigned team member can update status of their task (200)."""
    org = create_org(db_session)
    dev, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=dev.id, project_role=ProjectMemberRole.member)
    task = Task(project_id=prj.id, title="Assigned Work", assignee_id=dev.id, status=TaskStatus.todo)
    db_session.add_all([m, task])
    db_session.commit()

    res = client.patch(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "done"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "done"


def test_team_member_cannot_modify_other_fields_on_own_task(client, db_session):
    """TK-13: Assigned team member cannot edit title/description/priority/assignee (403)."""
    org = create_org(db_session)
    dev, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=dev.id, project_role=ProjectMemberRole.member)
    task = Task(project_id=prj.id, title="Assigned Work", assignee_id=dev.id, status=TaskStatus.todo)
    db_session.add_all([m, task])
    db_session.commit()

    # Attempt to change title
    res1 = client.patch(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Hacked Title"},
    )
    assert res1.status_code == 403

    # Attempt to change assignee
    res2 = client.patch(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"assignee_id": None},
    )
    assert res2.status_code == 403

    # Attempt to change priority
    res3 = client.patch(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"priority": "high"},
    )
    assert res3.status_code == 403


def test_team_member_cannot_update_unassigned_task_status(client, db_session):
    """TK-14: Team member on project cannot update status of task assigned to someone else (403)."""
    org = create_org(db_session)
    dev1, token1 = make_user_in_org(db_session, org.id, ["team_member"])
    dev2, _ = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m1 = ProjectMember(project_id=prj.id, user_id=dev1.id, project_role=ProjectMemberRole.member)
    m2 = ProjectMember(project_id=prj.id, user_id=dev2.id, project_role=ProjectMemberRole.member)
    task = Task(project_id=prj.id, title="Dev2 Work", assignee_id=dev2.id, status=TaskStatus.todo)
    db_session.add_all([m1, m2, task])
    db_session.commit()

    res = client.patch(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "done"},
    )
    assert res.status_code == 403


def test_patch_task_explicit_null_assignee_clears_it(client, db_session):
    """TK-15: PM unassigns task by sending explicit assignee_id: null."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    dev, _ = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    task = Task(project_id=prj.id, title="Work", assignee_id=dev.id)
    db_session.add(task)
    db_session.commit()

    res = client.patch(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"assignee_id": None},
    )
    assert res.status_code == 200
    assert res.json()["assignee_id"] is None


def test_patch_task_explicit_null_title_returns_422(client, db_session):
    """TK-16: Explicit null for title returns 422."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    task = Task(project_id=prj.id, title="Work")
    db_session.add(task)
    db_session.commit()

    res = client.patch(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": None},
    )
    assert res.status_code == 422


def test_delete_task_as_pm_succeeds(client, db_session):
    """TK-17: PM can delete task (204)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    task = Task(project_id=prj.id, title="To Delete")
    db_session.add(task)
    db_session.commit()

    del_res = client.delete(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 204

    # Verify task no longer exists
    get_res = client.get(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 404


def test_delete_task_as_team_member_forbidden(client, db_session):
    """TK-18: Team member cannot delete task (403)."""
    org = create_org(db_session)
    dev, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=dev.id, project_role=ProjectMemberRole.member)
    task = Task(project_id=prj.id, title="Work", assignee_id=dev.id)
    db_session.add_all([m, task])
    db_session.commit()

    res = client.delete(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_task_tenant_isolation(client, db_session):
    """TK-19: User in Org A cannot view, update, or delete task in Org B (404)."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    pm_a, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])

    prj_b = Project(organization_id=org_b.id, name="Org B Prj")
    db_session.add(prj_b)
    db_session.flush()
    task_b = Task(project_id=prj_b.id, title="Org B Task")
    db_session.add(task_b)
    db_session.commit()

    # GET list on cross-org project
    assert client.get(f"/api/v1/projects/{prj_b.id}/tasks", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # GET single task
    assert client.get(f"/api/v1/tasks/{task_b.id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # PATCH task
    assert client.patch(f"/api/v1/tasks/{task_b.id}", headers={"Authorization": f"Bearer {token_a}"}, json={"title": "Hacked"}).status_code == 404

    # DELETE task
    assert client.delete(f"/api/v1/tasks/{task_b.id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404


def test_task_unauthenticated_returns_401(client, db_session):
    """TK-20: Missing token returns 401."""
    org = create_org(db_session)
    prj = Project(organization_id=org.id, name="Prj")
    db_session.add(prj)
    db_session.flush()
    task = Task(project_id=prj.id, title="Work")
    db_session.add(task)
    db_session.commit()

    assert client.get(f"/api/v1/projects/{prj.id}/tasks").status_code == 401
    assert client.post(f"/api/v1/projects/{prj.id}/tasks", json={"title": "X"}).status_code == 401
    assert client.get(f"/api/v1/tasks/{task.id}").status_code == 401
    assert client.patch(f"/api/v1/tasks/{task.id}", json={"status": "done"}).status_code == 401
    assert client.delete(f"/api/v1/tasks/{task.id}").status_code == 401


def test_get_task_direct_as_unassigned_member_forbidden(client, db_session):
    """TK-21: Unassigned same-org team member receives 403 on GET /api/v1/tasks/{task_id}."""
    org = create_org(db_session)
    unassigned_member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()

    task = Task(project_id=prj.id, title="Restricted Task", description="Sensitive Scope", status=TaskStatus.todo)
    db_session.add(task)
    db_session.commit()

    res = client.get(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "Forbidden: You are not a member of this project."

    # Verify no database state was mutated
    db_session.refresh(task)
    assert task.title == "Restricted Task"
    assert task.status == TaskStatus.todo

