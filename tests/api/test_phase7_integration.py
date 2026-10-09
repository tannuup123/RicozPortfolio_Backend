"""Integration tests for Phase 7 (Portfolio & Project Core: INT7-01 to INT7-03)."""

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


def test_full_portfolio_project_lifecycle_journey(client, db_session):
    """INT7-01: Complete lifecycle journey:

    1. Portfolio manager creates a Portfolio.
    2. Direct project is created inside the portfolio (starts as 'planned').
    3. Creator is automatically the project manager.
    4. Project manager adds team members to the project.
    5. Project manager updates status from 'planned' -> 'active'.
    6. Portfolio details endpoint accurately reflects 1 project count.
    7. Project is listed under portfolio filter.
    """
    org = create_org(db_session)
    pm, pm_token = make_user_in_org(db_session, org.id, ["portfolio_manager"], name="Alice PM")
    engineer, eng_token = make_user_in_org(db_session, org.id, ["team_member"], name="Bob Dev")

    # 1. Create Portfolio
    port_res = client.post(
        "/api/v1/portfolios",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"name": "Cloud Transformation", "description": "Migration to Cloud"},
    )
    assert port_res.status_code == 201
    port_id = port_res.json()["id"]

    # 2. Create Project directly in Portfolio
    prj_res = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={
            "name": "Database Migration",
            "description": "Migrate MySQL to Postgres",
            "portfolio_id": port_id,
        },
    )
    assert prj_res.status_code == 201
    prj_data = prj_res.json()
    prj_id = prj_data["id"]
    assert prj_data["status"] == "planned"
    assert prj_data["portfolio_id"] == port_id

    # 3. Verify creator is project manager
    members_res = client.get(
        f"/api/v1/projects/{prj_id}/members",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert members_res.status_code == 200
    members = members_res.json()["items"]
    assert len(members) == 1
    assert members[0]["user_id"] == str(pm.id)
    assert members[0]["project_role"] == "manager"

    # 4. Add engineer as team member
    add_res = client.post(
        f"/api/v1/projects/{prj_id}/members",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"user_id": str(engineer.id), "project_role": "member"},
    )
    assert add_res.status_code == 201
    assert add_res.json()["user_id"] == str(engineer.id)

    # 5. Update project status to active
    patch_res = client.patch(
        f"/api/v1/projects/{prj_id}",
        headers={"Authorization": f"Bearer {pm_token}"},
        json={"status": "active"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "active"

    # 6. Verify portfolio project_count is 1
    port_detail = client.get(
        f"/api/v1/portfolios/{port_id}",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert port_detail.status_code == 200
    assert port_detail.json()["project_count"] == 1

    # 7. Engineer can list the project
    eng_list = client.get(
        f"/api/v1/projects?portfolio_id={port_id}",
        headers={"Authorization": f"Bearer {eng_token}"},
    )
    assert eng_list.status_code == 200
    assert eng_list.json()["total"] == 1
    assert eng_list.json()["items"][0]["id"] == prj_id


def test_converted_idea_project_management_journey(client, db_session):
    """INT7-02: Converted idea project management journey:

    1. Convert approved idea to project (Phase 6 endpoint POST /ideas/{id}/convert).
    2. Retrieve project via Phase 7 GET /projects/{id} (initially has 0 members because conversion does not add members).
    3. Org admin adds a project manager to the converted project.
    4. Assigned project manager updates project name and description.
    5. Verify source_idea_id is linked properly.
    """
    org = create_org(db_session)
    admin, admin_token = make_user_in_org(db_session, org.id, ["org_admin"], name="Org Admin")
    pjm, pjm_token = make_user_in_org(db_session, org.id, ["project_manager"], name="Project Lead")

    # Create portfolio
    port_res = client.post(
        "/api/v1/portfolios",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Innovation Lab"},
    )
    assert port_res.status_code == 201
    port_id = port_res.json()["id"]

    # Create approved idea
    idea = Idea(
        organization_id=org.id,
        author_id=admin.id,
        title="AI Chatbot Assistant",
        description="Internal customer service chatbot",
        status=IdeaStatus.approved,
    )
    db_session.add(idea)
    db_session.commit()

    # 1. Convert idea to project
    conv_res = client.post(
        f"/api/v1/ideas/{idea.id}/convert",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"portfolio_id": port_id},
    )
    assert conv_res.status_code == 201
    prj_id = conv_res.json()["id"]
    assert conv_res.json()["source_idea_id"] == str(idea.id)

    # 2. Retrieve via Phase 7 endpoint
    get_res = client.get(
        f"/api/v1/projects/{prj_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "AI Chatbot Assistant"
    assert len(get_res.json()["members"]) == 0

    # 3. Org admin assigns pjm as project manager
    add_m = client.post(
        f"/api/v1/projects/{prj_id}/members",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_id": str(pjm.id), "project_role": "manager"},
    )
    assert add_m.status_code == 201

    # 4. Assigned project manager updates project attributes
    patch_res = client.patch(
        f"/api/v1/projects/{prj_id}",
        headers={"Authorization": f"Bearer {pjm_token}"},
        json={"description": "Updated scope for AI bot"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["description"] == "Updated scope for AI bot"
    assert patch_res.json()["source_idea_id"] == str(idea.id)


def test_multi_tenant_isolation_cross_portfolio_and_projects(client, db_session):
    """INT7-03: Multi-tenant isolation cross portfolio and projects:

    Org A and Org B users cannot access, see, modify, or assign cross-org resources.
    """
    org_a = create_org(db_session)
    org_b = create_org(db_session)

    pm_a, token_a = make_user_in_org(db_session, org_a.id, ["portfolio_manager"], name="Org A PM")
    pm_b, token_b = make_user_in_org(db_session, org_b.id, ["portfolio_manager"], name="Org B PM")

    # Create Org A resources
    port_a = client.post("/api/v1/portfolios", headers={"Authorization": f"Bearer {token_a}"}, json={"name": "Port A"}).json()
    client.post("/api/v1/projects", headers={"Authorization": f"Bearer {token_a}"}, json={"name": "Prj A", "portfolio_id": port_a["id"]})

    # Create Org B resources
    port_b = client.post("/api/v1/portfolios", headers={"Authorization": f"Bearer {token_b}"}, json={"name": "Port B"}).json()
    prj_b = client.post("/api/v1/projects", headers={"Authorization": f"Bearer {token_b}"}, json={"name": "Prj B", "portfolio_id": port_b["id"]}).json()

    # Cross-tenant portfolio list isolation
    list_port_a = client.get("/api/v1/portfolios", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert all(p["id"] != port_b["id"] for p in list_port_a["items"])

    # Cross-tenant project list isolation
    list_prj_a = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert all(p["id"] != prj_b["id"] for p in list_prj_a["items"])

    # Cross-tenant direct access
    assert client.get(f"/api/v1/portfolios/{port_b['id']}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404
    assert client.get(f"/api/v1/projects/{prj_b['id']}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # Cross-tenant modification
    assert client.patch(f"/api/v1/portfolios/{port_b['id']}", headers={"Authorization": f"Bearer {token_a}"}, json={"name": "Hack"}).status_code == 404
    assert client.patch(f"/api/v1/projects/{prj_b['id']}", headers={"Authorization": f"Bearer {token_a}"}, json={"name": "Hack"}).status_code == 404

    # Cross-tenant member add
    assert client.post(f"/api/v1/projects/{prj_b['id']}/members", headers={"Authorization": f"Bearer {token_a}"}, json={"user_id": str(pm_a.id)}).status_code == 404
