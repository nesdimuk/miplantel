import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.db.models import AlertaLog

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
    """Receive delivery statuses (sent/delivered/read/failed) and store them in alertas_log."""
    body = await request.json()

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

    await db.commit()
    return {"status": "ok"}


def _extract_statuses(body: dict) -> list[dict]:
    """Flatten Meta's entry[].changes[].value.statuses[] structure."""
    statuses = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            statuses.extend(change.get("value", {}).get("statuses", []))
    return statuses
