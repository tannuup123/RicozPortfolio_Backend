"""Tests for Role-Based Access Control (RBAC) require_role dependency."""

import uuid

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app.core.deps import require_role
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User, UserRole
from tests.conftest_db import db_engine, db_session  # noqa: F401

# Test-only router with routes guarded by different roles
rbac_test_router = APIRouter(prefix="/test-rbac")


@rbac_test_router.get("/pm")
def pm_endpoint(user: User = Depends(require_role("portfolio_manager"))):
    return {"message": "ok", "user": user.email}


@rbac_test_router.get("/pjm")
def pjm_endpoint(user: User = Depends(require_role("project_manager"))):
    return {"message": "ok", "user": user.email}


@rbac_test_router.get("/team")
def team_endpoint(user: User = Depends(require_role("team_member"))):
    return {"message": "ok", "user": user.email}


@pytest.fixture(scope="module")
def rbac_app():
    """App instance including the test-only RBAC routes for the duration of this module."""
    app.include_router(rbac_test_router)
    yield app


@pytest.fixture
def client(rbac_app, db_session):  # noqa: F811
    """FastAPI TestClient with overridden get_db pointing to test DB."""
    def _override_get_db():
        yield db_session

    rbac_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(rbac_app) as test_client:
        yield test_client
    rbac_app.dependency_overrides.clear()


def create_user_with_roles(db_session, role_names: list[str]) -> tuple[User, str]:
    """Helper to create an organization, user with specific roles, and return (user, access_token)."""
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()

    user = User(
        email=f"user_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("Password123!"),
        name="Test User",
        organization_id=org.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    roles = db_session.query(Role).filter(Role.name.in_(role_names)).all()
    for role in roles:
        db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token(user_id=user.id, organization_id=org.id)
    return user, token


@pytest.mark.parametrize(
    ("user_role", "endpoint", "expected_status"),
    [
        # org_admin passes everywhere
        ("org_admin", "/test-rbac/pm", 200),
        ("org_admin", "/test-rbac/pjm", 200),
        ("org_admin", "/test-rbac/team", 200),
        # portfolio_manager
        ("portfolio_manager", "/test-rbac/pm", 200),
        ("portfolio_manager", "/test-rbac/pjm", 403),
        ("portfolio_manager", "/test-rbac/team", 403),
        # project_manager
        ("project_manager", "/test-rbac/pm", 403),
        ("project_manager", "/test-rbac/pjm", 200),
        ("project_manager", "/test-rbac/team", 403),
        # team_member
        ("team_member", "/test-rbac/pm", 403),
        ("team_member", "/test-rbac/pjm", 403),
        ("team_member", "/test-rbac/team", 200),
    ],
)
def test_rbac_role_matrix(client, db_session, user_role, endpoint, expected_status):
    """Verify full matrix of 4 roles x guarded endpoints."""
    _, token = create_user_with_roles(db_session, [user_role])
    resp = client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == expected_status
    if expected_status == 403:
        assert resp.json()["detail"] == "Forbidden: Insufficient permissions"


def test_rbac_unauthenticated_returns_401(client):
    """Verify request with no auth token returns 401."""
    resp = client.get("/test-rbac/pm")
    assert resp.status_code == 401


def test_rbac_user_with_multiple_roles(client, db_session):
    """Verify user with both portfolio_manager and project_manager can access both endpoints."""
    _, token = create_user_with_roles(db_session, ["portfolio_manager", "project_manager"])

    resp_pm = client.get("/test-rbac/pm", headers={"Authorization": f"Bearer {token}"})
    assert resp_pm.status_code == 200

    resp_pjm = client.get("/test-rbac/pjm", headers={"Authorization": f"Bearer {token}"})
    assert resp_pjm.status_code == 200

    # But not team_member endpoint
    resp_team = client.get("/test-rbac/team", headers={"Authorization": f"Bearer {token}"})
    assert resp_team.status_code == 403


def test_rbac_user_with_no_roles_returns_403(client, db_session):
    """Verify user with no roles assigned receives 403."""
    _, token = create_user_with_roles(db_session, [])
    resp = client.get("/test-rbac/pm", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
