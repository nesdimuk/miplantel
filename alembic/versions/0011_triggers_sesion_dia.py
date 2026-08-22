"""Agrega campos de control de triggers basados en comportamiento a mp_sesiones_dia."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mp_sesiones_dia", sa.Column("primer_aviso_enviado", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("mp_sesiones_dia", sa.Column("tercer_checkout_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mp_sesiones_dia", sa.Column("resumen_post_enviado", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("mp_sesiones_dia", sa.Column("dashboard_enviado", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("mp_sesiones_dia", "dashboard_enviado")
    op.drop_column("mp_sesiones_dia", "resumen_post_enviado")
    op.drop_column("mp_sesiones_dia", "tercer_checkout_at")
    op.drop_column("mp_sesiones_dia", "primer_aviso_enviado")
