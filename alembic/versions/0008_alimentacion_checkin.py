"""Agrega columna alimentacion a mp_checkins (escala 1-7).

Registra si la comida previa al entrenamiento fue suficiente.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mp_checkins",
        sa.Column("alimentacion", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mp_checkins", "alimentacion")
