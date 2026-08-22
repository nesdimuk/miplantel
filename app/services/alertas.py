import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertaLog, Staff
from app.messaging import get_provider
from app.messaging.base import SendResult
from app.messaging.templates import render

logger = logging.getLogger("services.alertas")

RETRY_DELAYS = [1.0, 2.0]
MAX_ATTEMPTS = 3


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
