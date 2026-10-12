"""Targeted unit tests for direct repository operations and query handling (Phase 11)."""

import uuid
from datetime import date
from decimal import Decimal

from app.models.organization import Organization
from app.models.project import Project
from app.models.risk import RiskLevel, RiskStatus
from app.models.task import TaskPriority, TaskStatus
from app.repositories.budget_repository import budget_repository
from app.repositories.expense_repository import expense_repository
from app.repositories.risk_repository import risk_repository
from app.repositories.task_repository import task_repository
from tests.conftest_db import db_engine, db_session  # noqa: F401


def create_org(db_session) -> Organization:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


def test_budget_repository_actual_spend_empty_vs_expenses(db_session):
    """BudgetRepository.get_actual_spend returns Decimal('0.00') for empty expenses and accurate sum otherwise."""
    org = create_org(db_session)
    project = Project(organization_id=org.id, name="Budget Rep Test")
    db_session.add(project)
    db_session.commit()

    # Empty expenses
    spend_zero = budget_repository.get_actual_spend(db_session, project_id=project.id)
    assert spend_zero == Decimal("0.00")

    # Add expenses
    expense_repository.create(db_session, project_id=project.id, amount=Decimal("120.50"), description="E1", expense_date=date.today())
    expense_repository.create(db_session, project_id=project.id, amount=Decimal("80.25"), description="E2", expense_date=date.today())
    db_session.commit()

    spend_total = budget_repository.get_actual_spend(db_session, project_id=project.id)
    assert spend_total == Decimal("200.75")


def test_risk_repository_filtering_by_status(db_session):
    """RiskRepository.list_by_project accurately filters by RiskStatus."""
    org = create_org(db_session)
    project = Project(organization_id=org.id, name="Risk Rep Test")
    db_session.add(project)
    db_session.flush()

    risk_repository.create(db_session, project_id=project.id, title="R1", description=None, probability=RiskLevel.low, impact=RiskLevel.low, status=RiskStatus.open)
    risk_repository.create(db_session, project_id=project.id, title="R2", description=None, probability=RiskLevel.medium, impact=RiskLevel.high, status=RiskStatus.closed)
    db_session.commit()

    open_risks, open_count = risk_repository.list_by_project(db_session, project_id=project.id, status_filter=RiskStatus.open)
    assert open_count == 1
    assert open_risks[0].title == "R1"

    all_risks, all_count = risk_repository.list_by_project(db_session, project_id=project.id, status_filter=None)
    assert all_count == 2


def test_task_repository_multi_criteria_filtering(db_session):
    """TaskRepository.list_by_project filters by multiple criteria simultaneously."""
    org = create_org(db_session)
    project = Project(organization_id=org.id, name="Task Rep Test")
    db_session.add(project)
    db_session.flush()

    task_repository.create(db_session, project_id=project.id, title="T1", description=None, status=TaskStatus.todo, priority=TaskPriority.high)
    task_repository.create(db_session, project_id=project.id, title="T2", description=None, status=TaskStatus.done, priority=TaskPriority.high)
    task_repository.create(db_session, project_id=project.id, title="T3", description=None, status=TaskStatus.todo, priority=TaskPriority.low)
    db_session.commit()

    filtered, count = task_repository.list_by_project(
        db_session,
        project_id=project.id,
        status=TaskStatus.todo,
        priority=TaskPriority.high,
    )
    assert count == 1
    assert filtered[0].title == "T1"
