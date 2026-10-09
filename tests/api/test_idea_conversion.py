"""Automated tests for Idea Conversion API endpoints (Phase 6)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.idea import Idea, IdeaStatus
from app.models.organization import Organization
from app.models.portfolio import Portfolio
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
    title: str = "Approved Idea to Convert",
    description: str = "Detailed conversion description",
    status: IdeaStatus = IdeaStatus.approved,
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


def create_portfolio_in_org(
    db_session,
    org_id: uuid.UUID,
    name: str = "Target Portfolio",
) -> Portfolio:
    portfolio = Portfolio(
        organization_id=org_id,
        name=name,
        description="Target portfolio for converted project",
    )
    db_session.add(portfolio)
    db_session.commit()
    db_session.refresh(portfolio)
    return portfolio


# ---------------------------------------------------------------------------
# Test Cases (17 tests)
# ---------------------------------------------------------------------------


def test_convert_approved_idea_no_portfolio(client, db_session):
    """CV-01: Converts without portfolio_id -> 201, status=planned, portfolio_id=null."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.approved)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == idea.title
    assert data["status"] == "planned"
    assert data["portfolio_id"] is None
    assert data["source_idea_id"] == str(idea.id)
    assert data["organization_id"] == str(org.id)


def test_convert_approved_idea_with_portfolio(client, db_session):
    """CV-02: Converts with valid portfolio_id in org -> 201, portfolio_id set."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.approved)
    portfolio = create_portfolio_in_org(db_session, org.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={"portfolio_id": str(portfolio.id)},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["portfolio_id"] == str(portfolio.id)
    assert data["source_idea_id"] == str(idea.id)


def test_convert_not_approved_idea_returns_400(client, db_session):
    """CV-03: Status=submitted -> 400."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.submitted)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 400
    assert "approved before conversion" in response.json()["detail"].lower()


def test_convert_draft_idea_returns_400(client, db_session):
    """CV-04: Status=draft -> 400."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.draft)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 400


def test_convert_rejected_idea_returns_400(client, db_session):
    """CV-05: Status=rejected -> 400."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.rejected)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 400


def test_double_conversion_returns_409(client, db_session):
    """CV-06: Second convert attempt -> 409 Conflict."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.approved)

    res1 = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert res1.status_code == 201

    res2 = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert res2.status_code == 409
    assert "already been converted" in res2.json()["detail"].lower()


def test_convert_as_team_member_forbidden(client, db_session):
    """CV-07: team_member -> 403."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])
    idea = create_idea_in_org(db_session, org.id, user.id, status=IdeaStatus.approved)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 403


def test_convert_as_project_manager_forbidden(client, db_session):
    """CV-08: project_manager -> 403."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["project_manager"])
    idea = create_idea_in_org(db_session, org.id, user.id, status=IdeaStatus.approved)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 403


def test_convert_as_org_admin_succeeds(client, db_session):
    """CV-09: org_admin -> 201."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    idea = create_idea_in_org(db_session, org.id, admin.id, status=IdeaStatus.approved)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 201


def test_convert_project_prefills_name_from_idea(client, db_session):
    """CV-10: Project.name == idea.title."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(
        db_session, org.id, pm.id, title="Specific Title", status=IdeaStatus.approved
    )

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Specific Title"


def test_convert_project_prefills_description_from_idea(client, db_session):
    """CV-11: Project.description == idea.description."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(
        db_session, org.id, pm.id, description="Specific Long Description", status=IdeaStatus.approved
    )

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 201
    assert response.json()["description"] == "Specific Long Description"


def test_convert_project_source_idea_id_set(client, db_session):
    """CV-12: Project.source_idea_id == idea.id."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.approved)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 201
    assert response.json()["source_idea_id"] == str(idea.id)


def test_convert_portfolio_not_in_org_returns_404(client, db_session):
    """CV-13: portfolio_id from different org -> 404."""
    org1 = create_org(db_session)
    org2 = create_org(db_session)

    pm1, token1 = make_user_in_org(db_session, org1.id, ["portfolio_manager"])
    idea1 = create_idea_in_org(db_session, org1.id, pm1.id, status=IdeaStatus.approved)

    portfolio2 = create_portfolio_in_org(db_session, org2.id)

    response = client.post(
        f"/api/v1/ideas/{idea1.id}/convert",
        headers={"Authorization": f"Bearer {token1}"},
        json={"portfolio_id": str(portfolio2.id)},
    )
    assert response.status_code == 404
    assert "Portfolio not found" in response.json()["detail"]


def test_convert_unauthenticated_returns_401(client, db_session):
    """CV-14: No token -> 401."""
    random_id = uuid.uuid4()
    response = client.post(
        f"/api/v1/ideas/{random_id}/convert",
        json={},
    )
    assert response.status_code == 401


def test_convert_idea_not_in_org_returns_404(client, db_session):
    """CV-15: Cross-org idea_id -> 404."""
    org1 = create_org(db_session)
    org2 = create_org(db_session)

    pm1, token1 = make_user_in_org(db_session, org1.id, ["portfolio_manager"])
    pm2, token2 = make_user_in_org(db_session, org2.id, ["portfolio_manager"])

    idea2 = create_idea_in_org(db_session, org2.id, pm2.id, status=IdeaStatus.approved)

    response = client.post(
        f"/api/v1/ideas/{idea2.id}/convert",
        headers={"Authorization": f"Bearer {token1}"},
        json={},
    )
    assert response.status_code == 404


def test_converted_project_has_status_planned(client, db_session):
    """CV-16: Project.status == 'planned'."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.approved)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "planned"


def test_convert_project_organization_id_matches_caller_org(client, db_session):
    """CV-17: org isolation on created project."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.approved)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 201
    assert response.json()["organization_id"] == str(org.id)


def test_convert_approved_idea_with_soft_deleted_portfolio_returns_404(client, db_session):
    """CV-18: Converting an approved idea targeting a soft-deleted portfolio returns 404."""
    from datetime import datetime, timezone

    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.approved)

    portfolio = Portfolio(
        organization_id=org.id,
        name="Soft Deleted Portfolio",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(portfolio)
    db_session.commit()
    db_session.refresh(portfolio)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {token}"},
        json={"portfolio_id": str(portfolio.id)},
    )
    assert response.status_code == 404
    assert "Portfolio not found in your organization." in response.json()["detail"]
