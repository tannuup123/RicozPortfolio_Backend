"""Integration tests for Phase 9 (Financial & Risk: INT9-01 to INT9-03)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.portfolio import Portfolio
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectMemberRole
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


def test_financial_lifecycle_end_to_end(client, db_session):
    """INT9-01: End-to-end financial lifecycle.

    1. Create Project and assign PM and Team Member.
    2. Check initial budget defaults (0 planned, 0 actual).
    3. PM sets planned budget ($25,000 USD).
    4. PM logs multiple expenses ($3,200 and $1,850.50).
    5. Planned-vs-actual automatically reflects SUM of expenses ($5,050.50).
    6. PM adjusts budget amount and currency ($30,000 EUR).
    7. Team member views budget and expense history.
    8. Team member attempt to mutate budget or log expenses is rejected (403).
    """
    org = create_org(db_session)
    pm, pm_token = make_user_in_org(db_session, org.id, ["project_manager"], name="Project Manager")
    member, member_token = make_user_in_org(db_session, org.id, ["team_member"], name="Team Member")

    # Setup project and memberships
    portfolio = Portfolio(organization_id=org.id, name="Core Portfolio")
    db_session.add(portfolio)
    db_session.flush()

    project = Project(organization_id=org.id, portfolio_id=portfolio.id, name="Cloud Migration")
    db_session.add(project)
    db_session.flush()

    db_session.add_all([
        ProjectMember(project_id=project.id, user_id=pm.id, project_role=ProjectMemberRole.manager),
        ProjectMember(project_id=project.id, user_id=member.id, project_role=ProjectMemberRole.member),
    ])
    db_session.commit()

    # Step 1: Initial budget query
    res_b0 = client.get(
        f"/api/v1/projects/{project.id}/budget",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_b0.status_code == 200
    b0 = res_b0.json()
    assert b0["id"] is None
    assert Decimal(str(b0["amount"])) == Decimal("0.00")
    assert Decimal(str(b0["actual_spend"])) == Decimal("0.00")
    assert b0["currency"] == "USD"

    # Step 2: PM sets planned budget
    res_b1 = client.put(
        f"/api/v1/projects/{project.id}/budget",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"amount": 25000.00, "currency": "USD"},
    )
    assert res_b1.status_code == 200
    b1 = res_b1.json()
    assert b1["id"] is not None
    assert Decimal(str(b1["amount"])) == Decimal("25000.00")
    assert Decimal(str(b1["actual_spend"])) == Decimal("0.00")

    # Step 3: PM logs first expense
    today = date.today().isoformat()
    res_e1 = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"amount": 3200.00, "description": "Software Licenses", "date": today},
    )
    assert res_e1.status_code == 201

    # Step 4: Verify actual_spend updated to 3200.00
    res_b2 = client.get(
        f"/api/v1/projects/{project.id}/budget",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_b2.status_code == 200
    assert Decimal(str(res_b2.json()["actual_spend"])) == Decimal("3200.00")

    # Step 5: PM logs second expense
    res_e2 = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"amount": 1850.50, "description": "Consulting Services", "date": today},
    )
    assert res_e2.status_code == 201

    # Step 6: Verify actual_spend updated to 5050.50 (3200 + 1850.50)
    res_b3 = client.get(
        f"/api/v1/projects/{project.id}/budget",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_b3.status_code == 200
    b3 = res_b3.json()
    assert Decimal(str(b3["amount"])) == Decimal("25000.00")
    assert Decimal(str(b3["actual_spend"])) == Decimal("5050.50")

    # Step 7: PM adjusts budget amount and currency
    res_b4 = client.put(
        f"/api/v1/projects/{project.id}/budget",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"amount": 30000.00, "currency": "eur"},
    )
    assert res_b4.status_code == 200
    b4 = res_b4.json()
    assert Decimal(str(b4["amount"])) == Decimal("30000.00")
    assert b4["currency"] == "EUR"
    assert Decimal(str(b4["actual_spend"])) == Decimal("5050.50")

    # Step 8: Team member views budget and expense list
    res_mb = client.get(
        f"/api/v1/projects/{project.id}/budget",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res_mb.status_code == 200
    assert Decimal(str(res_mb.json()["actual_spend"])) == Decimal("5050.50")

    res_me = client.get(
        f"/api/v1/projects/{project.id}/expenses",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res_me.status_code == 200
    assert res_me.json()["total"] == 2

    # Step 9: Team member is forbidden from mutating budget or logging expenses
    res_denied_b = client.put(
        f"/api/v1/projects/{project.id}/budget",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"amount": 99999.00, "currency": "USD"},
    )
    assert res_denied_b.status_code == 403

    res_denied_e = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"amount": 100.00, "description": "Unauthorized spend", "date": today},
    )
    assert res_denied_e.status_code == 403


def test_risk_management_lifecycle_end_to_end(client, db_session):
    """INT9-02: End-to-end risk management lifecycle.

    1. PM logs multiple risks with distinct severity levels.
    2. Filter risks by status (all initially open).
    3. Mitigate high-impact risk with notes.
    4. Transition status: open -> mitigated -> closed.
    5. Delete low-severity risk.
    6. Verify risk count and remaining statuses.
    """
    org = create_org(db_session)
    pm, pm_token = make_user_in_org(db_session, org.id, ["project_manager"])

    project = Project(organization_id=org.id, name="Security Overhaul")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=pm.id, project_role=ProjectMemberRole.manager))
    db_session.commit()

    # Step 1: Create 3 risks
    r1_payload = {
        "title": "Data breach through unpatched library",
        "description": "CVE-2026-XXXX found in dependency",
        "probability": "high",
        "impact": "high",
        "status": "open",
    }
    res_r1 = client.post(
        f"/api/v1/projects/{project.id}/risks",
        headers={"Authorization": f"Bearer {pm_token}"},
        json=r1_payload,
    )
    assert res_r1.status_code == 201
    r1_id = res_r1.json()["id"]

    r2_payload = {
        "title": "Vendor SLA downtime",
        "probability": "medium",
        "impact": "medium",
        "status": "open",
    }
    res_r2 = client.post(
        f"/api/v1/projects/{project.id}/risks",
        headers={"Authorization": f"Bearer {pm_token}"},
        json=r2_payload,
    )
    assert res_r2.status_code == 201
    r2_id = res_r2.json()["id"]

    r3_payload = {
        "title": "Minor localization typo",
        "probability": "low",
        "impact": "low",
        "status": "open",
    }
    res_r3 = client.post(
        f"/api/v1/projects/{project.id}/risks",
        headers={"Authorization": f"Bearer {pm_token}"},
        json=r3_payload,
    )
    assert res_r3.status_code == 201
    r3_id = res_r3.json()["id"]

    # Step 2: List all risks
    res_list = client.get(
        f"/api/v1/projects/{project.id}/risks",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_list.status_code == 200
    assert res_list.json()["total"] == 3

    # Step 3: Mitigate Risk 1
    res_mit = client.patch(
        f"/api/v1/risks/{r1_id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"status": "mitigated", "description": "Patched to version 2.4.1 in staging"},
    )
    assert res_mit.status_code == 200
    assert res_mit.json()["status"] == "mitigated"

    # Step 4: Verify filter by status
    res_open = client.get(
        f"/api/v1/projects/{project.id}/risks?status=open",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_open.status_code == 200
    assert res_open.json()["total"] == 2

    res_mitigated = client.get(
        f"/api/v1/projects/{project.id}/risks?status=mitigated",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_mitigated.status_code == 200
    assert res_mitigated.json()["total"] == 1
    assert res_mitigated.json()["items"][0]["id"] == r1_id

    # Step 5: Close Risk 1
    res_close = client.patch(
        f"/api/v1/risks/{r1_id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"status": "closed"},
    )
    assert res_close.status_code == 200
    assert res_close.json()["status"] == "closed"

    # Step 6: Delete Risk 3 (minor typo)
    res_del = client.delete(
        f"/api/v1/risks/{r3_id}",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_del.status_code == 204

    # Direct get on deleted risk returns 404
    assert client.get(f"/api/v1/risks/{r3_id}", headers={"Authorization": f"Bearer {pm_token}"}).status_code == 404

    # Final list check: 2 risks total (one closed, one open)
    res_final = client.get(
        f"/api/v1/projects/{project.id}/risks",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert res_final.status_code == 200
    assert res_final.json()["total"] == 2
    ids = {r["id"] for r in res_final.json()["items"]}
    assert ids == {r1_id, r2_id}


def test_multi_tenant_isolation_financial_and_risks(client, db_session):
    """INT9-03: Multi-tenant isolation for Budgets, Expenses, and Risks.

    - Org A and Org B both create projects, budgets, expenses, and risks.
    - Neither org can view, modify, or delete the other org's resources (404).
    - Actual spend calculations are strictly isolated per tenant.
    """
    org_a = create_org(db_session)
    org_b = create_org(db_session)
    admin_a, token_a = make_user_in_org(db_session, org_a.id, ["org_admin"], name="Admin A")
    admin_b, token_b = make_user_in_org(db_session, org_b.id, ["org_admin"], name="Admin B")

    prj_a = Project(organization_id=org_a.id, name="Project Alpha")
    prj_b = Project(organization_id=org_b.id, name="Project Beta")
    db_session.add_all([prj_a, prj_b])
    db_session.commit()

    # Org A sets budget and logs expense
    client.put(
        f"/api/v1/projects/{prj_a.id}/budget",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"amount": 10000.00, "currency": "USD"},
    )
    client.post(
        f"/api/v1/projects/{prj_a.id}/expenses",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"amount": 2500.00, "description": "Alpha expense", "date": date.today().isoformat()},
    )
    res_ra = client.post(
        f"/api/v1/projects/{prj_a.id}/risks",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Alpha Risk", "status": "open"},
    )
    risk_a_id = res_ra.json()["id"]

    # Org B sets budget and logs expense
    client.put(
        f"/api/v1/projects/{prj_b.id}/budget",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"amount": 20000.00, "currency": "USD"},
    )
    client.post(
        f"/api/v1/projects/{prj_b.id}/expenses",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"amount": 7500.00, "description": "Beta expense", "date": date.today().isoformat()},
    )
    res_rb = client.post(
        f"/api/v1/projects/{prj_b.id}/risks",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"title": "Beta Risk", "status": "open"},
    )
    risk_b_id = res_rb.json()["id"]

    # 1. Budget isolation
    # Org A cannot access Org B budget
    assert client.get(f"/api/v1/projects/{prj_b.id}/budget", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404
    assert client.put(f"/api/v1/projects/{prj_b.id}/budget", headers={"Authorization": f"Bearer {token_a}"}, json={"amount": 1.00}).status_code == 404

    # Org B cannot access Org A budget
    assert client.get(f"/api/v1/projects/{prj_a.id}/budget", headers={"Authorization": f"Bearer {token_b}"}).status_code == 404
    assert client.put(f"/api/v1/projects/{prj_a.id}/budget", headers={"Authorization": f"Bearer {token_b}"}, json={"amount": 1.00}).status_code == 404

    # 2. Expense isolation
    today_iso = date.today().isoformat()
    # Org A cannot access Org B expenses
    assert client.get(f"/api/v1/projects/{prj_b.id}/expenses", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404
    assert client.post(
        f"/api/v1/projects/{prj_b.id}/expenses",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"amount": 1.00, "description": "H", "date": today_iso},
    ).status_code == 404

    # Org B cannot access Org A expenses
    assert client.get(f"/api/v1/projects/{prj_a.id}/expenses", headers={"Authorization": f"Bearer {token_b}"}).status_code == 404
    assert client.post(
        f"/api/v1/projects/{prj_a.id}/expenses",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"amount": 1.00, "description": "H", "date": today_iso},
    ).status_code == 404

    # 3. Risk isolation
    # Org A cannot access Org B risks
    assert client.get(f"/api/v1/projects/{prj_b.id}/risks", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404
    assert client.post(f"/api/v1/projects/{prj_b.id}/risks", headers={"Authorization": f"Bearer {token_a}"}, json={"title": "H"}).status_code == 404
    assert client.get(f"/api/v1/risks/{risk_b_id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404
    assert client.patch(f"/api/v1/risks/{risk_b_id}", headers={"Authorization": f"Bearer {token_a}"}, json={"status": "closed"}).status_code == 404
    assert client.delete(f"/api/v1/risks/{risk_b_id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # Org B cannot access Org A risks
    assert client.get(f"/api/v1/projects/{prj_a.id}/risks", headers={"Authorization": f"Bearer {token_b}"}).status_code == 404
    assert client.post(f"/api/v1/projects/{prj_a.id}/risks", headers={"Authorization": f"Bearer {token_b}"}, json={"title": "H"}).status_code == 404
    assert client.get(f"/api/v1/risks/{risk_a_id}", headers={"Authorization": f"Bearer {token_b}"}).status_code == 404
    assert client.patch(f"/api/v1/risks/{risk_a_id}", headers={"Authorization": f"Bearer {token_b}"}, json={"status": "closed"}).status_code == 404
    assert client.delete(f"/api/v1/risks/{risk_a_id}", headers={"Authorization": f"Bearer {token_b}"}).status_code == 404

    # 4. Calculation isolation (no leakage across tenants)
    res_ba = client.get(f"/api/v1/projects/{prj_a.id}/budget", headers={"Authorization": f"Bearer {token_a}"})
    assert Decimal(str(res_ba.json()["actual_spend"])) == Decimal("2500.00")

    res_bb = client.get(f"/api/v1/projects/{prj_b.id}/budget", headers={"Authorization": f"Bearer {token_b}"})
    assert Decimal(str(res_bb.json()["actual_spend"])) == Decimal("7500.00")
