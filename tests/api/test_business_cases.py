"""Automated tests for BusinessCase API endpoints (Phase 6)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.idea import Idea, IdeaStatus
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


def create_idea_in_org(
    db_session,
    org_id: uuid.UUID,
    author_id: uuid.UUID,
    title: str = "Idea with BC",
    description: str = "Description for BC",
    status: IdeaStatus = IdeaStatus.submitted,
) -> Idea:
    idea = Idea(
        organization_id=org_id,
        author_id=author_id,
        title=title,
        description=description,
        status=status,
    )
    db_session.add(idea)
    db_session.commit()
    db_session.refresh(idea)
    return idea


# ---------------------------------------------------------------------------
# Test Cases (15 tests)
# ---------------------------------------------------------------------------


def test_create_business_case_as_pm_succeeds(client, db_session):
    """BC-01: PM can POST a business case; returns 201; response includes computed ROI."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 50000.0, "estimated_benefit": 150000.0},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["idea_id"] == str(idea.id)
    assert data["estimated_cost"] == 50000.0
    assert data["estimated_benefit"] == 150000.0
    assert float(data["roi"]) == 2.0


def test_create_business_case_as_org_admin_succeeds(client, db_session):
    """BC-02: org_admin can POST a business case; returns 201."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    idea = create_idea_in_org(db_session, org.id, admin.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 10000.0, "estimated_benefit": 20000.0},
    )
    assert response.status_code == 201
    assert float(response.json()["roi"]) == 1.0


def test_create_business_case_as_team_member_forbidden(client, db_session):
    """BC-03: team_member gets 403."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])
    idea = create_idea_in_org(db_session, org.id, user.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 10000.0, "estimated_benefit": 20000.0},
    )
    assert response.status_code == 403


def test_create_business_case_as_project_manager_forbidden(client, db_session):
    """BC-04: project_manager gets 403."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["project_manager"])
    idea = create_idea_in_org(db_session, org.id, user.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 10000.0, "estimated_benefit": 20000.0},
    )
    assert response.status_code == 403


def test_update_business_case_patch_succeeds(client, db_session):
    """BC-05: PATCH updates existing BC; ROI recalculated and quantized via Decimal (asserts roi == 1.67)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id)

    client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 50000.0, "estimated_benefit": 100000.0},
    )

    response = client.patch(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 75000.0, "estimated_benefit": 200000.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["estimated_cost"] == 75000.0
    assert data["estimated_benefit"] == 200000.0
    assert float(data["roi"]) == 1.67


def test_roi_computed_correctly(client, db_session):
    """BC-06: (50000 cost, 150000 benefit) -> ROI = 2.0; (75000 cost, 200000 benefit) -> ROI = 1.67."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id)

    # 1. 50k cost, 150k benefit -> 2.0
    res1 = client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 50000.0, "estimated_benefit": 150000.0},
    )
    assert res1.status_code == 201
    assert float(res1.json()["roi"]) == 2.0

    # 2. 75k cost, 200k benefit -> 1.67
    res2 = client.patch(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 75000.0, "estimated_benefit": 200000.0},
    )
    assert res2.status_code == 200
    assert float(res2.json()["roi"]) == 1.67


def test_roi_zero_cost_returns_null(client, db_session):
    """BC-07: estimated_cost=0 -> roi is null."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 0.0, "estimated_benefit": 50000.0},
    )
    assert response.status_code == 201
    assert response.json()["roi"] is None


def test_get_business_case_any_authenticated_user(client, db_session):
    """BC-08: team_member can GET an existing business case."""
    org = create_org(db_session)
    pm, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    member, member_token = make_user_in_org(db_session, org.id, ["team_member"])
    idea = create_idea_in_org(db_session, org.id, pm.id)

    client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"estimated_cost": 10000.0, "estimated_benefit": 30000.0},
    )

    response = client.get(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert response.status_code == 200
    assert response.json()["idea_id"] == str(idea.id)


def test_get_business_case_not_found_returns_404(client, db_session):
    """BC-09: idea has no BC -> 404."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])
    idea = create_idea_in_org(db_session, org.id, user.id)

    response = client.get(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_unauthenticated_request_returns_401(client, db_session):
    """BC-10: No token -> 401."""
    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/ideas/{random_id}/business-case")
    assert response.status_code == 401


def test_idea_not_in_org_returns_404(client, db_session):
    """BC-11: Cross-org idea_id -> 404 (tenant isolation)."""
    org1 = create_org(db_session)
    org2 = create_org(db_session)

    pm1, token1 = make_user_in_org(db_session, org1.id, ["portfolio_manager"])
    pm2, token2 = make_user_in_org(db_session, org2.id, ["portfolio_manager"])

    idea2 = create_idea_in_org(db_session, org2.id, pm2.id)

    # User in org1 attempts to create BC on idea in org2
    res_post = client.post(
        f"/api/v1/ideas/{idea2.id}/business-case",
        headers={"Authorization": f"Bearer {token1}"},
        json={"estimated_cost": 10000.0, "estimated_benefit": 20000.0},
    )
    assert res_post.status_code == 404

    # User in org1 attempts to get BC on idea in org2
    res_get = client.get(
        f"/api/v1/ideas/{idea2.id}/business-case",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert res_get.status_code == 404


def test_negative_cost_returns_422(client, db_session):
    """BC-12: estimated_cost < 0 -> 422 validation error."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": -50.0, "estimated_benefit": 100.0},
    )
    assert response.status_code == 422


def test_negative_benefit_returns_422(client, db_session):
    """BC-13: estimated_benefit < 0 -> 422 validation error."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 50.0, "estimated_benefit": -100.0},
    )
    assert response.status_code == 422


def test_create_duplicate_business_case_returns_409(client, db_session):
    """BC-14: Second POST for same idea -> 409 Conflict."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id)

    res1 = client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 1000.0, "estimated_benefit": 2000.0},
    )
    assert res1.status_code == 201

    res2 = client.post(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 1500.0, "estimated_benefit": 3000.0},
    )
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


def test_patch_nonexistent_business_case_returns_404(client, db_session):
    """BC-15: PATCH when no BC exists yet -> 404."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id)

    response = client.patch(
        f"/api/v1/ideas/{idea.id}/business-case",
        headers={"Authorization": f"Bearer {token}"},
        json={"estimated_cost": 5000.0, "estimated_benefit": 10000.0},
    )
    assert response.status_code == 404
    assert "No business case found" in response.json()["detail"]
