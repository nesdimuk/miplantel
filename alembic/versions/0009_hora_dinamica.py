"""Agrega hora_inicio_declarada en checkins y hora_termino en checkouts.

Permite calcular duración individual y disparar el semáforo dinámicamente.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mp_checkins",
        sa.Column("hora_inicio_declarada", sa.String(5), nullable=True),
    )
    op.add_column(
        "mp_checkouts",
        sa.Column("hora_termino", sa.String(5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mp_checkins", "hora_inicio_declarada")
    op.drop_column("mp_checkouts", "hora_termino")
