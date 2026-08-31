"""Create the ServiceOps MVP schema.

Revision ID: 20260831_0001
Revises:
Create Date: 2026-08-31
"""

from alembic import op
from serviceops import models  # noqa: F401
from serviceops.database import Base

revision = "20260831_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
