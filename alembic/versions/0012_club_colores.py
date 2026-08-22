"""Agrega color_primario y color_secundario a mp_clubes."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mp_clubes", sa.Column("color_primario", sa.String(7), nullable=True))
    op.add_column("mp_clubes", sa.Column("color_secundario", sa.String(7), nullable=True))

    op.execute("UPDATE mp_clubes SET color_primario='#F5C518', color_secundario='#1A1A1A' WHERE slug='coquimbo'")
    op.execute("UPDATE mp_clubes SET color_primario='#003DA5', color_secundario='#E31E24' WHERE slug='udechile'")


def downgrade() -> None:
    op.drop_column("mp_clubes", "color_secundario")
    op.drop_column("mp_clubes", "color_primario")
