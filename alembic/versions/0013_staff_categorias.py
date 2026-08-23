"""staff: agregar categoria_ids para filtrar alertas por categoría

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    # categoria_ids: null = recibe todas las categorías del club
    op.add_column(
        "mp_staff",
        sa.Column("categoria_ids", ARRAY(sa.Integer()), nullable=True),
    )
    op.add_column(
        "mp_staff",
        sa.Column("es_coordinador", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "mp_staff",
        sa.Column("password_coord", sa.String(64), nullable=True),
    )


def downgrade():
    op.drop_column("mp_staff", "password_coord")
    op.drop_column("mp_staff", "es_coordinador")
    op.drop_column("mp_staff", "categoria_ids")
