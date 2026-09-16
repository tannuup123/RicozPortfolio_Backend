import pytest
from sqlalchemy.exc import IntegrityError

from app.models.budget import ProjectBudget
from app.models.organization import Organization
from app.models.project import Project, ProjectStatus
from app.models.user import User


def test_create_organization(db_session):
    org = Organization(name="Acme Corp")
    db_session.add(org)
    db_session.commit()
    assert org.id is not None
    assert org.name == "Acme Corp"

def test_create_user_unique_email(db_session):
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.commit()

    user1 = User(
        organization_id=org.id,
        email="test@example.com",
        hashed_password="hash",
        name="Test User 1"
    )
    db_session.add(user1)
    db_session.commit()

    user2 = User(
        organization_id=org.id,
        email="test@example.com", # Duplicate email
        hashed_password="hash",
        name="Test User 2"
    )
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_project_budget_unique_per_project(db_session):
    org = Organization(name="Budget Org")
    db_session.add(org)
    db_session.commit()

    project = Project(
        organization_id=org.id,
        name="Project X",
        status=ProjectStatus.planned
    )
    db_session.add(project)
    db_session.commit()

    budget1 = ProjectBudget(
        project_id=project.id,
        amount=1000.0,
        currency="USD"
    )
    db_session.add(budget1)
    db_session.commit()

    budget2 = ProjectBudget(
        project_id=project.id, # Duplicate project_id
        amount=2000.0,
        currency="USD"
    )
    db_session.add(budget2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_seed_migration_roles(db_session):
    from app.models.role import Role
    roles = db_session.query(Role).all()
    role_names = {role.name for role in roles}
    expected_roles = {"org_admin", "portfolio_manager", "project_manager", "team_member"}
    assert role_names == expected_roles
    assert len(roles) == 4
