"""Automated end-to-end integration tests for Phase 6."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
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


def create_org(db_session, name: str = "Test Org") -> Organization:
    org = Organization(name=f"{name} {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


def make_user_in_org(
    db_session,
    org_id: uuid.UUID,
    role_names: list[str],
    name: str = "Test User",
) -> tuple[User, str]:
    user = User(
        email=f"usr_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("Password123!"),
        name=name,
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

    token = create_access_token(user_id=user.id, organization_id=org_id)
    return user, token


def create_portfolio_in_org(
    db_session,
    org_id: uuid.UUID,
    name: str = "Strategic Portfolio",
) -> Portfolio:
    portfolio = Portfolio(
        organization_id=org_id,
        name=name,
        description="Target portfolio for projects",
    )
    db_session.add(portfolio)
    db_session.commit()
    db_session.refresh(portfolio)
    return portfolio


# ---------------------------------------------------------------------------
# Integration Tests (3 tests)
# ---------------------------------------------------------------------------


def test_full_idea_to_project_journey(client, db_session):
    """INT-01: Full end-to-end journey via API endpoints only.

    Steps:
    1. Register/create organization and users (portfolio_manager, team_member).
    2. Team member creates idea (initial status submitted).
    3. Portfolio manager advances idea to in_review.
    4. Portfolio manager creates business case (POST 201) and updates it (PATCH 200).
    5. Portfolio manager approves idea (POST 201) -> idea status approved.
    6. Portfolio manager converts idea to project with target portfolio (POST 201).
    7. Verify created project details and source_idea_id linkage.
    """
    org = create_org(db_session, name="Acme Corp")
    pm, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"], name="Alice PM")
    dev, dev_token = make_user_in_org(db_session, org.id, ["team_member"], name="Bob Dev")
    portfolio = create_portfolio_in_org(db_session, org.id, name="Digital Transformation")

    # Step 2: Submit idea
    res_idea = client.post(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {dev_token}"},
        json={
            "title": "Cloud Migration Initiative",
            "description": "Migrate on-prem infrastructure to AWS cloud.",
            "status": "submitted",
        },
    )
    assert res_idea.status_code == 201
    idea_id = res_idea.json()["id"]
    assert res_idea.json()["status"] == "submitted"

    # Step 3: Advance idea to in_review
    res_review = client.patch(
        f"/api/v1/ideas/{idea_id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"status": "in_review"},
    )
    assert res_review.status_code == 200
    assert res_review.json()["status"] == "in_review"

    # Step 4: Create business case and PATCH update
    res_bc = client.post(
        f"/api/v1/ideas/{idea_id}/business-case",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"estimated_cost": 50000.0, "estimated_benefit": 150000.0},
    )
    assert res_bc.status_code == 201
    assert float(res_bc.json()["roi"]) == 2.0

    res_bc_patch = client.patch(
        f"/api/v1/ideas/{idea_id}/business-case",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"estimated_cost": 75000.0, "estimated_benefit": 200000.0},
    )
    assert res_bc_patch.status_code == 200
    assert float(res_bc_patch.json()["roi"]) == 1.67

    # Step 5: Approve idea
    res_appr = client.post(
        f"/api/v1/ideas/{idea_id}/approvals",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"decision": "approved", "notes": "Approved with high expected ROI."},
    )
    assert res_appr.status_code == 201
    assert res_appr.json()["decision"] == "approved"

    # Verify idea status is now approved
    res_idea_check = client.get(
        f"/api/v1/ideas/{idea_id}",
        headers={"Authorization": f"Bearer {dev_token}"},
    )
    assert res_idea_check.status_code == 200
    assert res_idea_check.json()["status"] == "approved"

    # Step 6: Convert to project
    res_proj = client.post(
        f"/api/v1/ideas/{idea_id}/convert",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"portfolio_id": str(portfolio.id)},
    )
    assert res_proj.status_code == 201
    proj_data = res_proj.json()
    assert proj_data["name"] == "Cloud Migration Initiative"
    assert proj_data["description"] == "Migrate on-prem infrastructure to AWS cloud."
    assert proj_data["status"] == "planned"
    assert proj_data["portfolio_id"] == str(portfolio.id)
    assert proj_data["source_idea_id"] == idea_id
    assert proj_data["organization_id"] == str(org.id)

    # Step 7: Duplicate conversion is prevented
    res_dup = client.post(
        f"/api/v1/ideas/{idea_id}/convert",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"portfolio_id": str(portfolio.id)},
    )
    assert res_dup.status_code == 409


def test_full_rejection_journey(client, db_session):
    """INT-02: End-to-end rejection path.

    Steps:
    1. Create idea, submit.
    2. Move to in_review.
    3. Create business case.
    4. Reject idea.
    5. Verify idea status is rejected and approval history contains record.
    6. Verify conversion is blocked (400).
    """
    org = create_org(db_session, name="Beta Corp")
    pm, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"])
    dev, dev_token = make_user_in_org(db_session, org.id, ["team_member"])

    # Create idea
    res_idea = client.post(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {dev_token}"},
        json={
            "title": "High Risk Speculative Project",
            "description": "Experiment with unsupported tech stack.",
            "status": "submitted",
        },
    )
    assert res_idea.status_code == 201
    idea_id = res_idea.json()["id"]

    # Move to in_review
    res_rev = client.patch(
        f"/api/v1/ideas/{idea_id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"status": "in_review"},
    )
    assert res_rev.status_code == 200

    # Create BC
    res_bc = client.post(
        f"/api/v1/ideas/{idea_id}/business-case",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"estimated_cost": 100000.0, "estimated_benefit": 50000.0},
    )
    assert res_bc.status_code == 201

    # Reject idea
    res_rej = client.post(
        f"/api/v1/ideas/{idea_id}/approvals",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"decision": "rejected", "notes": "Negative ROI expectation."},
    )
    assert res_rej.status_code == 201
    assert res_rej.json()["decision"] == "rejected"

    # Verify idea status is rejected
    res_idea_check = client.get(
        f"/api/v1/ideas/{idea_id}",
        headers={"Authorization": f"Bearer {dev_token}"},
    )
    assert res_idea_check.status_code == 200
    assert res_idea_check.json()["status"] == "rejected"

    # Verify approval history
    res_history = client.get(
        f"/api/v1/ideas/{idea_id}/approvals",
        headers={"Authorization": f"Bearer {dev_token}"},
    )
    assert res_history.status_code == 200
    assert res_history.json()["total"] == 1
    assert res_history.json()["items"][0]["decision"] == "rejected"

    # Verify convert attempt returns 400
    res_conv = client.post(
        f"/api/v1/ideas/{idea_id}/convert",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={},
    )
    assert res_conv.status_code == 400


def test_cross_org_isolation_full_journey(client, db_session):
    """INT-03: Two orgs; Org A cannot see or operate on Org B's business cases or approvals."""
    org1 = create_org(db_session, name="Org Alpha")
    org2 = create_org(db_session, name="Org Bravo")

    pm1, token1 = make_user_in_org(db_session, org1.id, ["portfolio_manager"])
    pm2, token2 = make_user_in_org(db_session, org2.id, ["portfolio_manager"])

    # Org2 creates idea and BC
    res_idea2 = client.post(
        "/api/v1/ideas",
        headers={"Authorization": f"Bearer {token2}"},
        json={"title": "Org2 Secret Initiative", "description": "Confidential", "status": "submitted"},
    )
    assert res_idea2.status_code == 201
    idea2_id = res_idea2.json()["id"]

    res_bc2 = client.post(
        f"/api/v1/ideas/{idea2_id}/business-case",
        headers={"Authorization": f"Bearer {token2}"},
        json={"estimated_cost": 20000.0, "estimated_benefit": 60000.0},
    )
    assert res_bc2.status_code == 201

    # PM1 in Org1 cannot GET Org2's BC
    res_get_bc = client.get(
        f"/api/v1/ideas/{idea2_id}/business-case",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert res_get_bc.status_code == 404

    # PM1 in Org1 cannot PATCH Org2's BC
    res_patch_bc = client.patch(
        f"/api/v1/ideas/{idea2_id}/business-case",
        headers={"Authorization": f"Bearer {token1}"},
        json={"estimated_cost": 10000.0, "estimated_benefit": 30000.0},
    )
    assert res_patch_bc.status_code == 404

    # PM1 in Org1 cannot post approval on Org2's idea
    res_appr = client.post(
        f"/api/v1/ideas/{idea2_id}/approvals",
        headers={"Authorization": f"Bearer {token1}"},
        json={"decision": "approved"},
    )
    assert res_appr.status_code == 404

    # PM1 in Org1 cannot list approvals for Org2's idea
    res_list_appr = client.get(
        f"/api/v1/ideas/{idea2_id}/approvals",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert res_list_appr.status_code == 404

    # PM1 in Org1 cannot convert Org2's idea
    res_conv = client.post(
        f"/api/v1/ideas/{idea2_id}/convert",
        headers={"Authorization": f"Bearer {token1}"},
        json={},
    )
    assert res_conv.status_code == 404
