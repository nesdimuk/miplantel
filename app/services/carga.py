"""Training load metrics: acute load, chronic load and ACWR.

ACWR (acute:chronic workload ratio) is computed but not yet used for
alerting — reserved for a later phase. The weekly-load alert uses
carga_aguda against the category's configurable threshold.
"""
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Checkout


async def carga_aguda(db: AsyncSession, jugador_id: int, fecha: date) -> int:
    """Sum of load over the last 7 days (inclusive of `fecha`)."""
    result = await db.execute(
        select(func.coalesce(func.sum(Checkout.carga), 0)).where(
            Checkout.jugador_id == jugador_id,
            Checkout.fecha > fecha - timedelta(days=7),
            Checkout.fecha <= fecha,
        )
    )
    return result.scalar_one()


async def carga_cronica(db: AsyncSession, jugador_id: int, fecha: date) -> float:
    """Mean weekly load over the last 28 days (4 rolling 7-day blocks)."""
    total = (await db.execute(
        select(func.coalesce(func.sum(Checkout.carga), 0)).where(
            Checkout.jugador_id == jugador_id,
            Checkout.fecha > fecha - timedelta(days=28),
            Checkout.fecha <= fecha,
        )
    )).scalar_one()
    return total / 4


# Minimum history for a meaningful chronic base — otherwise every first
# session yields ACWR = 4.0 (aguda / (aguda/4)), a cold-start false positive.
MIN_SESIONES_CRONICA = 4
MIN_ANTIGUEDAD_DIAS = 7  # at least one session older than the acute window


async def calcular_acwr(db: AsyncSession, jugador_id: int, fecha: date) -> Optional[float]:
    """Acute:chronic ratio. None until the player has enough history to compare against."""
    historial = (await db.execute(
        select(func.count(Checkout.id), func.min(Checkout.fecha)).where(
            Checkout.jugador_id == jugador_id,
            Checkout.fecha > fecha - timedelta(days=28),
            Checkout.fecha <= fecha,
        )
    )).one()
    n_sesiones, primera_fecha = historial
    if n_sesiones < MIN_SESIONES_CRONICA or primera_fecha > fecha - timedelta(days=MIN_ANTIGUEDAD_DIAS):
        return None

    cronica = await carga_cronica(db, jugador_id, fecha)
    if cronica == 0:
        return None
    aguda = await carga_aguda(db, jugador_id, fecha)
    return round(aguda / cronica, 2)
