"""Recalibra el umbral de alerta de carga: 800 → 3500.

El default original (800 pts/semana) disparaba "carga alta" para casi cualquier
plantel (4 sesiones × 120 min × RPE 6 ≈ 2.880), matando la señal por ruido.
Solo se actualizan categorías que siguen en el default viejo — un valor
distinto de 800 fue elegido a mano y se respeta.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE mp_categorias SET umbral_alerta_carga = 3500 WHERE umbral_alerta_carga = 800")


def downgrade() -> None:
    op.execute("UPDATE mp_categorias SET umbral_alerta_carga = 800 WHERE umbral_alerta_carga = 3500")
