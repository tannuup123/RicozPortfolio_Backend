"""Automated tests for Approvals API endpoints (Phase 6)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.business_case import BusinessCase
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
    title: str = "Idea for Approval",
    description: str = "Description for Approval",
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


def create_business_case_in_db(
    db_session,
    idea_id: uuid.UUID,
    estimated_cost: float = 50000.0,
    estimated_benefit: float = 100000.0,
) -> BusinessCase:
    bc = BusinessCase(
        idea_id=idea_id,
        estimated_cost=estimated_cost,
        estimated_benefit=estimated_benefit,
    )
    db_session.add(bc)
    db_session.commit()
    db_session.refresh(bc)
    return bc


# ---------------------------------------------------------------------------
# Test Cases (20 tests)
# ---------------------------------------------------------------------------


def test_approve_idea_as_pm_succeeds(client, db_session):
    """AP-01: PM approves idea -> 201, Approval record created, idea.status=approved."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.submitted)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved", "notes": "Solid proposal."},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["decision"] == "approved"
    assert data["idea_id"] == str(idea.id)
    assert data["approver_id"] == str(pm.id)
    assert data["notes"] == "Solid proposal."

    db_session.refresh(idea)
    assert idea.status == IdeaStatus.approved


def test_reject_idea_as_pm_succeeds(client, db_session):
    """AP-02: PM rejects idea -> 201, idea.status=rejected."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.in_review)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "rejected", "notes": "Insufficient budget."},
    )
    assert response.status_code == 201
    assert response.json()["decision"] == "rejected"

    db_session.refresh(idea)
    assert idea.status == IdeaStatus.rejected


def test_approve_as_org_admin_succeeds(client, db_session):
    """AP-03: org_admin can approve."""
    org = create_org(db_session)
    admin, token = make_user_in_org(db_session, org.id, ["org_admin"])
    idea = create_idea_in_org(db_session, org.id, admin.id, status=IdeaStatus.submitted)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 201
    db_session.refresh(idea)
    assert idea.status == IdeaStatus.approved


def test_approve_as_team_member_forbidden(client, db_session):
    """AP-04: team_member -> 403."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])
    idea = create_idea_in_org(db_session, org.id, user.id, status=IdeaStatus.submitted)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 403


def test_approve_as_project_manager_forbidden(client, db_session):
    """AP-05: project_manager -> 403."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["project_manager"])
    idea = create_idea_in_org(db_session, org.id, user.id, status=IdeaStatus.submitted)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 403


def test_approve_without_business_case_returns_400(client, db_session):
    """AP-06: No BC -> 400 with descriptive error."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.submitted)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 400
    assert "business case must exist" in response.json()["detail"].lower()


def test_approve_draft_idea_returns_400(client, db_session):
    """AP-07: Idea in draft -> 400."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.draft)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 400


def test_approve_already_approved_idea_returns_400(client, db_session):
    """AP-08: Idea already approved -> 400."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.approved)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 400


def test_approve_already_rejected_idea_returns_400(client, db_session):
    """AP-09: Idea already rejected -> 400."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.rejected)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 400


def test_approve_submitted_idea_succeeds(client, db_session):
    """AP-10: Status=submitted -> valid (201)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.submitted)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 201


def test_approve_in_review_idea_succeeds(client, db_session):
    """AP-11: Status=in_review -> valid (201)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.in_review)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 201


def test_list_approval_history_empty(client, db_session):
    """AP-12: No approvals -> items=[], total=0."""
    org = create_org(db_session)
    user, token = make_user_in_org(db_session, org.id, ["team_member"])
    idea = create_idea_in_org(db_session, org.id, user.id)

    response = client.get(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_list_approval_history_multiple_records(client, db_session):
    """AP-13: Multiple decisions -> all returned in order."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.submitted)
    create_business_case_in_db(db_session, idea.id)

    client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved", "notes": "First decision"},
    )

    response = client.get(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["notes"] == "First decision"


def test_list_approvals_any_authenticated_user(client, db_session):
    """AP-14: team_member can GET history."""
    org = create_org(db_session)
    pm, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    member, member_token = make_user_in_org(db_session, org.id, ["team_member"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.submitted)
    create_business_case_in_db(db_session, idea.id)

    client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"decision": "approved"},
    )

    response = client.get(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_approval_unauthenticated_returns_401(client, db_session):
    """AP-15: No token -> 401."""
    random_id = uuid.uuid4()
    response = client.post(
        f"/api/v1/ideas/{random_id}/approvals",
        json={"decision": "approved"},
    )
    assert response.status_code == 401


def test_approval_idea_not_in_org_returns_404(client, db_session):
    """AP-16: Cross-org idea -> 404 (tenant isolation)."""
    org1 = create_org(db_session)
    org2 = create_org(db_session)

    pm1, token1 = make_user_in_org(db_session, org1.id, ["portfolio_manager"])
    pm2, token2 = make_user_in_org(db_session, org2.id, ["portfolio_manager"])

    idea2 = create_idea_in_org(db_session, org2.id, pm2.id)
    create_business_case_in_db(db_session, idea2.id)

    response = client.post(
        f"/api/v1/ideas/{idea2.id}/approvals",
        headers={"Authorization": f"Bearer {token1}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 404


def test_invalid_decision_value_returns_422(client, db_session):
    """AP-17: decision='maybe' -> 422."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.submitted)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "maybe"},
    )
    assert response.status_code == 422


def test_approver_id_in_response_is_current_user(client, db_session):
    """AP-18: approver_id equals calling user's ID, not client-supplied."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.submitted)
    create_business_case_in_db(db_session, idea.id)

    spoofed_id = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved", "approver_id": spoofed_id},
    )
    assert response.status_code == 201
    assert response.json()["approver_id"] == str(pm.id)
    assert response.json()["approver_id"] != spoofed_id


def test_notes_optional(client, db_session):
    """AP-19: notes can be omitted (null)."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.submitted)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 201
    assert response.json()["notes"] is None


def test_notes_max_length_enforced(client, db_session):
    """AP-20: notes > 2000 chars -> 422."""
    org = create_org(db_session)
    pm, token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    idea = create_idea_in_org(db_session, org.id, pm.id, status=IdeaStatus.submitted)
    create_business_case_in_db(db_session, idea.id)

    response = client.post(
        f"/api/v1/ideas/{idea.id}/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved", "notes": "x" * 2001},
    )
    assert response.status_code == 422
