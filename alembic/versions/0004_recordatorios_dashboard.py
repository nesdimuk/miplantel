"""recordatorios table + club dashboard password

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mp_clubes", sa.Column("password_dashboard", sa.String(64), nullable=True))  # sha256 hex

    op.create_table(
        "mp_recordatorios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("categoria_id", sa.Integer(), sa.ForeignKey("mp_categorias.id"), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("hora", sa.String(5), nullable=True),            # fixed HH:MM, or…
        sa.Column("minutos_antes", sa.Integer(), nullable=True),   # …relative to hora_inicio
        sa.Column("condicion_min_checkins", sa.Integer(), nullable=True),  # send only if checkins < N
        sa.Column("mensaje", sa.String(500), nullable=False),
        sa.Column("last_enviado", sa.Date(), nullable=True),       # daily claim
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_mp_recordatorios_categoria_id", "mp_recordatorios", ["categoria_id"])


def downgrade() -> None:
    op.drop_table("mp_recordatorios")
    op.drop_column("mp_clubes", "password_dashboard")
