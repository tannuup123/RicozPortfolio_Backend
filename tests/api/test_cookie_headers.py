"""API integration tests for actual raw Set-Cookie response headers in non-local environments (Phase 11)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import hash_password
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


def create_org(db_session) -> Organization:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


def make_user_in_org(db_session, org_id: uuid.UUID, role_names: list[str]) -> User:
    user = User(
        email=f"user_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("Password123!"),
        name="Cookie User",
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
    return user


def test_login_and_logout_headers_under_production_environment(client, db_session, monkeypatch):
    """Verify live Set-Cookie response headers enforce SameSite=none and Secure under production mode."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    org = create_org(db_session)
    user = make_user_in_org(db_session, org.id, ["team_member"])

    # 1. POST /auth/login
    res_login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Password123!"},
    )
    assert res_login.status_code == 200

    set_cookie_login = res_login.headers.get("set-cookie")
    assert set_cookie_login is not None
    assert "refresh_token=" in set_cookie_login
    assert "HttpOnly" in set_cookie_login or "httponly" in set_cookie_login
    assert "Secure" in set_cookie_login or "secure" in set_cookie_login
    assert "samesite=none" in set_cookie_login.lower()
    assert "path=/api/v1/auth" in set_cookie_login.lower()

    # Extract the cookie for refresh testing
    raw_cookie = res_login.cookies.get("refresh_token")
    assert raw_cookie is not None

    # 2. POST /auth/refresh with CSRF header
    res_refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"X-Requested-With": "RicozPortfolio"},
        cookies={"refresh_token": raw_cookie},
    )
    assert res_refresh.status_code == 200
    set_cookie_refresh = res_refresh.headers.get("set-cookie")
    assert set_cookie_refresh is not None
    assert "samesite=none" in set_cookie_refresh.lower()
    assert "secure" in set_cookie_refresh.lower()

    # 3. POST /auth/logout clears cookie with Max-Age=0 and same security attributes
    res_logout = client.post("/api/v1/auth/logout")
    assert res_logout.status_code == 200
    set_cookie_logout = res_logout.headers.get("set-cookie")
    assert set_cookie_logout is not None
    assert "max-age=0" in set_cookie_logout.lower()
    assert "samesite=none" in set_cookie_logout.lower()
    assert "secure" in set_cookie_logout.lower()
