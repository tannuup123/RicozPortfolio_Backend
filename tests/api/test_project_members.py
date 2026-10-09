"""Automated tests for Project Member API endpoints (Phase 7: PM-01 to PM-15)."""

import concurrent.futures
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


def test_add_member_as_portfolio_manager_succeeds(client, db_session):
    """PM-01: PM can add member to project (201)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    target_user, _ = make_user_in_org(db_session, org.id, ["team_member"], name="New Member")

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.commit()

    response = client.post(
        f"/api/v1/projects/{prj.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": str(target_user.id), "project_role": "member"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["project_id"] == str(prj.id)
    assert data["user_id"] == str(target_user.id)
    assert data["user_name"] == "New Member"
    assert data["project_role"] == "member"


def test_add_member_as_project_manager_on_project_succeeds(client, db_session):
    """PM-02: Assigned project manager can add members (201)."""
    org = create_org(db_session)
    pjm, token = make_user_in_org(db_session, org.id, ["project_manager"])
    target_user, _ = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.flush()

    m = ProjectMember(project_id=prj.id, user_id=pjm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    response = client.post(
        f"/api/v1/projects/{prj.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": str(target_user.id), "project_role": "member"},
    )
    assert response.status_code == 201
    assert response.json()["user_id"] == str(target_user.id)


def test_add_member_as_unassigned_pjm_forbidden(client, db_session):
    """PM-03: Unassigned PM gets 403."""
    org = create_org(db_session)
    pjm, token = make_user_in_org(db_session, org.id, ["project_manager"])
    target_user, _ = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.commit()

    response = client.post(
        f"/api/v1/projects/{prj.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": str(target_user.id)},
    )
    assert response.status_code == 403


def test_add_member_as_assigned_member_role_forbidden(client, db_session):
    """PM-04: User assigned as member (not manager) gets 403."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["project_manager"])
    target_user, _ = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.flush()

    m = ProjectMember(project_id=prj.id, user_id=user.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    response = client.post(
        f"/api/v1/projects/{prj.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": str(target_user.id)},
    )
    assert response.status_code == 403


def test_add_member_as_team_member_forbidden(client, db_session):
    """PM-05: team_member gets 403."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])
    target_user, _ = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.commit()

    response = client.post(
        f"/api/v1/projects/{prj.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": str(target_user.id)},
    )
    assert response.status_code == 403


def test_add_duplicate_member_returns_409(client, db_session):
    """PM-06: Adding same user twice returns 409 Conflict."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    target_user, _ = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.flush()

    m = ProjectMember(project_id=prj.id, user_id=target_user.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    response = client.post(
        f"/api/v1/projects/{prj.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": str(target_user.id)},
    )
    assert response.status_code == 409
    assert "User is already a member of this project." in response.json()["detail"]


def test_add_cross_org_user_returns_404(client, db_session):
    """PM-07: User from another organization cannot be added (404)."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    pm_a, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    user_b, _ = make_user_in_org(db_session, org_b.id, ["team_member"])

    prj_a = Project(organization_id=org_a.id, name="Project A")
    db_session.add(prj_a)
    db_session.commit()

    response = client.post(
        f"/api/v1/projects/{prj_a.id}/members",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"user_id": str(user_b.id)},
    )
    assert response.status_code == 404


def test_list_project_members_includes_user_details(client, db_session):
    """PM-08: Returns list with user name, email, project_role (200)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    member, _ = make_user_in_org(db_session, org.id, ["team_member"], name="Member Alice")

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.flush()

    m1 = ProjectMember(project_id=prj.id, user_id=pm.id, project_role=ProjectMemberRole.manager)
    m2 = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add_all([m1, m2])
    db_session.commit()

    response = client.get(
        f"/api/v1/projects/{prj.id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    emails = [m["user_email"] for m in data["items"]]
    assert member.email in emails


def test_update_member_role_succeeds(client, db_session):
    """PM-09: Can promote/demote member role (200)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    member, _ = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.flush()

    m1 = ProjectMember(project_id=prj.id, user_id=admin.id, project_role=ProjectMemberRole.manager)
    m2 = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add_all([m1, m2])
    db_session.commit()

    # Promote member to manager
    response = client.patch(
        f"/api/v1/projects/{prj.id}/members/{member.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"project_role": "manager"},
    )
    assert response.status_code == 200
    assert response.json()["project_role"] == "manager"

    # Demote back to member
    response2 = client.patch(
        f"/api/v1/projects/{prj.id}/members/{member.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"project_role": "member"},
    )
    assert response2.status_code == 200
    assert response2.json()["project_role"] == "member"


def test_cannot_demote_last_project_manager(client, db_session):
    """PM-10: Attempting to demote sole manager returns 400."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    pjm, _ = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.flush()

    m1 = ProjectMember(project_id=prj.id, user_id=pjm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m1)
    db_session.commit()

    response = client.patch(
        f"/api/v1/projects/{prj.id}/members/{pjm.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"project_role": "member"},
    )
    assert response.status_code == 400
    assert "Cannot remove or demote the last project manager" in response.json()["detail"]


def test_remove_member_succeeds(client, db_session):
    """PM-11: Manager can remove member from project (204)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    member, _ = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.flush()

    m1 = ProjectMember(project_id=prj.id, user_id=admin.id, project_role=ProjectMemberRole.manager)
    m2 = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add_all([m1, m2])
    db_session.commit()

    response = client.delete(
        f"/api/v1/projects/{prj.id}/members/{member.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    # Confirm member is deleted
    rem = db_session.query(ProjectMember).filter(ProjectMember.project_id == prj.id, ProjectMember.user_id == member.id).first()
    assert rem is None


def test_cannot_remove_last_project_manager(client, db_session):
    """PM-12: Attempting to remove sole manager returns 400."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.flush()

    m1 = ProjectMember(project_id=prj.id, user_id=admin.id, project_role=ProjectMemberRole.manager)
    db_session.add(m1)
    db_session.commit()

    response = client.delete(
        f"/api/v1/projects/{prj.id}/members/{admin.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "Cannot remove the last project manager" in response.json()["detail"]


def test_member_removal_revokes_project_visibility(client, db_session):
    """PM-13: Removed member no longer sees project in list or GET (403)."""
    org = create_org(db_session)
    admin, token_admin = make_user_in_org(db_session, org.id, ["org_admin"])
    member, token_member = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Secret Project")
    db_session.add(prj)
    db_session.flush()

    m1 = ProjectMember(project_id=prj.id, user_id=admin.id, project_role=ProjectMemberRole.manager)
    m2 = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add_all([m1, m2])
    db_session.commit()

    # Member can see project initially
    assert client.get(f"/api/v1/projects/{prj.id}", headers={"Authorization": f"Bearer {token_member}"}).status_code == 200

    # Admin removes member
    assert client.delete(f"/api/v1/projects/{prj.id}/members/{member.id}", headers={"Authorization": f"Bearer {token_admin}"}).status_code == 204

    # Member cannot see project now
    assert client.get(f"/api/v1/projects/{prj.id}", headers={"Authorization": f"Bearer {token_member}"}).status_code == 403


def test_project_member_does_not_grant_org_level_permissions(client, db_session):
    """PM-14: team_member with project role manager cannot create portfolios or direct projects (403)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Project 1")
    db_session.add(prj)
    db_session.flush()

    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    # Cannot create portfolio
    res1 = client.post("/api/v1/portfolios", headers={"Authorization": f"Bearer {token}"}, json={"name": "Port"})
    assert res1.status_code == 403

    # Cannot create direct project
    res2 = client.post("/api/v1/projects", headers={"Authorization": f"Bearer {token}"}, json={"name": "Prj"})
    assert res2.status_code == 403


def test_concurrent_last_manager_removal_serialized_safety(db_engine):  # noqa: F811
    """PM-15: Concurrency safety: two threads simultaneously attempt to remove the two managers

    of a 2-manager project via the real PostgreSQL test DB; SELECT FOR UPDATE serializes them —
    exactly one removal succeeds (204) and one receives 400.
    """
    from sqlalchemy.orm import sessionmaker

    TestSession = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    setup_db = TestSession()

    try:
        org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
        setup_db.add(org)
        setup_db.commit()

        # Create two managers in org
        pm1, token1 = make_user_in_org(setup_db, org.id, ["org_admin"], name="Manager 1")
        pm2, token2 = make_user_in_org(setup_db, org.id, ["org_admin"], name="Manager 2")

        prj = Project(organization_id=org.id, name="Concurrent Prj")
        setup_db.add(prj)
        setup_db.flush()

        m1 = ProjectMember(project_id=prj.id, user_id=pm1.id, project_role=ProjectMemberRole.manager)
        m2 = ProjectMember(project_id=prj.id, user_id=pm2.id, project_role=ProjectMemberRole.manager)
        setup_db.add_all([m1, m2])
        setup_db.commit()

        prj_id = prj.id
        pm1_id = pm1.id
        pm2_id = pm2.id
    finally:
        setup_db.close()

    def _thread_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _thread_get_db

    def remove_manager(target_user_id: uuid.UUID, caller_token: str) -> int:
        with TestClient(app) as test_client:
            res = test_client.delete(
                f"/api/v1/projects/{prj_id}/members/{target_user_id}",
                headers={"Authorization": f"Bearer {caller_token}"},
            )
            return res.status_code

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(remove_manager, pm1_id, token1)
            f2 = executor.submit(remove_manager, pm2_id, token2)
            results = [f1.result(), f2.result()]
    finally:
        app.dependency_overrides.clear()

    assert sorted(results) == [204, 400]
