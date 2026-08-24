import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.db.models import AlertaLog, Staff, Categoria, Club
from app.services.horarios_bot import parsear_horario, enviar_texto_whatsapp

router = APIRouter()
logger = logging.getLogger("api.webhooks")

# Meta status progression; never downgrade (e.g. a late "delivered" after "read")
_STATUS_RANK = {"pending": 0, "failed": 1, "sent": 2, "delivered": 3, "read": 4}


@router.get("/webhooks/whatsapp")
async def verify_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """Meta webhook verification handshake."""
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(403, "Token de verificación inválido")


@router.post("/webhooks/whatsapp")
async def receive_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive delivery statuses and incoming messages from Meta WhatsApp Cloud API."""
    body = await request.json()

    # Process delivery status updates
    statuses = _extract_statuses(body)
    for st in statuses:
        wamid = st.get("id")
        status = st.get("status")
        if not wamid or status not in _STATUS_RANK:
            continue

        result = await db.execute(select(AlertaLog).where(AlertaLog.wamid == wamid))
        alerta = result.scalar_one_or_none()
        if alerta is None:
            logger.warning("Status para wamid desconocido: %s (%s)", wamid, status)
            continue

        if _STATUS_RANK[status] > _STATUS_RANK.get(alerta.estado_envio, 0):
            alerta.estado_envio = status
        if status == "failed":
            errors = json.dumps(st.get("errors", []), ensure_ascii=False)
            alerta.respuesta_api = f"{alerta.respuesta_api or ''}\nwebhook_failed: {errors}".strip()

    # Process incoming text messages (coach schedule updates)
    for msg in _extract_messages(body):
        if msg.get("type") != "text":
            continue
        from_number = msg.get("from", "")
        texto = msg.get("text", {}).get("body", "").strip()
        if not texto:
            continue
        try:
            await _procesar_mensaje_entrante(db, from_number, texto)
        except Exception:
            logger.exception("Error procesando mensaje entrante de %s", from_number)

    await db.commit()
    return {"status": "ok"}


async def _procesar_mensaje_entrante(db: AsyncSession, from_number: str, texto: str) -> None:
    """Process an incoming WhatsApp message from a staff member."""
    result = await db.execute(
        select(Staff).where(Staff.telefono_whatsapp == from_number, Staff.recibe_alertas == True)  # noqa: E712
    )
    staff = result.scalars().first()
    if not staff:
        logger.debug("Mensaje de número no reconocido como staff: %s", from_number)
        return

    result = await db.execute(
        select(Categoria).where(Categoria.club_id == staff.club_id, Categoria.activo == True)  # noqa: E712
    )
    categorias = result.scalars().all()
    if not categorias:
        return

    nombres_categorias = [c.nombre for c in categorias]
    cat_map = {c.nombre: c for c in categorias}

    if texto.lower() in ("hola", "ayuda", "menu", "menú", "help", "?"):
        cats_ejemplo = nombres_categorias[0] if nombres_categorias else "Sub-13"
        await enviar_texto_whatsapp(
            from_number,
            f"📅 *Mi Plantel · Horarios*\n\n"
            f"Escríbeme el horario de la semana y lo actualizo automáticamente.\n\n"
            f"Ejemplo: _{cats_ejemplo} entrena martes y jueves a las 15:30_",
        )
        return

    from app.services.horarios_semana import _formato_horario, marcar_horario_confirmado

    # Confirmation of unchanged schedule (reply to Sunday message)
    if texto.lower().strip() in ("si", "sí", "ok", "mismo", "confirmo", "igual", "se mantiene"):
        resumen = "\n".join(_formato_horario(c) for c in sorted(categorias, key=lambda c: c.nombre))
        await marcar_horario_confirmado(db, [c.id for c in categorias])
        await enviar_texto_whatsapp(
            from_number,
            f"✅ *Horarios confirmados para esta semana*\n\n{resumen}",
        )
        return

    cambios = await parsear_horario(texto, nombres_categorias)
    if not cambios:
        return

    confirmaciones = []
    cats_actualizadas = []
    for cambio in cambios:
        cat = cat_map.get(cambio.get("categoria"))
        if not cat:
            continue

        hora = cambio.get("hora_inicio")
        dias = cambio.get("dias")

        if hora:
            cat.hora_inicio = hora
        if dias:
            cat.dias_entrenamiento = dias

        partes = []
        if hora:
            partes.append(f"hora {hora}")
        if dias:
            nombres_dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
            partes.append("días: " + ", ".join(nombres_dias[d] for d in sorted(dias)))
        confirmaciones.append(f"✅ {cat.nombre}: {' · '.join(partes)}")
        cats_actualizadas.append(cat.id)

    if confirmaciones:
        await marcar_horario_confirmado(db, cats_actualizadas)
        await enviar_texto_whatsapp(
            from_number,
            "📅 Horarios actualizados:\n" + "\n".join(confirmaciones),
        )


def _extract_statuses(body: dict) -> list[dict]:
    """Flatten Meta's entry[].changes[].value.statuses[] structure."""
    statuses = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            statuses.extend(change.get("value", {}).get("statuses", []))
    return statuses


def _extract_messages(body: dict) -> list[dict]:
    """Flatten Meta's entry[].changes[].value.messages[] structure."""
    messages = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            messages.extend(change.get("value", {}).get("messages", []))
    return messages
