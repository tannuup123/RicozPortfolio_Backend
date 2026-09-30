"""Automated tests for Phase 4 User Management endpoints."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
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


def make_user_in_org(
    db_session,
    org_id: uuid.UUID,
    role_names: list[str],
    is_active: bool = True,
    name: str = "Test User",
) -> tuple[User, str]:
    """Factory helper to create a user with specific roles in an organization and return (user, access_token)."""
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


def create_org(db_session) -> Organization:
    """Helper to create a new Organization."""
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


# ---------------------------------------------------------------------------
# 1. GET /api/v1/users
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role_name",
    ["org_admin", "portfolio_manager", "project_manager", "team_member"],
)
def test_get_users_all_roles_can_view_own_org(client, db_session, role_name):
    """All 4 roles receive 200 on GET /users and only view users from their own organization."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    caller, token = make_user_in_org(db_session, org_a.id, [role_name])
    # Add another user in org_a
    make_user_in_org(db_session, org_a.id, ["team_member"])
    # Add a user in org_b (should not leak)
    make_user_in_org(db_session, org_b.id, ["org_admin"])

    resp = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] == 2
    for item in data["items"]:
        assert item["organization_id"] == str(org_a.id)


def test_get_users_pagination(client, db_session):
    """Verify limit and offset query parameters work as expected."""
    org = create_org(db_session)
    _, admin_token = make_user_in_org(db_session, org.id, ["org_admin"])

    # Create 4 more users (total 5)
    for i in range(4):
        make_user_in_org(db_session, org.id, ["team_member"], name=f"Member {i}")

    resp_page1 = client.get(
        "/api/v1/users?limit=2&offset=0",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_page1.status_code == 200
    data_page1 = resp_page1.json()
    assert len(data_page1["items"]) == 2
    assert data_page1["total"] == 5

    resp_page2 = client.get(
        "/api/v1/users?limit=2&offset=2",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_page2.status_code == 200
    data_page2 = resp_page2.json()
    assert len(data_page2["items"]) == 2
    assert data_page2["total"] == 5

    # Ensure items in page 1 and page 2 are different
    ids_p1 = {item["id"] for item in data_page1["items"]}
    ids_p2 = {item["id"] for item in data_page2["items"]}
    assert ids_p1.isdisjoint(ids_p2)


# ---------------------------------------------------------------------------
# 2. POST /api/v1/users
# ---------------------------------------------------------------------------


def test_create_user_org_admin_success(client, db_session):
    """org_admin can create a user within their org, and the new user can log in."""
    org = create_org(db_session)
    _, admin_token = make_user_in_org(db_session, org.id, ["org_admin"])

    email = f"newuser_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "password": "Password123!",
        "name": "New Team Member",
        "roles": ["portfolio_manager"],
    }
    resp = client.post(
        "/api/v1/users",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == email.lower()
    assert data["name"] == "New Team Member"
    assert data["organization_id"] == str(org.id)
    assert "portfolio_manager" in data["roles"]

    # Verify newly created user can log in with initial password
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


@pytest.mark.parametrize(
    "role_name",
    ["portfolio_manager", "project_manager", "team_member"],
)
def test_create_user_non_admin_forbidden(client, db_session, role_name):
    """Non-org_admin roles receive 403 on POST /users."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, [role_name])

    payload = {
        "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Password123!",
        "name": "Member",
        "roles": ["team_member"],
    }
    resp = client.post(
        "/api/v1/users",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_create_user_duplicate_email_conflict(client, db_session):
    """Attempting to create a user with an already registered email returns 409 Conflict."""
    org = create_org(db_session)
    existing_user, admin_token = make_user_in_org(db_session, org.id, ["org_admin"])

    payload = {
        "email": existing_user.email,
        "password": "Password123!",
        "name": "Duplicate User",
        "roles": ["team_member"],
    }
    resp = client.post(
        "/api/v1/users",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 3. PATCH /api/v1/users/{user_id}/roles
# ---------------------------------------------------------------------------


def test_patch_user_roles_org_admin_success(client, db_session):
    """org_admin can replace roles, and the change takes effect immediately on user's next request."""
    org = create_org(db_session)
    _, admin_token = make_user_in_org(db_session, org.id, ["org_admin"])
    target_user, target_token = make_user_in_org(db_session, org.id, ["team_member"])

    # Update role to portfolio_manager
    patch_resp = client.patch(
        f"/api/v1/users/{target_user.id}/roles",
        json={"roles": ["portfolio_manager"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["roles"] == ["portfolio_manager"]

    # Verify target's next request via existing token reflects new role
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {target_token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["roles"] == ["portfolio_manager"]


@pytest.mark.parametrize(
    "role_name",
    ["portfolio_manager", "project_manager", "team_member"],
)
def test_patch_user_roles_non_admin_forbidden(client, db_session, role_name):
    """Non-org_admin roles receive 403 on PATCH /users/{user_id}/roles."""
    org = create_org(db_session)
    caller, token = make_user_in_org(db_session, org.id, [role_name])
    target, _ = make_user_in_org(db_session, org.id, ["team_member"])

    resp = client.patch(
        f"/api/v1/users/{target.id}/roles",
        json={"roles": ["project_manager"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_patch_user_roles_validation_errors(client, db_session):
    """Invalid role names or empty roles list return 422 Unprocessable Entity."""
    org = create_org(db_session)
    _, admin_token = make_user_in_org(db_session, org.id, ["org_admin"])
    target, _ = make_user_in_org(db_session, org.id, ["team_member"])

    # Invalid role name
    resp_invalid = client.patch(
        f"/api/v1/users/{target.id}/roles",
        json={"roles": ["super_admin"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_invalid.status_code == 422

    # Empty roles list
    resp_empty = client.patch(
        f"/api/v1/users/{target.id}/roles",
        json={"roles": []},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_empty.status_code == 422


# ---------------------------------------------------------------------------
# 4. PATCH /api/v1/users/{user_id}
# ---------------------------------------------------------------------------


def test_patch_user_admin_updates_name_and_active_status(client, db_session):
    """org_admin can update name and is_active for users in their org."""
    org = create_org(db_session)
    _, admin_token = make_user_in_org(db_session, org.id, ["org_admin"])
    target, _ = make_user_in_org(db_session, org.id, ["team_member"], name="Old Name")

    resp = client.patch(
        f"/api/v1/users/{target.id}",
        json={"name": "New Name", "is_active": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_patch_user_self_service_can_update_own_name(client, db_session):
    """A regular member can update their own name."""
    org = create_org(db_session)
    member, token = make_user_in_org(db_session, org.id, ["team_member"], name="Original Name")

    resp = client.patch(
        f"/api/v1/users/{member.id}",
        json={"name": "Updated Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


def test_patch_user_self_service_cannot_update_others_or_active_status(client, db_session):
    """A regular member cannot update another user (403) and cannot set is_active (403)."""
    org = create_org(db_session)
    member_a, token_a = make_user_in_org(db_session, org.id, ["team_member"])
    member_b, _ = make_user_in_org(db_session, org.id, ["team_member"])

    # Attempt to update someone else -> 403
    resp_other = client.patch(
        f"/api/v1/users/{member_b.id}",
        json={"name": "Hacked Name"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_other.status_code == 403

    # Attempt to update own is_active -> 403
    resp_active = client.patch(
        f"/api/v1/users/{member_a.id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_active.status_code == 403


# ---------------------------------------------------------------------------
# 5. Tenant Isolation
# ---------------------------------------------------------------------------


def test_tenant_isolation_404_for_cross_org_access(client, db_session):
    """An org_admin in Org A targeting a user in Org B receives 404 for all {user_id} endpoints."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    _, admin_token_a = make_user_in_org(db_session, org_a.id, ["org_admin"])
    user_b, _ = make_user_in_org(db_session, org_b.id, ["team_member"])

    # PATCH /users/{user_id}/roles
    resp_roles = client.patch(
        f"/api/v1/users/{user_b.id}/roles",
        json={"roles": ["project_manager"]},
        headers={"Authorization": f"Bearer {admin_token_a}"},
    )
    assert resp_roles.status_code == 404

    # PATCH /users/{user_id}
    resp_user = client.patch(
        f"/api/v1/users/{user_b.id}",
        json={"name": "Hacked Cross Org"},
        headers={"Authorization": f"Bearer {admin_token_a}"},
    )
    assert resp_user.status_code == 404


# ---------------------------------------------------------------------------
# 6. Lockout Protection
# ---------------------------------------------------------------------------


def test_lockout_protection_cannot_demote_or_deactivate_last_active_admin(client, db_session):
    """Cannot demote or deactivate the last active org_admin (400), but allowed once a second active admin exists."""
    org = create_org(db_session)
    admin_1, admin_token_1 = make_user_in_org(db_session, org.id, ["org_admin"])

    # Demoting last admin -> 400
    resp_demote = client.patch(
        f"/api/v1/users/{admin_1.id}/roles",
        json={"roles": ["team_member"]},
        headers={"Authorization": f"Bearer {admin_token_1}"},
    )
    assert resp_demote.status_code == 400
    assert "Cannot remove org_admin role from the last active" in resp_demote.json()["detail"]

    # Deactivating last admin -> 400
    resp_deactivate = client.patch(
        f"/api/v1/users/{admin_1.id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token_1}"},
    )
    assert resp_deactivate.status_code == 400
    assert "Cannot deactivate the last active" in resp_deactivate.json()["detail"]

    # Add a second active org_admin
    admin_2, admin_token_2 = make_user_in_org(db_session, org.id, ["org_admin"])

    # Now deactivating admin_1 succeeds
    resp_deact_ok = client.patch(
        f"/api/v1/users/{admin_1.id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token_1}"},
    )
    assert resp_deact_ok.status_code == 200

    # With admin_1 inactive, admin_2 is now the sole active admin. Attempting to demote admin_2 -> 400
    resp_demote_sole = client.patch(
        f"/api/v1/users/{admin_2.id}/roles",
        json={"roles": ["portfolio_manager"]},
        headers={"Authorization": f"Bearer {admin_token_2}"},
    )
    assert resp_demote_sole.status_code == 400



# ---------------------------------------------------------------------------
# 7. Deactivation
# ---------------------------------------------------------------------------


def test_deactivation_blocks_login_and_invalidates_current_token(client, db_session):
    """A deactivated user cannot log in (generic 401) and access token issued before deactivation stops working (401)."""
    org = create_org(db_session)
    _, admin_token = make_user_in_org(db_session, org.id, ["org_admin"])
    target_user, target_token = make_user_in_org(db_session, org.id, ["team_member"])

    # Confirm token currently works
    me_resp_ok = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {target_token}"},
    )
    assert me_resp_ok.status_code == 200

    # Admin deactivates user
    deact_resp = client.patch(
        f"/api/v1/users/{target_user.id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deact_resp.status_code == 200

    # 1. Existing access token now returns 401
    me_resp_after = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {target_token}"},
    )
    assert me_resp_after.status_code == 401
    assert "inactive" in me_resp_after.json()["detail"].lower()

    # 2. Login returns generic 401
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": target_user.email, "password": "Password123!"},
    )
    assert login_resp.status_code == 401
    assert login_resp.json()["detail"] == "Invalid email or password."
