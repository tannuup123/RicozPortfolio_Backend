import os


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

mixins_py = """import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import DateTime, Uuid, ForeignKey

class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class TenantMixin:
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)

class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
"""

org_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin

class Organization(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
"""

user_py = """from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, ForeignKey, Table, Column
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin, TenantMixin
import uuid

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

class User(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    roles = relationship("Role", secondary=user_roles)
"""

role_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin

class Role(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
"""

goal_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin, TenantMixin

class StrategicGoal(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "strategic_goals"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
"""

idea_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, ForeignKey, Enum as SQLEnum
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin, TenantMixin, SoftDeleteMixin
import enum
import uuid

class IdeaStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"

class Idea(Base, UUIDMixin, TenantMixin, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "ideas"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[IdeaStatus] = mapped_column(SQLEnum(IdeaStatus, native_enum=True), default=IdeaStatus.draft, nullable=False)

    strategic_goal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("strategic_goals.id", ondelete="SET NULL"), nullable=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
"""

bcase_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Numeric, ForeignKey
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
import uuid

class BusinessCase(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "business_cases"
    idea_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ideas.id", ondelete="CASCADE"), unique=True, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    estimated_benefit: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    roi: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
"""

approval_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, ForeignKey, Enum as SQLEnum
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
import enum
import uuid

class ApprovalStatus(str, enum.Enum):
    approved = "approved"
    rejected = "rejected"

class Approval(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "approvals"
    idea_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False)
    approver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(SQLEnum(ApprovalStatus, native_enum=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
"""

portfolio_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin, TenantMixin, SoftDeleteMixin

class Portfolio(Base, UUIDMixin, TenantMixin, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "portfolios"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
"""

project_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, ForeignKey, Enum as SQLEnum
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin, TenantMixin, SoftDeleteMixin
import enum
import uuid

class ProjectStatus(str, enum.Enum):
    planned = "planned"
    active = "active"
    on_hold = "on_hold"
    completed = "completed"
    cancelled = "cancelled"

class Project(Base, UUIDMixin, TenantMixin, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(SQLEnum(ProjectStatus, native_enum=True), default=ProjectStatus.planned, nullable=False)

    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True)
    source_idea_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ideas.id", ondelete="SET NULL"), unique=True, nullable=True)
"""

pmember_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey
from app.db.base import Base
from app.models.mixins import TimestampMixin
import uuid

class ProjectMember(Base, TimestampMixin):
    __tablename__ = "project_members"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
"""

task_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, ForeignKey, Enum as SQLEnum
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
import enum
import uuid

class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"

class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"

class Task(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tasks"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(SQLEnum(TaskStatus, native_enum=True), default=TaskStatus.todo, nullable=False)
    priority: Mapped[TaskPriority] = mapped_column(SQLEnum(TaskPriority, native_enum=True), default=TaskPriority.medium, nullable=False)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
"""

milestone_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, Date, ForeignKey, Enum as SQLEnum
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
from datetime import date
import enum
import uuid

class MilestoneStatus(str, enum.Enum):
    pending = "pending"
    achieved = "achieved"
    missed = "missed"

class Milestone(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "milestones"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[MilestoneStatus] = mapped_column(SQLEnum(MilestoneStatus, native_enum=True), default=MilestoneStatus.pending, nullable=False)
"""

risk_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, ForeignKey, Enum as SQLEnum
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
import enum
import uuid

class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"

class RiskStatus(str, enum.Enum):
    open = "open"
    mitigated = "mitigated"
    closed = "closed"

class Risk(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "risks"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    probability: Mapped[RiskLevel] = mapped_column(SQLEnum(RiskLevel, name="risk_probability_enum", native_enum=True), default=RiskLevel.medium, nullable=False)
    impact: Mapped[RiskLevel] = mapped_column(SQLEnum(RiskLevel, name="risk_impact_enum", native_enum=True), default=RiskLevel.medium, nullable=False)
    status: Mapped[RiskStatus] = mapped_column(SQLEnum(RiskStatus, native_enum=True), default=RiskStatus.open, nullable=False)
"""

budget_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Numeric, ForeignKey
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
import uuid

class ProjectBudget(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "project_budgets"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
"""

expense_py = """from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Numeric, Date, ForeignKey
from app.db.base import Base
from app.models.mixins import UUIDMixin, TimestampMixin
from datetime import date
import uuid

class Expense(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "expenses"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
"""

write_file("app/models/mixins.py", mixins_py)
write_file("app/models/organization.py", org_py)
write_file("app/models/user.py", user_py)
write_file("app/models/role.py", role_py)
write_file("app/models/strategic_goal.py", goal_py)
write_file("app/models/idea.py", idea_py)
write_file("app/models/business_case.py", bcase_py)
write_file("app/models/approval.py", approval_py)
write_file("app/models/portfolio.py", portfolio_py)
write_file("app/models/project.py", project_py)
write_file("app/models/project_member.py", pmember_py)
write_file("app/models/task.py", task_py)
write_file("app/models/milestone.py", milestone_py)
write_file("app/models/risk.py", risk_py)
write_file("app/models/budget.py", budget_py)
write_file("app/models/expense.py", expense_py)

print("Generated all model files.")
