"""Automated tests for Milestone API endpoints (Phase 8: ML-01 to ML-15)."""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.milestone import Milestone, MilestoneStatus
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


def test_create_milestone_as_pm_succeeds(client, db_session):
    """ML-01: Assigned PM creates milestone in project (201)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    payload = {
        "title": "Beta Release",
        "description": "Internal test flight",
        "due_date": "2026-11-01",
        "status": "pending",
    }
    res = client.post(
        f"/api/v1/projects/{prj.id}/milestones",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Beta Release"
    assert data["description"] == "Internal test flight"
    assert data["due_date"] == "2026-11-01"
    assert data["status"] == "pending"
    assert data["project_id"] == str(prj.id)


def test_create_milestone_as_admin_succeeds(client, db_session):
    """ML-02: Org Admin creates milestone without explicit project membership (201)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj Admin")
    db_session.add(prj)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/milestones",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "V1 Launch"},
    )
    assert res.status_code == 201
    assert res.json()["title"] == "V1 Launch"


def test_create_milestone_as_team_member_forbidden(client, db_session):
    """ML-03: Team member cannot create milestone (403)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    res = client.post(
        f"/api/v1/projects/{prj.id}/milestones",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Member Milestone Attempt"},
    )
    assert res.status_code == 403


def test_list_milestones_as_assigned_member(client, db_session):
    """ML-04: Assigned project member can list milestones (200)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    ml1 = Milestone(project_id=prj.id, title="M1", due_date=date(2026, 10, 15), status=MilestoneStatus.pending)
    ml2 = Milestone(project_id=prj.id, title="M2", due_date=date(2026, 12, 1), status=MilestoneStatus.achieved)
    db_session.add_all([m, ml1, ml2])
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/milestones",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_milestones_as_unassigned_member_forbidden(client, db_session):
    """ML-05: Unassigned team member receives 403."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/milestones",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_list_milestones_filter_by_status(client, db_session):
    """ML-06: Filter milestones by status query param."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    ml1 = Milestone(project_id=prj.id, title="M1", status=MilestoneStatus.pending)
    ml2 = Milestone(project_id=prj.id, title="M2", status=MilestoneStatus.achieved)
    ml3 = Milestone(project_id=prj.id, title="M3", status=MilestoneStatus.missed)
    db_session.add_all([ml1, ml2, ml3])
    db_session.commit()

    res = client.get(
        f"/api/v1/projects/{prj.id}/milestones?status=achieved",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "M2"


def test_get_milestone_by_id(client, db_session):
    """ML-07: Retrieve single milestone by ID (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    ml = Milestone(project_id=prj.id, title="Architecture Review", due_date=date(2026, 10, 20))
    db_session.add(ml)
    db_session.commit()

    res = client.get(
        f"/api/v1/milestones/{ml.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "Architecture Review"
    assert res.json()["due_date"] == "2026-10-20"


def test_get_milestone_not_found(client, db_session):
    """ML-08: Non-existent milestone returns 404."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    res = client.get(
        f"/api/v1/milestones/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


def test_update_milestone_as_pm_succeeds(client, db_session):
    """ML-09: PM updates milestone attributes (200)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    ml = Milestone(project_id=prj.id, title="Old Title", status=MilestoneStatus.pending)
    db_session.add(ml)
    db_session.commit()

    res = client.patch(
        f"/api/v1/milestones/{ml.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Updated Title", "status": "achieved", "due_date": "2026-11-15"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Updated Title"
    assert data["status"] == "achieved"
    assert data["due_date"] == "2026-11-15"


def test_update_milestone_as_team_member_forbidden(client, db_session):
    """ML-10: Team member cannot update milestone (403)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    ml = Milestone(project_id=prj.id, title="Release")
    db_session.add_all([m, ml])
    db_session.commit()

    res = client.patch(
        f"/api/v1/milestones/{ml.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "achieved"},
    )
    assert res.status_code == 403


def test_patch_milestone_explicit_null_fields(client, db_session):
    """ML-11: PM can clear description and due_date using explicit null; title: null returns 422."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    ml = Milestone(project_id=prj.id, title="Keep Title", description="Desc", due_date=date(2026, 12, 1))
    db_session.add(ml)
    db_session.commit()

    # Clear description and due_date
    res1 = client.patch(
        f"/api/v1/milestones/{ml.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": None, "due_date": None},
    )
    assert res1.status_code == 200
    assert res1.json()["description"] is None
    assert res1.json()["due_date"] is None
    assert res1.json()["title"] == "Keep Title"

    # Reject null title
    res2 = client.patch(
        f"/api/v1/milestones/{ml.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": None},
    )
    assert res2.status_code == 422


def test_delete_milestone_as_pm_succeeds(client, db_session):
    """ML-12: PM can delete milestone (204)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    ml = Milestone(project_id=prj.id, title="To Delete")
    db_session.add(ml)
    db_session.commit()

    del_res = client.delete(
        f"/api/v1/milestones/{ml.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 204

    assert client.get(f"/api/v1/milestones/{ml.id}", headers={"Authorization": f"Bearer {token}"}).status_code == 404


def test_delete_milestone_as_team_member_forbidden(client, db_session):
    """ML-13: Team member cannot delete milestone (403)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()
    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    ml = Milestone(project_id=prj.id, title="Milestone")
    db_session.add_all([m, ml])
    db_session.commit()

    res = client.delete(
        f"/api/v1/milestones/{ml.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_milestone_tenant_isolation(client, db_session):
    """ML-14: User in Org A cannot access or modify milestone in Org B (404)."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    pm_a, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])

    prj_b = Project(organization_id=org_b.id, name="Org B Prj")
    db_session.add(prj_b)
    db_session.flush()
    ml_b = Milestone(project_id=prj_b.id, title="Org B Milestone")
    db_session.add(ml_b)
    db_session.commit()

    # GET list on cross-org project
    assert client.get(f"/api/v1/projects/{prj_b.id}/milestones", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # GET single milestone
    assert client.get(f"/api/v1/milestones/{ml_b.id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # PATCH milestone
    assert client.patch(f"/api/v1/milestones/{ml_b.id}", headers={"Authorization": f"Bearer {token_a}"}, json={"title": "Hacked"}).status_code == 404

    # DELETE milestone
    assert client.delete(f"/api/v1/milestones/{ml_b.id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404


def test_milestone_unauthenticated_returns_401(client, db_session):
    """ML-15: Missing token returns 401."""
    org = create_org(db_session)
    prj = Project(organization_id=org.id, name="Prj")
    db_session.add(prj)
    db_session.flush()
    ml = Milestone(project_id=prj.id, title="M1")
    db_session.add(ml)
    db_session.commit()

    assert client.get(f"/api/v1/projects/{prj.id}/milestones").status_code == 401
    assert client.post(f"/api/v1/projects/{prj.id}/milestones", json={"title": "M2"}).status_code == 401
    assert client.get(f"/api/v1/milestones/{ml.id}").status_code == 401
    assert client.patch(f"/api/v1/milestones/{ml.id}", json={"title": "M3"}).status_code == 401
    assert client.delete(f"/api/v1/milestones/{ml.id}").status_code == 401


def test_get_milestone_direct_as_unassigned_member_forbidden(client, db_session):
    """ML-16: Unassigned same-org team member receives 403 on GET /api/v1/milestones/{milestone_id}."""
    org = create_org(db_session)
    unassigned_member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Prj 1")
    db_session.add(prj)
    db_session.flush()

    ml = Milestone(project_id=prj.id, title="Internal Milestone", status=MilestoneStatus.pending)
    db_session.add(ml)
    db_session.commit()

    res = client.get(
        f"/api/v1/milestones/{ml.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "Forbidden: You are not a member of this project."

    # Verify no database state was mutated
    db_session.refresh(ml)
    assert ml.title == "Internal Milestone"
    assert ml.status == MilestoneStatus.pending

