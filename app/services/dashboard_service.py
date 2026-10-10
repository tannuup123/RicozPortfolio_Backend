"""Service layer for Dashboard operations (Phase 10).

Computes project and portfolio dashboard metrics live from the database.
No computed values are cached or persisted (architecture.md §7).

Health-flag rules (mvp-requirements.md §10.2 — concrete implementation of [PROPOSED]):
  off_track : actual_spend > planned_amount (over budget; planned == 0 treated as
              zero-budget so any spend > 0 triggers off_track)
  at_risk   : (not off_track) AND (any open risk with impact == 'high'
               OR budget_utilization_pct >= 80)
  on_track  : everything else

Zero-budget policy:
  When no budget row exists (or planned_amount == 0), budget_utilization_pct is
  reported as Decimal("0.00") so callers never divide by zero.  The health flag
  will still be at_risk / off_track if spend exists or a high-impact risk exists.
"""

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.risk import RiskLevel, RiskStatus
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.repositories.budget_repository import budget_repository
from app.repositories.portfolio_repository import portfolio_repository
from app.repositories.project_member_repository import project_member_repository
from app.repositories.project_repository import project_repository
from app.repositories.risk_repository import risk_repository
from app.schemas.dashboard import (
    HealthFlag,
    PortfolioDashboardResponse,
    ProjectDashboardResponse,
    ProjectSummary,
)

_ZERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Internal permission helpers (same pattern as budget_service / risk_service)
# ---------------------------------------------------------------------------


def _caller_is_broad_manager(caller: User) -> bool:
    return bool({r.name for r in caller.roles} & {"org_admin", "portfolio_manager"})


def _require_project_in_org(
    db: Session,
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> Project:
    project = project_repository.get_by_id_within_org(
        db, project_id=project_id, organization_id=organization_id
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return project


def _caller_can_view_project(
    db: Session,
    caller: User,
    project_id: uuid.UUID,
) -> bool:
    if _caller_is_broad_manager(caller):
        return True
    membership = project_member_repository.get_membership(
        db, project_id=project_id, user_id=caller.id
    )
    return membership is not None


# ---------------------------------------------------------------------------
# Internal computation helpers
# ---------------------------------------------------------------------------


def _compute_task_metrics(db: Session, project_id: uuid.UUID) -> tuple[int, int, Decimal]:
    """Return (task_total, task_done, task_completion_pct)."""
    task_total: int = (
        db.query(func.count(Task.id)).filter(Task.project_id == project_id).scalar() or 0
    )
    task_done: int = (
        db.query(func.count(Task.id))
        .filter(Task.project_id == project_id, Task.status == TaskStatus.done)
        .scalar()
        or 0
    )
    if task_total == 0:
        completion_pct = _ZERO
    else:
        completion_pct = Decimal(str(round(task_done / task_total * 100, 2)))
    return task_total, task_done, completion_pct


def _compute_budget_metrics(db: Session, project_id: uuid.UUID) -> tuple[Decimal, Decimal, Decimal]:
    """Return (budget_planned, budget_actual, budget_utilization_pct).

    Zero-budget policy: utilization_pct is 0.00 when planned == 0 to avoid
    division-by-zero. The health-flag logic still handles spend-without-budget.
    """
    budget = budget_repository.get_by_project_id(db, project_id=project_id)
    planned = Decimal(str(budget.amount)) if budget else _ZERO
    actual = budget_repository.get_actual_spend(db, project_id=project_id)

    if planned == _ZERO:
        utilization_pct = _ZERO
    else:
        utilization_pct = Decimal(str(round(float(actual) / float(planned) * 100, 2)))

    return planned, actual, utilization_pct


def _count_open_risks(db: Session, project_id: uuid.UUID) -> int:
    """Count risks with status == 'open'."""
    rows, total = risk_repository.list_by_project(
        db, project_id=project_id, status_filter=RiskStatus.open, limit=1000, offset=0
    )
    return total


def _has_high_impact_open_risk(db: Session, project_id: uuid.UUID) -> bool:
    """Return True if any open risk has impact == 'high'."""
    from app.models.risk import Risk  # local import to avoid circular
    count = (
        db.query(func.count(Risk.id))
        .filter(
            Risk.project_id == project_id,
            Risk.status == RiskStatus.open,
            Risk.impact == RiskLevel.high,
        )
        .scalar()
        or 0
    )
    return count > 0


def _compute_health_flag(
    planned: Decimal,
    actual: Decimal,
    utilization_pct: Decimal,
    high_impact_open_risk: bool,
) -> HealthFlag:
    """Apply the health-flag rules documented in the module docstring.

    Priority order (first match wins):
      1. off_track  — actual_spend > planned (over budget; 0-budget + any spend → off_track)
      2. at_risk    — high-impact open risk exists OR utilization_pct >= 80
      3. on_track   — default
    """
    if actual > planned:
        return "off_track"
    if high_impact_open_risk or utilization_pct >= Decimal("80"):
        return "at_risk"
    return "on_track"


def _build_project_dashboard(db: Session, project: Project) -> ProjectDashboardResponse:
    """Compute the full dashboard snapshot for a single project."""
    task_total, task_done, completion_pct = _compute_task_metrics(db, project.id)
    planned, actual, utilization_pct = _compute_budget_metrics(db, project.id)
    open_risk_count = _count_open_risks(db, project.id)
    high_impact_risk = _has_high_impact_open_risk(db, project.id)
    health = _compute_health_flag(planned, actual, utilization_pct, high_impact_risk)

    return ProjectDashboardResponse(
        project_id=project.id,
        project_name=project.name,
        project_status=project.status.value,
        task_total=task_total,
        task_done=task_done,
        task_completion_pct=completion_pct,
        budget_planned=planned,
        budget_actual=actual,
        budget_utilization_pct=utilization_pct,
        open_risk_count=open_risk_count,
        has_high_impact_open_risk=high_impact_risk,
        health_flag=health,
    )


def _build_project_summary(db: Session, project: Project) -> ProjectSummary:
    """Compute the condensed project card for the portfolio dashboard list."""
    planned, actual, utilization_pct = _compute_budget_metrics(db, project.id)
    open_risk_count = _count_open_risks(db, project.id)
    high_impact_risk = _has_high_impact_open_risk(db, project.id)
    health = _compute_health_flag(planned, actual, utilization_pct, high_impact_risk)

    return ProjectSummary(
        project_id=project.id,
        project_name=project.name,
        project_status=project.status.value,
        budget_utilization_pct=utilization_pct,
        open_risk_count=open_risk_count,
        health_flag=health,
    )


# ---------------------------------------------------------------------------
# Public service class
# ---------------------------------------------------------------------------


class DashboardService:
    """Orchestrates permission checks and metric computation for dashboards."""

    @staticmethod
    def get_project_dashboard(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
    ) -> ProjectDashboardResponse:
        """Return the project dashboard for a given project.

        Accessible to any project member or broad manager (org_admin /
        portfolio_manager) within the same organization.
        """
        project = _require_project_in_org(
            db, project_id=project_id, organization_id=caller.organization_id
        )

        if not _caller_can_view_project(db, caller=caller, project_id=project.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You are not a member of this project.",
            )

        return _build_project_dashboard(db, project)

    @staticmethod
    def get_portfolio_dashboard(
        db: Session,
        caller: User,
        portfolio_id: uuid.UUID,
    ) -> PortfolioDashboardResponse:
        """Return the portfolio dashboard with per-project summaries.

        Only org_admin and portfolio_manager can view the portfolio dashboard
        (mvp-requirements.md §10.2 — portfolio-level decision view).

        Projects are listed by name ascending for stable ordering.
        """
        if not _caller_is_broad_manager(caller):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Portfolio dashboard requires org_admin or portfolio_manager role.",
            )

        portfolio = portfolio_repository.get_by_id_within_org(
            db, portfolio_id=portfolio_id, organization_id=caller.organization_id
        )
        if not portfolio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found.",
            )

        # Fetch all active projects in this portfolio (no pagination on
        # portfolio dashboard — PM tools expect to see all projects at once)
        projects, _ = project_repository.list_all_within_org(
            db,
            organization_id=caller.organization_id,
            portfolio_id=portfolio_id,
            limit=1000,
            offset=0,
        )

        summaries = [_build_project_summary(db, p) for p in projects]
        # Sort by project name for stable, predictable ordering
        summaries.sort(key=lambda s: s.project_name.lower())

        return PortfolioDashboardResponse(
            portfolio_id=portfolio.id,
            portfolio_name=portfolio.name,
            project_count=len(summaries),
            projects=summaries,
        )


dashboard_service = DashboardService()
