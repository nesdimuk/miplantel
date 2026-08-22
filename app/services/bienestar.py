import logging
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AlertaLog, Categoria, Checkin, Jugador, SesionDia
from app.services.alertas import enviar_a_staff

logger = logging.getLogger("services.bienestar")

UMBRAL_ROJO = 3.5


async def revisar_bienestar(db: AsyncSession, jugador: Jugador, fecha: date) -> bool:
    """Alert staff only when a player's check-in is ROJO and arrives after the semáforo was sent (tardío)."""
    checkin_hoy = (await db.execute(
        select(Checkin)
        .where(
            Checkin.jugador_id == jugador.id,
            Checkin.fecha == fecha,
            Checkin.asistencia == True,  # noqa: E712
        )
    )).scalar_one_or_none()

    if not checkin_hoy or any(
        getattr(checkin_hoy, f) is None
        for f in ("sueno", "energia", "dolor_pre", "estres")
    ):
        return False

    bienestar = (
        checkin_hoy.sueno + checkin_hoy.energia
        + (8 - checkin_hoy.dolor_pre) + (8 - checkin_hoy.estres)
    ) / 4

    if bienestar >= UMBRAL_ROJO:
        return False

    categoria = await db.get(Categoria, jugador.categoria_id)
    semaforo_enviado = (await db.execute(
        select(SesionDia.semaforo_enviado).where(
            SesionDia.categoria_id == categoria.id,
            SesionDia.fecha == fecha,
        )
    )).scalar_one_or_none()

    # Solo enviar WhatsApp si es tardío (semáforo ya fue enviado)
    if not semaforo_enviado:
        return False

    if await _ya_alertado_hoy(db, "bienestar_rojo_tardio", jugador.id, fecha):
        return False

    link = (
        f"{settings.base_url.rstrip('/')}/r/{categoria.id}/{fecha.isoformat()}"
        if settings.base_url else f"/r/{categoria.id}/{fecha.isoformat()}"
    )
    await enviar_a_staff(
        db,
        club_id=categoria.club_id,
        tipo="bienestar_rojo_tardio",
        categoria_id=categoria.id,
        jugador_id=jugador.id,
        template="alerta_bienestar_rojo_tardio",
        variables=[categoria.nombre, link],
    )
    logger.info("Alerta bienestar ROJO tardío: jugador=%s bienestar=%.2f", jugador.id, bienestar)
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
