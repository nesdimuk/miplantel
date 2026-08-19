"""self-service registration: club email + admin password

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mp_clubes", sa.Column("email", sa.String(120), nullable=True))
    op.add_column("mp_clubes", sa.Column("password_admin", sa.String(64), nullable=True))  # sha256 hex
    op.create_index("ix_mp_clubes_email", "mp_clubes", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_mp_clubes_email", table_name="mp_clubes")
    op.drop_column("mp_clubes", "password_admin")
    op.drop_column("mp_clubes", "email")
