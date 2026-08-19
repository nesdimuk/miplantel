import logging
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Categoria, Recordatorio, SesionDia
from app.services.alertas import enviar_a_staff

logger = logging.getLogger("services.recordatorios")


def hora_objetivo(rec: Recordatorio, categoria: Categoria) -> str:
    """HH:MM at which this reminder becomes due. Fixed hour wins over relative."""
    if rec.hora:
        return rec.hora
    minutos = _a_minutos(categoria.hora_inicio) - (rec.minutos_antes or 0)
    minutos = max(minutos, 0)
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


async def evaluar_recordatorios(
    db: AsyncSession,
    categoria: Categoria,
    fecha: date,
    hhmm_actual: str,
) -> int:
    """Send every due reminder for the category. Returns how many were sent.

    Each reminder fires at most once per day (claimed via last_enviado).
    If condicion_min_checkins is set, it only sends while check-ins < N;
    when the condition is not met, the day is claimed silently.
    """
    result = await db.execute(
        select(Recordatorio).where(
            Recordatorio.categoria_id == categoria.id,
            Recordatorio.activo == True,  # noqa: E712
        )
    )
    enviados = 0
    for rec in result.scalars().all():
        if hhmm_actual < hora_objetivo(rec, categoria):
            continue
        if not await _claim(db, rec.id, fecha):
            continue

        checkins = await _checkins_del_dia(db, categoria.id, fecha)
        if rec.condicion_min_checkins is not None and checkins >= rec.condicion_min_checkins:
            logger.info("Recordatorio %s: condición no cumplida (%d check-ins), se omite", rec.id, checkins)
            continue

        await enviar_a_staff(
            db,
            club_id=categoria.club_id,
            tipo="recordatorio",
            categoria_id=categoria.id,
            jugador_id=None,
            template="recordatorio_checkin",
            variables=[categoria.nombre, rec.mensaje, str(checkins)],
        )
        logger.info("Recordatorio enviado: %s (%s)", rec.nombre, categoria.nombre)
        enviados += 1
    return enviados


async def _claim(db: AsyncSession, recordatorio_id: int, fecha: date) -> bool:
    """Atomically claim today's send for this reminder."""
    result = await db.execute(
        update(Recordatorio)
        .where(
            Recordatorio.id == recordatorio_id,
            (Recordatorio.last_enviado.is_(None)) | (Recordatorio.last_enviado < fecha),
        )
        .values(last_enviado=fecha)
        .returning(Recordatorio.id)
    )
    return result.scalar_one_or_none() is not None


async def _checkins_del_dia(db: AsyncSession, categoria_id: int, fecha: date) -> int:
    result = await db.execute(
        select(SesionDia.total_checkins).where(
            SesionDia.categoria_id == categoria_id,
            SesionDia.fecha == fecha,
        )
    )
    return result.scalar_one_or_none() or 0


def _a_minutos(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])
