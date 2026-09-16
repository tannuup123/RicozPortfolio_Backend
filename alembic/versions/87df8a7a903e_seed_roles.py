"""seed_roles

Revision ID: 87df8a7a903e
Revises: 1aac2fc70d0a
Create Date: 2026-09-16 16:18:05.876036
"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '87df8a7a903e'
down_revision: Union[str, None] = '1aac2fc70d0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ["org_admin", "portfolio_manager", "project_manager", "team_member"]

def upgrade() -> None:
    roles_table = sa.table(
        'roles',
        sa.column('id', sa.Uuid),
        sa.column('name', sa.String),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime)
    )

    now = datetime.now(timezone.utc)

    op.bulk_insert(
        roles_table,
        [
            {
                'id': uuid.uuid4(),
                'name': role_name,
                'created_at': now,
                'updated_at': now
            }
            for role_name in ROLES
        ]
    )


def downgrade() -> None:
    # Rows are automatically removed when Group 1's downgrade drops the roles
    # table. Attempting to DELETE here is unsafe because the table may already
    # be absent (e.g. when downgrading from base on a fresh test database).
    pass
