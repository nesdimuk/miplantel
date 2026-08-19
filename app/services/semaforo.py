import logging
from datetime import date
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Categoria, Checkin, Jugador, SesionDia
from app.services.alertas import enviar_a_staff

logger = logging.getLogger("services.semaforo")

# Wellness score = (sueño + energía + ánimo + dolor invertido) / 4, escala 1-7
ESTADOS = [
    (5.5, "🟢 VERDE"),
    (4.5, "🟡 AMARILLO"),
    (3.5, "🟠 NARANJA"),
    (0.0, "🔴 ROJO"),
]


async def calcular_semaforo(db: AsyncSession, categoria_id: int, fecha: date) -> Optional[dict]:
    """Compute squad wellness averages from today's check-ins. None if no data."""
    result = await db.execute(
        select(
            func.count(Checkin.id),
            func.avg(Checkin.sueno),
            func.avg(Checkin.energia),
            func.avg(Checkin.animo),
            func.avg(Checkin.dolor_pre),
        )
        .join(Jugador, Checkin.jugador_id == Jugador.id)
        .where(
            Jugador.categoria_id == categoria_id,
            Checkin.fecha == fecha,
            Checkin.asistencia == True,  # noqa: E712
        )
    )
    count, sueno, energia, animo, dolor = result.one()
    if not count:
        return None

    sueno, energia, animo, dolor = float(sueno), float(energia), float(animo), float(dolor)
    bienestar = (sueno + energia + animo + (8 - dolor)) / 4
    estado = next(nombre for umbral, nombre in ESTADOS if bienestar >= umbral)

    return {
        "checkins": count,
        "sueno": round(sueno, 1),
        "energia": round(energia, 1),
        "animo": round(animo, 1),
        "dolor": round(dolor, 1),
        "bienestar": round(bienestar, 2),
        "estado": estado,
    }


async def enviar_semaforo(
    db: AsyncSession,
    categoria: Categoria,
    fecha: date,
    forzado: bool = False,
) -> bool:
    """Send the squad wellness traffic light to staff, exactly once per day.

    Returns True if this call performed the send.
    """
    stats = await calcular_semaforo(db, categoria.id, fecha)
    if stats is None:
        logger.debug("Semáforo %s %s: sin datos, se omite", categoria.nombre, fecha)
        return False

    if not forzado and stats["checkins"] < categoria.min_checkins_semaforo:
        return False

    if not await _claim_semaforo(db, categoria.id, fecha):
        return False  # already sent (or being sent by a concurrent request)

    variables = [
        categoria.nombre,
        fecha.strftime("%d/%m/%Y"),
        stats["estado"],
        str(stats["checkins"]),
        str(stats["sueno"]),
        str(stats["energia"]),
        str(stats["animo"]),
        str(stats["dolor"]),
    ]
    await enviar_a_staff(
        db,
        club_id=categoria.club_id,
        tipo="semaforo",
        categoria_id=categoria.id,
        jugador_id=None,
        template="semaforo_diario",
        variables=variables,
    )
    logger.info("Semáforo enviado: %s %s → %s", categoria.nombre, fecha, stats["estado"])
    return True


async def _claim_semaforo(db: AsyncSession, categoria_id: int, fecha: date) -> bool:
    """Atomically claim the daily send. Ensures the sesion row exists first."""
    await db.execute(
        pg_insert(SesionDia)
        .values(categoria_id=categoria_id, fecha=fecha)
        .on_conflict_do_nothing(constraint="mp_uq_sesion_categoria_fecha")
    )
    result = await db.execute(
        update(SesionDia)
        .where(
            SesionDia.categoria_id == categoria_id,
            SesionDia.fecha == fecha,
            SesionDia.semaforo_enviado == False,  # noqa: E712
        )
        .values(semaforo_enviado=True)
        .returning(SesionDia.id)
    )
    return result.scalar_one_or_none() is not None
