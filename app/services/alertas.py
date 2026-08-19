import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertaLog, Categoria, Checkin, Checkout, Jugador, Staff
from app.messaging import get_provider
from app.messaging.base import SendResult
from app.messaging.templates import render

logger = logging.getLogger("services.alertas")

# Delays (seconds) before 2nd and 3rd attempt. Patched to zeros in tests.
RETRY_DELAYS = [1.0, 2.0]
MAX_ATTEMPTS = 3


async def notificar_molestia(
    db: AsyncSession,
    jugador: Jugador,
    zona: Optional[str],
    contexto: str,  # "check-in" | "check-out"
    fecha: date,
) -> None:
    """Immediate alert to staff when a player reports a physical issue."""
    categoria = await db.get(Categoria, jugador.categoria_id)
    variables = [
        categoria.nombre,
        f"{jugador.nombre} {jugador.apellido}",
        zona or "zona no indicada",
        contexto,
    ]
    await enviar_a_staff(
        db,
        club_id=categoria.club_id,
        tipo="molestia",
        categoria_id=categoria.id,
        jugador_id=jugador.id,
        template="alerta_molestia",
        variables=variables,
    )


async def notificar_inasistencia(
    db: AsyncSession,
    jugador: Jugador,
    motivo: str,
    fecha: date,
) -> None:
    """Immediate alert to staff when a player reports absence."""
    categoria = await db.get(Categoria, jugador.categoria_id)
    variables = [
        categoria.nombre,
        f"{jugador.nombre} {jugador.apellido}",
        motivo,
    ]
    await enviar_a_staff(
        db,
        club_id=categoria.club_id,
        tipo="inasistencia",
        categoria_id=categoria.id,
        jugador_id=jugador.id,
        template="alerta_inasistencia",
        variables=variables,
    )


async def revisar_tendencia_molestia(
    db: AsyncSession,
    jugador: Jugador,
    zona: Optional[str],
    fecha: date,
    umbral: int = 3,
    ventana_dias: int = 14,
) -> None:
    """Alert staff if the same player has reported a molestia ≥ umbral times in the last ventana_dias days.
    Fires at most once per 7 days per player to avoid spam."""
    desde = fecha - timedelta(days=ventana_dias)

    ci_count = (await db.execute(
        select(func.count(Checkin.id)).where(
            Checkin.jugador_id == jugador.id,
            Checkin.molestia_previa == True,  # noqa: E712
            Checkin.fecha >= desde,
        )
    )).scalar_one()

    co_count = (await db.execute(
        select(func.count(Checkout.id)).where(
            Checkout.jugador_id == jugador.id,
            Checkout.molestia_nueva == True,  # noqa: E712
            Checkout.fecha >= desde,
        )
    )).scalar_one()

    if ci_count + co_count < umbral:
        return

    # Throttle: max one tendencia alert per player per 7 days
    hace_7 = datetime.utcnow() - timedelta(days=7)
    ya_enviado = (await db.execute(
        select(AlertaLog.id).where(
            AlertaLog.jugador_id == jugador.id,
            AlertaLog.tipo == "tendencia_molestia",
            AlertaLog.created_at >= hace_7,
        )
    )).scalar_one_or_none()
    if ya_enviado:
        return

    categoria = await db.get(Categoria, jugador.categoria_id)
    variables = [
        categoria.nombre,
        f"{jugador.nombre} {jugador.apellido}",
        str(ci_count + co_count),
        zona or "zona no indicada",
    ]
    await enviar_a_staff(
        db,
        club_id=categoria.club_id,
        tipo="tendencia_molestia",
        categoria_id=categoria.id,
        jugador_id=jugador.id,
        template="alerta_tendencia_molestia",
        variables=variables,
    )


async def enviar_a_staff(
    db: AsyncSession,
    club_id: int,
    tipo: str,
    categoria_id: int,
    jugador_id: Optional[int],
    template: str,
    variables: list[str],
    canal: str = "alertas",  # "alertas" → recibe_alertas | "resumen" → recibe_resumen
) -> None:
    """Send a template to every opted-in staff member, logging each send."""
    flag = Staff.recibe_alertas if canal == "alertas" else Staff.recibe_resumen
    result = await db.execute(
        select(Staff).where(
            Staff.club_id == club_id,
            flag == True,  # noqa: E712
            Staff.activo == True,  # noqa: E712
        )
    )
    destinatarios = result.scalars().all()
    if not destinatarios:
        logger.warning("Alerta %s sin destinatarios (club_id=%s)", tipo, club_id)
        return

    mensaje = render(template, variables)
    for staff in destinatarios:
        send = await _send_with_retry(staff.telefono_whatsapp, template, variables)
        db.add(AlertaLog(
            tipo=tipo,
            categoria_id=categoria_id,
            jugador_id=jugador_id,
            destinatario=staff.telefono_whatsapp,
            mensaje=mensaje,
            estado_envio="sent" if send.ok else "failed",
            respuesta_api=send.response,
            wamid=send.message_id,
        ))
    await db.flush()


async def _send_with_retry(to: str, template: str, variables: list[str]) -> SendResult:
    provider = get_provider()
    result: SendResult = SendResult(ok=False, message_id=None, response="not_attempted")
    for attempt in range(MAX_ATTEMPTS):
        result = await provider.send_template(to, template, variables)
        if result.ok:
            return result
        if attempt < MAX_ATTEMPTS - 1:
            await asyncio.sleep(RETRY_DELAYS[attempt])
            logger.warning("Reintentando envío a %s (intento %d/%d)", to, attempt + 2, MAX_ATTEMPTS)
    logger.error("Envío a %s falló tras %d intentos: %s", to, MAX_ATTEMPTS, result.response)
    return result
