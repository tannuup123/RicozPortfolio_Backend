"""Pydantic response schemas for Dashboard endpoints (Phase 10)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

HealthFlag = Literal["on_track", "at_risk", "off_track"]


class ProjectDashboardResponse(BaseModel):
    """Computed snapshot for a single project dashboard.

    All numeric values are calculated live from the underlying data tables;
    they are never cached or stored.
    """

    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    project_name: str
    project_status: str

    # Task completion
    task_total: int
    task_done: int
    task_completion_pct: Decimal  # 0.00–100.00; 0 when no tasks

    # Budget utilization
    budget_planned: Decimal   # 0.00 when no budget row exists
    budget_actual: Decimal    # SUM(expenses.amount), always >= 0
    budget_utilization_pct: Decimal  # 0.00 when planned == 0 (zero-budget rule)

    # Risk
    open_risk_count: int
    has_high_impact_open_risk: bool

    # Composite
    health_flag: HealthFlag


class ProjectSummary(BaseModel):
    """Condensed project card used in the portfolio dashboard list."""

    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    project_name: str
    project_status: str
    budget_utilization_pct: Decimal
    open_risk_count: int
    health_flag: HealthFlag


class PortfolioDashboardResponse(BaseModel):
    """Aggregated dashboard for a portfolio.

    Contains a sortable/filterable list of per-project summaries
    (mvp-requirements.md §6.2).
    """

    model_config = ConfigDict(from_attributes=True)

    portfolio_id: UUID
    portfolio_name: str
    project_count: int
    projects: list[ProjectSummary]
