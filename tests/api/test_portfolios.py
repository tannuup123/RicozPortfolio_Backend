"""Automated tests for Portfolio API endpoints (Phase 7: PF-01 to PF-15)."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.portfolio import Portfolio
from app.models.project import Project, ProjectStatus
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


def test_create_portfolio_as_pm_succeeds(client, db_session):
    """PF-01: PM can create portfolio (201)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    payload = {"name": "Core Platform Portfolio", "description": "High level initiatives"}
    response = client.post(
        "/api/v1/portfolios",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Core Platform Portfolio"
    assert data["description"] == "High level initiatives"
    assert data["organization_id"] == str(org.id)
    assert "id" in data


def test_create_portfolio_as_admin_succeeds(client, db_session):
    """PF-02: Org Admin can create portfolio (201)."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])

    payload = {"name": "Admin Portfolio"}
    response = client.post(
        "/api/v1/portfolios",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Admin Portfolio"


def test_create_portfolio_as_team_member_forbidden(client, db_session):
    """PF-03: team_member gets 403."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])

    response = client.post(
        "/api/v1/portfolios",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Member Portfolio"},
    )
    assert response.status_code == 403


def test_create_portfolio_as_project_manager_forbidden(client, db_session):
    """PF-04: project_manager gets 403."""
    org = create_org(db_session)
    pjm, token = make_user_in_org(db_session, org.id, ["project_manager"])

    response = client.post(
        "/api/v1/portfolios",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "PJM Portfolio"},
    )
    assert response.status_code == 403


def test_list_portfolios_any_role_succeeds(client, db_session):
    """PF-05: Any authenticated user in org can list portfolios (200)."""
    org = create_org(db_session)
    pm, _ = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    # Create 2 portfolios in org
    p1 = Portfolio(organization_id=org.id, name="Portfolio Alpha")
    p2 = Portfolio(organization_id=org.id, name="Portfolio Beta")
    db_session.add_all([p1, p2])
    db_session.commit()

    response = client.get(
        "/api/v1/portfolios",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_portfolios_pagination(client, db_session):
    """PF-06: limit and offset work correctly."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])

    for i in range(5):
        p = Portfolio(organization_id=org.id, name=f"Portfolio {i}")
        db_session.add(p)
    db_session.commit()

    response = client.get(
        "/api/v1/portfolios?limit=2&offset=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2


def test_get_portfolio_with_project_count(client, db_session):
    """PF-07: Returns 200 with accurate active project count."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])

    portfolio = Portfolio(organization_id=org.id, name="Count Portfolio")
    db_session.add(portfolio)
    db_session.flush()

    # Add 2 active projects and 1 soft-deleted project
    prj1 = Project(organization_id=org.id, name="Prj 1", portfolio_id=portfolio.id, status=ProjectStatus.planned)
    prj2 = Project(organization_id=org.id, name="Prj 2", portfolio_id=portfolio.id, status=ProjectStatus.active)
    prj3 = Project(
        organization_id=org.id,
        name="Prj 3",
        portfolio_id=portfolio.id,
        status=ProjectStatus.planned,
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add_all([prj1, prj2, prj3])
    db_session.commit()

    response = client.get(
        f"/api/v1/portfolios/{portfolio.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(portfolio.id)
    assert data["project_count"] == 2


def test_get_portfolio_not_found_returns_404(client, db_session):
    """PF-08: Non-existent ID returns 404."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])

    response = client.get(
        f"/api/v1/portfolios/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_update_portfolio_as_pm_succeeds(client, db_session):
    """PF-09: PM can update name and description (200)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    portfolio = Portfolio(organization_id=org.id, name="Original Name", description="Original Desc")
    db_session.add(portfolio)
    db_session.commit()

    response = client.patch(
        f"/api/v1/portfolios/{portfolio.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Updated Name", "description": "Updated Desc"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Updated Desc"

    # Test clearing description with explicit null
    clear_resp = client.patch(
        f"/api/v1/portfolios/{portfolio.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": None},
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["name"] == "Updated Name"
    assert clear_resp.json()["description"] is None


def test_update_portfolio_as_member_forbidden(client, db_session):
    """PF-10: Non-PM gets 403."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"])

    portfolio = Portfolio(organization_id=org.id, name="Portfolio X")
    db_session.add(portfolio)
    db_session.commit()

    response = client.patch(
        f"/api/v1/portfolios/{portfolio.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Hacked Name"},
    )
    assert response.status_code == 403


def test_delete_portfolio_soft_deletes(client, db_session):
    """PF-11: Portfolio marked with deleted_at; subsequent GET returns 404; associated projects retain portfolio_id."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    portfolio = Portfolio(organization_id=org.id, name="To Delete")
    db_session.add(portfolio)
    db_session.flush()

    project = Project(organization_id=org.id, name="Assigned Project", portfolio_id=portfolio.id)
    db_session.add(project)
    db_session.commit()

    response = client.delete(
        f"/api/v1/portfolios/{portfolio.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    # Subsequent GET returns 404
    get_resp = client.get(
        f"/api/v1/portfolios/{portfolio.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404

    # Project still exists and retains portfolio_id
    db_session.refresh(project)
    assert project.deleted_at is None
    assert project.portfolio_id == portfolio.id


def test_portfolio_tenant_isolation(client, db_session):
    """PF-12: User in Org A cannot GET/PATCH/DELETE portfolio in Org B (404)."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    pm_a, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"])
    pm_b, token_b = make_user_in_org(db_session, org_b.id, ["portfolio_manager"])

    portfolio_b = Portfolio(organization_id=org_b.id, name="Org B Portfolio")
    db_session.add(portfolio_b)
    db_session.commit()

    # User in Org A attempts GET
    get_resp = client.get(
        f"/api/v1/portfolios/{portfolio_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_resp.status_code == 404

    # User in Org A attempts PATCH
    patch_resp = client.patch(
        f"/api/v1/portfolios/{portfolio_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Org A Overwrite"},
    )
    assert patch_resp.status_code == 404

    # User in Org A attempts DELETE
    del_resp = client.delete(
        f"/api/v1/portfolios/{portfolio_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert del_resp.status_code == 404


def test_portfolio_unauthenticated_returns_401(client, db_session):
    """PF-13: Missing token returns 401."""
    org = create_org(db_session)
    portfolio = Portfolio(organization_id=org.id, name="Test Port")
    db_session.add(portfolio)
    db_session.commit()

    assert client.get("/api/v1/portfolios").status_code == 401
    assert client.get(f"/api/v1/portfolios/{portfolio.id}").status_code == 401
    assert client.post("/api/v1/portfolios", json={"name": "X"}).status_code == 401
    assert client.patch(f"/api/v1/portfolios/{portfolio.id}", json={"name": "Y"}).status_code == 401
    assert client.delete(f"/api/v1/portfolios/{portfolio.id}").status_code == 401


def test_create_portfolio_validation_errors(client, db_session):
    """PF-14: Empty name returns 422."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    response = client.post(
        "/api/v1/portfolios",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": ""},
    )
    assert response.status_code == 422


def test_update_portfolio_name_explicit_null_returns_422(client, db_session):
    """PF-15: PATCH with {"name": null} explicitly provided returns 422; omitting name preserves existing value."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    portfolio = Portfolio(organization_id=org.id, name="Keep This Name", description="Desc")
    db_session.add(portfolio)
    db_session.commit()

    # Explicit null returns 422
    response = client.patch(
        f"/api/v1/portfolios/{portfolio.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": None},
    )
    assert response.status_code == 422

    # Omitting name preserves existing name
    ok_resp = client.patch(
        f"/api/v1/portfolios/{portfolio.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": "Updated Description Only"},
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["name"] == "Keep This Name"
    assert ok_resp.json()["description"] == "Updated Description Only"
