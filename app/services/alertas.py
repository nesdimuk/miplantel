import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertaLog, Staff
from app.messaging import get_providers
from app.messaging.base import MessagingProvider, SendResult
from app.messaging.fake import FakeProvider
from app.messaging.telegram_provider import TelegramProvider
from app.messaging.templates import render

logger = logging.getLogger("services.alertas")

RETRY_DELAYS = [1.0, 2.0]
MAX_ATTEMPTS = 3


def _resolve_to(provider: MessagingProvider, staff: Staff) -> str | None:
    """Return the address string for this provider, or None if the staff member
    is not reachable via this channel (e.g. Telegram not linked yet)."""
    if isinstance(provider, TelegramProvider):
        if staff.telegram_chat_id:
            return str(staff.telegram_chat_id)
        logger.debug("Staff %s (%s) sin telegram_chat_id — omitido en Telegram", staff.id, staff.nombre)
        return None
    # WhatsAppCloudProvider and FakeProvider both use phone number
    return staff.telefono_whatsapp


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
    """Send a template to every opted-in staff member via all active providers."""
    flag = Staff.recibe_alertas if canal == "alertas" else Staff.recibe_resumen
    result = await db.execute(
        select(Staff).where(
            Staff.club_id == club_id,
            flag == True,  # noqa: E712
            Staff.activo == True,  # noqa: E712
        )
    )
    todos = result.scalars().all()
    destinatarios = [
        s for s in todos
        if s.categoria_ids is None or categoria_id in s.categoria_ids
    ]
    if not destinatarios:
        logger.warning("Alerta %s sin destinatarios (club_id=%s)", tipo, club_id)
        return

    mensaje = render(template, variables)
    providers = get_providers()

    for staff in destinatarios:
        for provider in providers:
            to = _resolve_to(provider, staff)
            if to is None:
                continue
            send = await _send_with_retry(provider, to, template, variables)
            # Log once per (staff, provider) send attempt
            canal_log = "telegram" if isinstance(provider, TelegramProvider) else "whatsapp"
            db.add(AlertaLog(
                tipo=tipo,
                categoria_id=categoria_id,
                jugador_id=jugador_id,
                destinatario=f"{canal_log}:{to}",
                mensaje=mensaje,
                estado_envio="sent" if send.ok else "failed",
                respuesta_api=send.response,
                wamid=send.message_id,
            ))
    await db.flush()


async def _send_with_retry(
    provider: MessagingProvider, to: str, template: str, variables: list[str]
) -> SendResult:
    result: SendResult = SendResult(ok=False, message_id=None, response="not_attempted")
    for attempt in range(MAX_ATTEMPTS):
        result = await provider.send_template(to, template, variables)
        if result.ok:
            return result
        if attempt < MAX_ATTEMPTS - 1:
            await asyncio.sleep(RETRY_DELAYS[attempt])
            logger.warning(
                "Reintentando envío a %s via %s (intento %d/%d)",
                to, type(provider).__name__, attempt + 2, MAX_ATTEMPTS,
            )
    logger.error(
        "Envío a %s via %s falló tras %d intentos: %s",
        to, type(provider).__name__, MAX_ATTEMPTS, result.response,
    )
    return result
