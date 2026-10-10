"""Repository for ProjectBudget database operations (Phase 9)."""

import uuid
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.budget import ProjectBudget
from app.models.expense import Expense


class BudgetRepository:
    """Encapsulates database access for ProjectBudget model."""

    @staticmethod
    def get_by_project_id(db: Session, project_id: uuid.UUID) -> ProjectBudget | None:
        """Retrieve the project's budget record, or None if not yet set."""
        return (
            db.query(ProjectBudget)
            .filter(ProjectBudget.project_id == project_id)
            .first()
        )

    @staticmethod
    def create(
        db: Session,
        project_id: uuid.UUID,
        amount: Decimal,
        currency: str,
    ) -> ProjectBudget:
        """Create a new budget record for a project."""
        budget = ProjectBudget(
            project_id=project_id,
            amount=amount,
            currency=currency.upper(),
        )
        db.add(budget)
        db.flush()
        return budget

    @staticmethod
    def update(
        db: Session,
        budget: ProjectBudget,
        amount: Decimal,
        currency: str,
    ) -> ProjectBudget:
        """Update an existing budget record."""
        budget.amount = amount
        budget.currency = currency.upper()
        db.flush()
        return budget

    @staticmethod
    def get_actual_spend(db: Session, project_id: uuid.UUID) -> Decimal:
        """Compute actual spend as SUM(expenses.amount) for the project.

        Returns Decimal(\"0.00\") if no expenses exist.
        Uses database-side aggregation to avoid floating-point rounding.
        """
        result = (
            db.query(func.sum(Expense.amount))
            .filter(Expense.project_id == project_id)
            .scalar()
        )
        return result if result is not None else Decimal("0.00")


budget_repository = BudgetRepository()
