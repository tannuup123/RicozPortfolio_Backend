"""Automated tests for Project API endpoints (Phase 7: PR-01 to PR-29)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.portfolio import Portfolio
from app.models.project import Project, ProjectStatus
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


def test_create_project_direct_as_pm_succeeds(client, db_session):
    """PR-01: PM creates direct project; initial status is planned (201)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    payload = {"name": "Direct Alpha Project", "description": "Planned directly"}
    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Direct Alpha Project"
    assert data["status"] == "planned"
    assert data["organization_id"] == str(org.id)
    assert data["portfolio_id"] is None


def test_create_project_direct_as_admin_succeeds(client, db_session):
    """PR-02: Admin creates direct project (201)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    payload = {"name": "Admin Direct Project"}
    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "planned"


def test_create_project_direct_as_team_member_forbidden(client, db_session):
    """PR-03: team_member gets 403."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])

    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Member Project"},
    )
    assert response.status_code == 403


def test_create_project_direct_as_pjm_forbidden(client, db_session):
    """PR-04: Org project_manager without PM role gets 403."""
    org = create_org(db_session)
    pjm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "PJM Direct Project"},
    )
    assert response.status_code == 403


def test_create_project_with_invalid_portfolio_returns_404(client, db_session):
    """PR-05: Cross-org or non-existent portfolio returns 404."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    pm_a, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])

    port_b = Portfolio(organization_id=org_b.id, name="Org B Portfolio")
    db_session.add(port_b)
    db_session.commit()

    # Non-existent portfolio
    res1 = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Test Prj", "portfolio_id": str(uuid.uuid4())},
    )
    assert res1.status_code == 404

    # Cross-org portfolio
    res2 = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Test Prj", "portfolio_id": str(port_b.id)},
    )
    assert res2.status_code == 404


def test_create_project_with_soft_deleted_portfolio_returns_404(client, db_session):
    """PR-06: Soft-deleted portfolio cannot be targeted (404)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    port = Portfolio(
        organization_id=org.id,
        name="Deleted Port",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(port)
    db_session.commit()

    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Target Deleted", "portfolio_id": str(port.id)},
    )
    assert response.status_code == 404


def test_create_project_atomic_transaction_creator_membership(client, db_session):
    """PR-07: Creator automatically has ProjectMember role=manager."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Atomic Project"},
    )
    assert response.status_code == 201
    prj_id = uuid.UUID(response.json()["id"])

    # Verify membership exists directly in DB
    membership = (
        db_session.query(ProjectMember)
        .filter(
            ProjectMember.project_id == prj_id,
            ProjectMember.user_id == pm.id,
        )
        .first()
    )
    assert membership is not None
    assert membership.project_role == ProjectMemberRole.manager


def test_create_project_rollback_on_failure(client, db_session):
    """PR-08: Atomicity: failure during member insert rolls back project."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    with patch(
        "app.services.project_service.project_member_repository.create_member",
        side_effect=RuntimeError("Simulated DB Failure"),
    ):
        with pytest.raises(RuntimeError):
            client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "Should Rollback"},
            )

    # Verify no orphaned project was committed
    prj = db_session.query(Project).filter(Project.name == "Should Rollback").first()
    assert prj is None


def test_list_projects_as_pm_sees_all_org_projects(client, db_session):
    """PR-09: PM lists all projects in org."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    p1 = Project(organization_id=org.id, name="Prj 1", status=ProjectStatus.planned)
    p2 = Project(organization_id=org.id, name="Prj 2", status=ProjectStatus.active)
    db_session.add_all([p1, p2])
    db_session.commit()

    response = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_projects_as_member_sees_only_assigned_projects(client, db_session):
    """PR-10: team_member only sees projects they are a member of."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])

    p1 = Project(organization_id=org.id, name="Assigned Prj", status=ProjectStatus.planned)
    p2 = Project(organization_id=org.id, name="Unassigned Prj", status=ProjectStatus.active)
    db_session.add_all([p1, p2])
    db_session.flush()

    m1 = ProjectMember(project_id=p1.id, user_id=user.id, project_role=ProjectMemberRole.member)
    db_session.add(m1)
    db_session.commit()

    response = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Assigned Prj"


def test_list_projects_as_unassigned_pjm_sees_only_assigned(client, db_session):
    """PR-11: Unassigned PM sees empty list / only assigned projects."""
    org = create_org(db_session)
    pjm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    p1 = Project(organization_id=org.id, name="Prj 1", status=ProjectStatus.planned)
    db_session.add(p1)
    db_session.commit()

    response = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_list_projects_filter_by_portfolio_and_status(client, db_session):
    """PR-12: Query params filter accurately."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    port1 = Portfolio(organization_id=org.id, name="Port 1")
    port2 = Portfolio(organization_id=org.id, name="Port 2")
    db_session.add_all([port1, port2])
    db_session.flush()

    p1 = Project(organization_id=org.id, name="P1", portfolio_id=port1.id, status=ProjectStatus.planned)
    p2 = Project(organization_id=org.id, name="P2", portfolio_id=port1.id, status=ProjectStatus.active)
    p3 = Project(organization_id=org.id, name="P3", portfolio_id=port2.id, status=ProjectStatus.planned)
    db_session.add_all([p1, p2, p3])
    db_session.commit()

    response = client.get(
        f"/api/v1/projects?portfolio_id={port1.id}&status=active",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "P2"


def test_list_projects_filter_by_soft_deleted_portfolio_returns_404(client, db_session):
    """PR-13: Filtering by soft-deleted portfolio returns 404."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    port = Portfolio(
        organization_id=org.id,
        name="Deleted Port",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(port)
    db_session.commit()

    response = client.get(
        f"/api/v1/projects?portfolio_id={port.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_get_project_detail_as_assigned_member(client, db_session):
    """PR-14: Assigned member can GET project details (200)."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Project Details")
    db_session.add(prj)
    db_session.flush()

    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    response = client.get(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Project Details"
    assert len(data["members"]) == 1
    assert data["members"][0]["user_id"] == str(member.id)


def test_get_project_detail_as_unassigned_member_forbidden(client, db_session):
    """PR-15: Unassigned team_member receives 403."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="Unassigned Project")
    db_session.add(prj)
    db_session.commit()

    response = client.get(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_get_project_detail_as_unassigned_pjm_forbidden(client, db_session):
    """PR-16: Unassigned project_manager receives 403."""
    org = create_org(db_session)
    pjm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Unassigned PJM Project")
    db_session.add(prj)
    db_session.commit()

    response = client.get(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_update_project_as_assigned_project_manager(client, db_session):
    """PR-17: Project manager assigned as manager can update status/name (200)."""
    org = create_org(db_session)
    pjm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="Old Name", status=ProjectStatus.planned)
    db_session.add(prj)
    db_session.flush()

    m = ProjectMember(project_id=prj.id, user_id=pjm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    response = client.patch(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "New Name", "status": "active"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["status"] == "active"


def test_update_project_as_assigned_member_role_forbidden(client, db_session):
    """PR-18: User assigned only as member cannot update project (403)."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="P1")
    db_session.add(prj)
    db_session.flush()

    m = ProjectMember(project_id=prj.id, user_id=user.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    response = client.patch(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Forbidden Change"},
    )
    assert response.status_code == 403


def test_update_project_as_unassigned_project_manager_forbidden(client, db_session):
    """PR-19: PM not on project gets 403."""
    org = create_org(db_session)
    pjm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="P1")
    db_session.add(prj)
    db_session.commit()

    response = client.patch(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Forbidden"},
    )
    assert response.status_code == 403


def test_update_project_as_team_member_forbidden(client, db_session):
    """PR-20: team_member without manager role gets 403."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    prj = Project(organization_id=org.id, name="P1")
    db_session.add(prj)
    db_session.flush()

    m = ProjectMember(project_id=prj.id, user_id=member.id, project_role=ProjectMemberRole.member)
    db_session.add(m)
    db_session.commit()

    response = client.patch(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Forbidden"},
    )
    assert response.status_code == 403


def test_update_project_status_transitions_valid(client, db_session):
    """PR-21: Direct transition to all enum statuses (planned -> active -> completed, etc.)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Status Test", status=ProjectStatus.planned)
    db_session.add(prj)
    db_session.commit()

    statuses = ["active", "on_hold", "completed", "cancelled", "planned"]
    for s in statuses:
        res = client.patch(
            f"/api/v1/projects/{prj.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": s},
        )
        assert res.status_code == 200
        assert res.json()["status"] == s


def test_update_project_status_invalid_enum_returns_422(client, db_session):
    """PR-22: Invalid status string returns 422."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    prj = Project(organization_id=org.id, name="Status Test")
    db_session.add(prj)
    db_session.commit()

    res = client.patch(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "in_progress_nonexistent"},
    )
    assert res.status_code == 422


def test_patch_project_portfolio_omitted_preserves_assignment(client, db_session):
    """PR-23: Omitted portfolio_id in PATCH preserves existing portfolio."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    port = Portfolio(organization_id=org.id, name="Assigned Port")
    db_session.add(port)
    db_session.flush()

    prj = Project(organization_id=org.id, name="Prj", portfolio_id=port.id)
    db_session.add(prj)
    db_session.commit()

    res = client.patch(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Renamed Prj"},
    )
    assert res.status_code == 200
    assert res.json()["portfolio_id"] == str(port.id)


def test_patch_project_portfolio_explicit_null_clears_assignment(client, db_session):
    """PR-24: Explicit null clears portfolio_id."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    port = Portfolio(organization_id=org.id, name="Assigned Port")
    db_session.add(port)
    db_session.flush()

    prj = Project(organization_id=org.id, name="Prj", portfolio_id=port.id)
    db_session.add(prj)
    db_session.commit()

    res = client.patch(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"portfolio_id": None},
    )
    assert res.status_code == 200
    assert res.json()["portfolio_id"] is None


def test_patch_project_portfolio_soft_deleted_returns_404(client, db_session):
    """PR-25: Targeting soft-deleted portfolio in PATCH returns 404."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    port = Portfolio(
        organization_id=org.id,
        name="Deleted Port",
        deleted_at=datetime.now(timezone.utc),
    )
    prj = Project(organization_id=org.id, name="Prj")
    db_session.add_all([port, prj])
    db_session.commit()

    res = client.patch(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"portfolio_id": str(port.id)},
    )
    assert res.status_code == 404


def test_patch_project_portfolio_cross_org_returns_404(client, db_session):
    """PR-26: Cross-org portfolio in PATCH returns 404."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    admin_a, token_a = make_user_in_org(db_session, org_a.id, ["org_admin"])

    port_b = Portfolio(organization_id=org_b.id, name="Org B Port")
    prj_a = Project(organization_id=org_a.id, name="Org A Prj")
    db_session.add_all([port_b, prj_a])
    db_session.commit()

    res = client.patch(
        f"/api/v1/projects/{prj_a.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"portfolio_id": str(port_b.id)},
    )
    assert res.status_code == 404


def test_delete_project_as_pm_succeeds(client, db_session):
    """PR-27: PM soft-deletes project; subsequent GET returns 404."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    prj = Project(organization_id=org.id, name="Delete Me")
    db_session.add(prj)
    db_session.commit()

    del_res = client.delete(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 204

    get_res = client.get(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 404


def test_delete_project_as_project_manager_forbidden(client, db_session):
    """PR-28: Project manager cannot delete project (403)."""
    org = create_org(db_session)
    pjm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    prj = Project(organization_id=org.id, name="No Delete")
    db_session.add(prj)
    db_session.flush()

    m = ProjectMember(project_id=prj.id, user_id=pjm.id, project_role=ProjectMemberRole.manager)
    db_session.add(m)
    db_session.commit()

    del_res = client.delete(
        f"/api/v1/projects/{prj.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 403


def test_project_tenant_isolation(client, db_session):
    """PR-29: User in Org A cannot view/edit project in Org B (404)."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    pm_a, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    prj_b = Project(organization_id=org_b.id, name="Org B Project")
    db_session.add(prj_b)
    db_session.commit()

    # GET
    assert client.get(
        f"/api/v1/projects/{prj_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    ).status_code == 404

    # PATCH
    assert client.patch(
        f"/api/v1/projects/{prj_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Hacked"},
    ).status_code == 404

    # DELETE
    assert client.delete(
        f"/api/v1/projects/{prj_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    ).status_code == 404
