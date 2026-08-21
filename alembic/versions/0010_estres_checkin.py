"""Agrega columna estres a mp_checkins (Hooper Index).

Captura nivel de estrés 1-7 donde 1=sin estrés, 7=muy estresado.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mp_checkins",
        sa.Column("estres", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mp_checkins", "estres")
