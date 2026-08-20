import logging
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertaLog, Categoria, Checkin, Jugador
from app.services import carga as carga_svc
from app.services.alertas import enviar_a_staff

logger = logging.getLogger("services.bienestar")

UMBRAL_ROJO = 3.5        # bienestar score below this triggers immediate alert
UMBRAL_BIENESTAR = 2.0   # avg ≤ 2 on a 1-7 scale triggers trend alert
REGISTROS_BIENESTAR = 3  # over the player's last N attendance check-ins


async def revisar_bienestar(db: AsyncSession, jugador: Jugador, fecha: date) -> bool:
    """Alert staff when a player's today bienestar is ROJO, or trend is critically low."""
    checkin_hoy = (await db.execute(
        select(Checkin)
        .where(
            Checkin.jugador_id == jugador.id,
            Checkin.fecha == fecha,
            Checkin.asistencia == True,  # noqa: E712
        )
    )).scalar_one_or_none()

    if checkin_hoy and all(
        getattr(checkin_hoy, f) is not None
        for f in ("sueno", "energia", "animo", "dolor_pre")
    ):
        bienestar = (
            checkin_hoy.sueno + checkin_hoy.energia + checkin_hoy.animo
            + (8 - checkin_hoy.dolor_pre)
        ) / 4
        if bienestar < UMBRAL_ROJO and not await _ya_alertado_hoy(db, "bienestar_rojo", jugador.id, fecha):
            categoria = await db.get(Categoria, jugador.categoria_id)
            await enviar_a_staff(
                db,
                club_id=categoria.club_id,
                tipo="bienestar_rojo",
                categoria_id=categoria.id,
                jugador_id=jugador.id,
                template="alerta_bienestar_rojo",
                variables=[
                    categoria.nombre,
                    f"{jugador.nombre} {jugador.apellido}",
                    str(checkin_hoy.sueno),
                    str(checkin_hoy.energia),
                    str(checkin_hoy.animo),
                    str(checkin_hoy.dolor_pre),
                ],
            )
            logger.info("Alerta bienestar ROJO: jugador=%s bienestar=%.2f", jugador.id, bienestar)
            return True

    # Trend alert: last N check-ins with critically low sleep or mood
    ultimos = (await db.execute(
        select(Checkin.sueno, Checkin.animo)
        .where(Checkin.jugador_id == jugador.id, Checkin.asistencia == True)  # noqa: E712
        .order_by(Checkin.fecha.desc())
        .limit(REGISTROS_BIENESTAR)
    )).all()
    if len(ultimos) < REGISTROS_BIENESTAR:
        return False

    avg_sueno = sum(r.sueno for r in ultimos) / len(ultimos)
    avg_animo = sum(r.animo for r in ultimos) / len(ultimos)

    if avg_sueno <= UMBRAL_BIENESTAR:
        metrica, valor = "sueño", avg_sueno
    elif avg_animo <= UMBRAL_BIENESTAR:
        metrica, valor = "ánimo", avg_animo
    else:
        return False

    if await _ya_alertado_hoy(db, "bienestar", jugador.id, fecha):
        return False

    categoria = await db.get(Categoria, jugador.categoria_id)
    await enviar_a_staff(
        db,
        club_id=categoria.club_id,
        tipo="bienestar",
        categoria_id=categoria.id,
        jugador_id=jugador.id,
        template="alerta_bienestar",
        variables=[
            categoria.nombre,
            f"{jugador.nombre} {jugador.apellido}",
            f"{metrica} (promedio {valor:.1f})",
            str(REGISTROS_BIENESTAR),
        ],
    )
    logger.info("Alerta bienestar tendencia: jugador=%s %s=%.1f", jugador.id, metrica, valor)
    return True


async def revisar_carga(db: AsyncSession, jugador: Jugador, fecha: date) -> bool:
    """Alert staff when a player's 7-day load exceeds the category threshold. Max one per day."""
    categoria = await db.get(Categoria, jugador.categoria_id)
    aguda = await carga_svc.carga_aguda(db, jugador.id, fecha)
    if aguda <= categoria.umbral_alerta_carga:
        return False

    if await _ya_alertado_hoy(db, "carga_alta", jugador.id, fecha):
        return False

    await enviar_a_staff(
        db,
        club_id=categoria.club_id,
        tipo="carga_alta",
        categoria_id=categoria.id,
        jugador_id=jugador.id,
        template="alerta_carga",
        variables=[
            categoria.nombre,
            f"{jugador.nombre} {jugador.apellido}",
            str(aguda),
            str(categoria.umbral_alerta_carga),
        ],
    )
    logger.info("Alerta carga alta: jugador=%s carga=%d", jugador.id, aguda)
    return True


async def _ya_alertado_hoy(db: AsyncSession, tipo: str, jugador_id: int, fecha: date) -> bool:
    result = await db.execute(
        select(AlertaLog.id).where(
            AlertaLog.tipo == tipo,
            AlertaLog.jugador_id == jugador_id,
            func.date(AlertaLog.created_at) == fecha,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None
