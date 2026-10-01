"""Automated tests for Ideas API endpoints (Phase 5 Track B)."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.idea import Idea, IdeaStatus
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
    title: str = "Target Goal",
) -> StrategicGoal:
    """Helper to create a strategic goal."""
    goal = StrategicGoal(organization_id=org_id, title=title)
    db_session.add(goal)
    db_session.commit()
    db_session.refresh(goal)
    return goal


def create_idea_in_org(
    db_session,
    org_id: uuid.UUID,
    author_id: uuid.UUID,
    title: str = "Innovative Idea",
    description: str = "Detailed description",
    status: IdeaStatus = IdeaStatus.submitted,
    strategic_goal_id: uuid.UUID | None = None,
    deleted_at: datetime | None = None,
) -> Idea:
    """Helper to create an Idea in the DB."""
    idea = Idea(
        organization_id=org_id,
        author_id=author_id,
        title=title,
        description=description,
        status=status,
        strategic_goal_id=strategic_goal_id,
        deleted_at=deleted_at,
    )
    db_session.add(idea)
    db_session.commit()
    db_session.refresh(idea)
    return idea


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role_name",
    ["org_admin", "portfolio_manager", "project_manager", "team_member"],
)
def test_submit_idea_as_any_role_succeeds(client, db_session, role_name):
    """Any authenticated user can submit an idea, defaulting to submitted status."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, [role_name])

    payload = {
        "title": f"Idea from {role_name}",
        "description": "Exploration of new AI workflows",
    }
    response = client.post(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == payload["title"]
    assert data["description"] == payload["description"]
    assert data["status"] == "submitted"
    assert data["author_id"] == str(user.id)
    assert data["organization_id"] == str(org.id)
    assert "id" in data


def test_submit_idea_unauthenticated_returns_401(client):
    """Submitting an idea without authentication returns 401."""
    response = client.post(
        "/api/v1/ideas",
        json={"title": "Anon Idea", "description": "No auth"},
    )
    assert response.status_code == 401


def test_submit_idea_with_strategic_goal_link(client, db_session):
    """Submitting an idea linked to a valid strategic goal preserves the foreign key."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])
    goal = create_goal_in_org(db_session, org.id, title="Efficiency Boost")

    payload = {
        "title": "Automate Reports",
        "description": "Save 5 hours weekly",
        "strategic_goal_id": str(goal.id),
    }
    response = client.post(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["strategic_goal_id"] == str(goal.id)


def test_submit_idea_with_invalid_goal_id_returns_404(client, db_session):
    """Linking an idea to a strategic goal from another organization returns 404."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    goal_a = create_goal_in_org(db_session, org_a.id, title="Org A Goal")
    _, token_b = make_user_in_org(db_session, org_b.id, ["team_member"])

    payload = {
        "title": "Cross Org Link Attempt",
        "description": "Should fail with 404",
        "strategic_goal_id": str(goal_a.id),
    }
    response = client.post(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {token_b}"},
        json=payload,
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "role_name",
    ["org_admin", "portfolio_manager", "project_manager", "team_member"],
)
def test_list_ideas_any_role_succeeds(client, db_session, role_name):
    """All authenticated roles can list active ideas within their organization."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, [role_name])
    create_idea_in_org(db_session, org.id, user.id, title="Idea 1")
    create_idea_in_org(db_session, org.id, user.id, title="Idea 2")

    response = client.get(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_ideas_excludes_soft_deleted(client, db_session):
    """Soft-deleted ideas are excluded from list queries."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])
    create_idea_in_org(db_session, org.id, user.id, title="Active Idea")
    create_idea_in_org(
        db_session,
        org.id,
        user.id,
        title="Deleted Idea",
        deleted_at=datetime.now(timezone.utc),
    )

    response = client.get(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Active Idea"


def test_get_idea_by_id_succeeds(client, db_session):
    """Retrieving an existing idea by ID succeeds for an authenticated user."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])
    idea = create_idea_in_org(db_session, org.id, user.id, title="Specific Idea")

    response = client.get(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(idea.id)
    assert data["title"] == "Specific Idea"


def test_get_idea_not_found_returns_404(client, db_session):
    """Non-existent or soft-deleted idea returns 404."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])

    # Non-existent ID
    response = client.get(
        f"/api/v1/ideas/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404

    # Soft-deleted idea ID
    deleted_idea = create_idea_in_org(
        db_session,
        org.id,
        user.id,
        title="Deleted",
        deleted_at=datetime.now(timezone.utc),
    )
    res_deleted = client.get(
        f"/api/v1/ideas/{deleted_idea.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_deleted.status_code == 404


def test_status_transition_portfolio_manager_can_advance_status(client, db_session):
    """Portfolio manager can advance idea statuses: draft -> submitted -> in_review -> approved."""
    org = create_org(db_session)
    _, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    author, _ = make_user_in_org(db_session, org.id, ["team_member"])

    idea = create_idea_in_org(
        db_session, org.id, author.id, title="Flow Idea", status=IdeaStatus.draft
    )

    # 1. draft -> submitted
    res1 = client.patch(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"status": "submitted"},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "submitted"

    # 2. submitted -> in_review
    res2 = client.patch(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"status": "in_review"},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "in_review"

    # 3. in_review -> approved
    res3 = client.patch(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"status": "approved"},
    )
    assert res3.status_code == 200
    assert res3.json()["status"] == "approved"


def test_status_transition_team_member_cannot_change_status(client, db_session):
    """Team member cannot change the status of an idea (403)."""
    org = create_org(db_session)
    author, author_token = make_user_in_org(db_session, org.id, ["team_member"])
    idea = create_idea_in_org(
        db_session, org.id, author.id, title="Status Test", status=IdeaStatus.draft
    )

    response = client.patch(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {author_token}"},
        json={"status": "submitted"},
    )
    assert response.status_code == 403


def test_invalid_status_transition_returns_400(client, db_session):
    """Invalid backwards or skip transition returns 400."""
    org = create_org(db_session)
    _, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    author, _ = make_user_in_org(db_session, org.id, ["team_member"])

    idea = create_idea_in_org(
        db_session, org.id, author.id, title="Status Test", status=IdeaStatus.approved
    )

    response = client.patch(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"status": "draft"},
    )
    assert response.status_code == 400


def test_content_edit_own_draft_idea_succeeds(client, db_session):
    """Author can edit title/description of their own idea while it is in draft status."""
    org = create_org(db_session)
    author, author_token = make_user_in_org(db_session, org.id, ["team_member"])
    idea = create_idea_in_org(
        db_session,
        org.id,
        author.id,
        title="Original Draft Title",
        description="Original Desc",
        status=IdeaStatus.draft,
    )

    payload = {"title": "Updated Draft Title", "description": "Updated Desc"}
    response = client.patch(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {author_token}"},
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Draft Title"
    assert data["description"] == "Updated Desc"


def test_content_edit_others_idea_forbidden(client, db_session):
    """A regular user cannot edit an idea authored by someone else (403)."""
    org = create_org(db_session)
    author, _ = make_user_in_org(db_session, org.id, ["team_member"])
    _, other_token = make_user_in_org(db_session, org.id, ["team_member"])

    idea = create_idea_in_org(
        db_session, org.id, author.id, title="Author Draft", status=IdeaStatus.draft
    )

    response = client.patch(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"title": "Hacked Title"},
    )
    assert response.status_code == 403


def test_content_edit_submitted_idea_forbidden(client, db_session):
    """A regular user cannot edit their own idea once it is submitted or in review (403)."""
    org = create_org(db_session)
    author, author_token = make_user_in_org(db_session, org.id, ["team_member"])

    idea = create_idea_in_org(
        db_session, org.id, author.id, title="Submitted Idea", status=IdeaStatus.submitted
    )

    response = client.patch(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {author_token}"},
        json={"title": "Attempted Edit"},
    )
    assert response.status_code == 403


def test_soft_delete_as_portfolio_manager_succeeds(client, db_session):
    """Portfolio manager (or org admin) can soft-delete an idea."""
    org = create_org(db_session)
    _, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    author, _ = make_user_in_org(db_session, org.id, ["team_member"])

    idea = create_idea_in_org(db_session, org.id, author.id, title="To Soft Delete")

    del_res = client.delete(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert del_res.status_code == 204

    # GET returns 404
    get_res = client.get(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert get_res.status_code == 404

    # List returns empty
    list_res = client.get(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 0


def test_soft_delete_as_team_member_forbidden(client, db_session):
    """Team member cannot delete an idea (403)."""
    org = create_org(db_session)
    author, author_token = make_user_in_org(db_session, org.id, ["team_member"])
    idea = create_idea_in_org(db_session, org.id, author.id, title="Cannot Delete")

    del_res = client.delete(
        f"/api/v1/ideas/{idea.id}",
        headers={"Authorization": f"Bearer {author_token}"},
    )
    assert del_res.status_code == 403


def test_tenant_isolation_cannot_access_other_orgs_idea(client, db_session):
    """Users cannot get, update, or delete an idea belonging to another organization."""
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    author_a, _ = make_user_in_org(db_session, org_a.id, ["team_member"])
    idea_a = create_idea_in_org(db_session, org_a.id, author_a.id, title="Org A Idea")

    _, admin_b_token = make_user_in_org(db_session, org_b.id, ["org_admin"])

    # Org B user tries GET Org A idea -> 404
    get_res = client.get(
        f"/api/v1/ideas/{idea_a.id}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert get_res.status_code == 404

    # Org B user tries PATCH Org A idea -> 404
    patch_res = client.patch(
        f"/api/v1/ideas/{idea_a.id}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
        json={"title": "Tampered"},
    )
    assert patch_res.status_code == 404

    # Org B user tries DELETE Org A idea -> 404
    delete_res = client.delete(
        f"/api/v1/ideas/{idea_a.id}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert delete_res.status_code == 404

    # Org B list does not contain Org A idea
    list_res = client.get(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert all(item["id"] != str(idea_a.id) for item in items)
