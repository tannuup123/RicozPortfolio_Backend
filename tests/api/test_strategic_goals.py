"""Automated tests for Strategic Goals API endpoints (Phase 5 Track A)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.role import Role
from app.models.strategic_goal import StrategicGoal
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
    """Helper to create a new Organization."""
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
    """Factory helper to create a user with specific roles in an org and return (user, token)."""
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


def create_goal_in_org(
    db_session,
    org_id: uuid.UUID,
    title: str = "Increase Cloud Adoption",
    description: str | None = "Target 80% workload migrated",
) -> StrategicGoal:
    """Helper to create a StrategicGoal in an organization directly."""
    goal = StrategicGoal(
        organization_id=org_id,
        title=title,
        description=description,
    )
    db_session.add(goal)
    db_session.commit()
    db_session.refresh(goal)
    return goal


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role_name",
    ["org_admin", "portfolio_manager", "project_manager", "team_member"],
)
def test_list_goals_any_role_succeeds(client, db_session, role_name):
    """All authenticated roles can list strategic goals in their organization."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, [role_name])
    create_goal_in_org(db_session, org.id, title="Goal 1")
    create_goal_in_org(db_session, org.id, title="Goal 2")

    response = client.get(
        "/api/v1/strategic-goals",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] == 2
    assert len(data["items"]) == 2
    titles = [item["title"] for item in data["items"]]
    assert "Goal 1" in titles
    assert "Goal 2" in titles


def test_list_goals_unauthenticated_returns_401(client):
    """Unauthenticated request to list goals returns 401."""
    response = client.get("/api/v1/strategic-goals")
    assert response.status_code == 401


def test_create_goal_as_portfolio_manager_succeeds(client, db_session):
    """Portfolio manager can create a strategic goal."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])

    payload = {
        "title": "Drive AI Innovation",
        "description": "Establish internal generative AI platform",
    }
    response = client.post(
        "/api/v1/strategic-goals",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == payload["title"]
    assert data["description"] == payload["description"]
    assert data["organization_id"] == str(org.id)
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_goal_as_org_admin_succeeds(client, db_session):
    """Org admin inherits portfolio_manager rights and can create a strategic goal."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, ["org_admin"])

    payload = {"title": "Expand Global Reach", "description": "Enter APAC markets"}
    response = client.post(
        "/api/v1/strategic-goals",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == payload["title"]
    assert data["organization_id"] == str(org.id)


def test_create_goal_as_project_manager_forbidden(client, db_session):
    """Project manager is forbidden from creating strategic goals (403)."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, ["project_manager"])

    payload = {"title": "PM Goal"}
    response = client.post(
        "/api/v1/strategic-goals",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 403


def test_create_goal_as_team_member_forbidden(client, db_session):
    """Team member is forbidden from creating strategic goals (403)."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, ["team_member"])

    payload = {"title": "Team Member Goal"}
    response = client.post(
        "/api/v1/strategic-goals",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 403


def test_get_goal_by_id_succeeds(client, db_session):
    """Any authenticated user in the organization can retrieve a goal by ID."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, ["team_member"])
    goal = create_goal_in_org(db_session, org.id, title="Specific Goal")

    response = client.get(
        f"/api/v1/strategic-goals/{goal.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(goal.id)
    assert data["title"] == "Specific Goal"


def test_get_goal_not_found_returns_404(client, db_session):
    """Non-existent goal ID returns 404."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, ["team_member"])

    response = client.get(
        f"/api/v1/strategic-goals/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_update_goal_as_portfolio_manager_succeeds(client, db_session):
    """Portfolio manager can update goal title and description."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    goal = create_goal_in_org(db_session, org.id, title="Initial Title")

    payload = {"title": "Updated Title", "description": "Updated Description"}
    response = client.patch(
        f"/api/v1/strategic-goals/{goal.id}",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["description"] == "Updated Description"


def test_update_goal_as_team_member_forbidden(client, db_session):
    """Team member cannot update strategic goals (403)."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, ["team_member"])
    goal = create_goal_in_org(db_session, org.id, title="Protected Goal")

    payload = {"title": "Hacked Title"}
    response = client.patch(
        f"/api/v1/strategic-goals/{goal.id}",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 403


def test_delete_goal_as_admin_succeeds(client, db_session):
    """Org admin (or portfolio manager) can delete a strategic goal."""
    org = create_org(db_session)
    _, token = make_user_in_org(db_session, org.id, ["org_admin"])
    goal = create_goal_in_org(db_session, org.id, title="To Delete")

    response = client.delete(
        f"/api/v1/strategic-goals/{goal.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    # Verify it is no longer retrieved
    get_res = client.get(
        f"/api/v1/strategic-goals/{goal.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 404


def test_tenant_isolation_cannot_access_other_orgs_goal(client, db_session):
    """Users cannot get, update, or delete a strategic goal belonging to another organization."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    _, token_b = make_user_in_org(db_session, org_b.id, ["org_admin"])
    goal_a = create_goal_in_org(db_session, org_a.id, title="Org A Secret Goal")

    # Org B user tries to GET Org A's goal -> 404
    get_res = client.get(
        f"/api/v1/strategic-goals/{goal_a.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert get_res.status_code == 404

    # Org B user tries to PATCH Org A's goal -> 404
    patch_res = client.patch(
        f"/api/v1/strategic-goals/{goal_a.id}",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"title": "Compromised"},
    )
    assert patch_res.status_code == 404

    # Org B user tries to DELETE Org A's goal -> 404
    delete_res = client.delete(
        f"/api/v1/strategic-goals/{goal_a.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert delete_res.status_code == 404

    # Org B list must not include Org A's goal
    list_res = client.get(
        "/api/v1/strategic-goals",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert all(item["id"] != str(goal_a.id) for item in items)
