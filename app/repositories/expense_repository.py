"""Repository for Expense database operations (Phase 9)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Sequence

from sqlalchemy.orm import Session

from app.models.expense import Expense


class ExpenseRepository:
    """Encapsulates database access for Expense model."""

    @staticmethod
    def list_by_project(
        db: Session,
        project_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[Expense], int]:
        """List expenses for a project ordered by date DESC, created_at DESC."""
        base = db.query(Expense).filter(Expense.project_id == project_id)
        total = base.count()
        items = (
            base.order_by(Expense.date.desc(), Expense.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def create(
        db: Session,
        project_id: uuid.UUID,
        amount: Decimal,
        description: str,
        expense_date: date,
    ) -> Expense:
        """Create a new expense record."""
        expense = Expense(
            project_id=project_id,
            amount=amount,
            description=description.strip(),
            date=expense_date,
        )
        db.add(expense)
        db.flush()
        return expense


expense_repository = ExpenseRepository()
