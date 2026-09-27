"""Automated tests for Phase 3 Authentication & Organization endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from tests.conftest_db import db_engine, db_session  # noqa: F401


@pytest.fixture
def client(db_session):  # noqa: F811
    """FastAPI TestClient with overridden get_db dependency pointing to the test DB."""
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_register_creates_org_and_user_happy_path(client):
    """Assert successful registration creates org, user, assigns org_admin, and sets tokens."""
    email = f"admin_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "password": "SecurePassword123!",
        "name": "Jane Admin",
        "organization_name": "Acme Innovations",
    }
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201

    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "refresh_token" in resp.cookies

    # Verify user profile via /me using the returned access token
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == email.lower()
    assert me_data["name"] == "Jane Admin"
    assert "org_admin" in me_data["roles"]


def test_register_rejects_duplicate_email(client):
    """Assert attempting to register with an existing email returns 409 Conflict."""
    email = f"duplicate_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "password": "Password123!",
        "name": "First User",
        "organization_name": "Org One",
    }
    first_resp = client.post("/api/v1/auth/register", json=payload)
    assert first_resp.status_code == 201

    duplicate_payload = {
        "email": email,
        "password": "AnotherPassword456!",
        "name": "Second User",
        "organization_name": "Org Two",
    }
    second_resp = client.post("/api/v1/auth/register", json=duplicate_payload)
    assert second_resp.status_code == 409
    assert "already registered" in second_resp.json()["detail"].lower()


def test_login_happy_path_returns_access_token_and_sets_cookie(client):
    """Assert valid credentials return access token and set refresh token cookie."""
    email = f"login_user_{uuid.uuid4().hex[:8]}@example.com"
    password = "CorrectPassword123!"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Login User",
            "organization_name": "Login Org",
        },
    )
    assert reg_resp.status_code == 201

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert "access_token" in login_data
    assert login_data["token_type"] == "bearer"
    assert "refresh_token" in login_resp.cookies


def test_login_rejects_wrong_password(client):
    """Assert login with incorrect password returns 401 Unauthorized."""
    email = f"wrong_pwd_{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "CorrectPassword123!",
            "name": "User",
            "organization_name": "Org",
        },
    )

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword999!"},
    )
    assert resp.status_code == 401
    assert "access_token" not in resp.json()
    assert resp.json()["detail"] == "Invalid email or password."


def test_login_rejects_nonexistent_email(client):
    """Assert login with unknown email returns 401 with identical generic message."""
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": f"nonexistent_{uuid.uuid4().hex[:8]}@example.com",
            "password": "SomePassword123!",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password."


def test_refresh_with_valid_cookie_returns_new_access_token(client):
    """Assert refresh with valid cookie and CSRF header issues new access token and rotates cookie."""
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"refresh_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "name": "Refresh User",
            "organization_name": "Refresh Org",
        },
    )
    assert reg_resp.status_code == 201
    initial_refresh_cookie = reg_resp.cookies["refresh_token"]

    refresh_resp = client.post(
        "/api/v1/auth/refresh",
        headers={"X-Requested-With": "RicozPortfolio"},
        cookies={"refresh_token": initial_refresh_cookie},
    )
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "access_token" in data
    assert "refresh_token" in refresh_resp.cookies
    # New rotated cookie is returned
    assert refresh_resp.cookies["refresh_token"] != ""


def test_refresh_rejects_missing_cookie(client):
    """Assert calling refresh without the cookie returns 401."""
    resp = client.post(
        "/api/v1/auth/refresh",
        headers={"X-Requested-With": "RicozPortfolio"},
    )
    assert resp.status_code == 401
    assert "cookie missing" in resp.json()["detail"].lower()


def test_refresh_rejects_expired_or_invalid_cookie(client):
    """Assert invalid or expired refresh tokens return 401."""
    # 1. Tampered / invalid token
    invalid_resp = client.post(
        "/api/v1/auth/refresh",
        headers={"X-Requested-With": "RicozPortfolio"},
        cookies={"refresh_token": "tampered.jwt.value"},
    )
    assert invalid_resp.status_code == 401

    # 2. Expired refresh token
    expired_token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "org_id": str(uuid.uuid4()),
            "type": "refresh",
            "exp": datetime.now(timezone.utc) - timedelta(hours=2),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    expired_resp = client.post(
        "/api/v1/auth/refresh",
        headers={"X-Requested-With": "RicozPortfolio"},
        cookies={"refresh_token": expired_token},
    )
    assert expired_resp.status_code == 401


def test_refresh_rejects_missing_custom_header(client):
    """Assert missing or mismatched X-Requested-With header returns 400 Bad Request."""
    resp = client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": "dummy_value"},
    )
    assert resp.status_code == 400
    assert "X-Requested-With" in resp.json()["detail"]


def test_logout_clears_cookie(client):
    """Assert logout sets Set-Cookie with Max-Age=0 to clear the refresh token cookie."""
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Successfully logged out."

    set_cookie = resp.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "max-age=0" in set_cookie.lower() or "expires=thu, 01 jan 1970" in set_cookie.lower()
    assert "path=/api/v1/auth" in set_cookie.lower()
    assert "httponly" in set_cookie.lower()


def test_me_requires_valid_access_token(client):
    """Assert unauthenticated requests or invalid tokens to /me return 401."""
    # 1. Missing Authorization header
    resp_no_auth = client.get("/api/v1/auth/me")
    assert resp_no_auth.status_code == 401

    # 2. Malformed / invalid Bearer token
    resp_invalid = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.payload"},
    )
    assert resp_invalid.status_code == 401


def test_me_returns_correct_user_and_org_data(client):
    """Assert /me returns expected user id, email, name, organization_id, and roles."""
    email = f"me_test_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "name": "Alice Bob",
            "organization_name": "Alice Org",
        },
    )
    assert reg_resp.status_code == 201
    access_token = reg_resp.json()["access_token"]

    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == email.lower()
    assert data["name"] == "Alice Bob"
    assert "organization_id" in data
    assert "roles" in data
    assert "org_admin" in data["roles"]


def test_cookie_flags_are_correct_in_non_local_environment(client, monkeypatch):
    """Assert in non-local environments the cookie has HttpOnly, Secure, SameSite=none, Path=/api/v1/auth."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "none")

    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"prod_cookie_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "name": "Prod User",
            "organization_name": "Prod Org",
        },
    )
    assert resp.status_code == 201

    set_cookie = resp.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "secure" in set_cookie.lower()
    assert "samesite=none" in set_cookie.lower()
    assert "path=/api/v1/auth" in set_cookie.lower()
