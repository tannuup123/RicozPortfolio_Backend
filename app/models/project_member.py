import enum
import uuid

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDMixin


class ProjectMemberRole(str, enum.Enum):
    manager = "manager"
    member = "member"


class ProjectMember(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_role: Mapped[ProjectMemberRole] = mapped_column(
        SQLEnum(ProjectMemberRole, name="projectmemberrole", native_enum=True),
        nullable=False,
        default=ProjectMemberRole.member,
    )
