"""Agrega molestia_severidad a checkins y checkouts

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-18
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mp_checkins", sa.Column("molestia_severidad", sa.String(20), nullable=True))
    op.add_column("mp_checkouts", sa.Column("molestia_severidad", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("mp_checkouts", "molestia_severidad")
    op.drop_column("mp_checkins", "molestia_severidad")
