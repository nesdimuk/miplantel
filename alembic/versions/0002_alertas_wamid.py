"""add wamid to alertas_log

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mp_alertas_log", sa.Column("wamid", sa.String(100), nullable=True))
    op.create_index("ix_mp_alertas_log_wamid", "mp_alertas_log", ["wamid"])


def downgrade() -> None:
    op.drop_index("ix_mp_alertas_log_wamid", table_name="mp_alertas_log")
    op.drop_column("mp_alertas_log", "wamid")
