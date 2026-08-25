"""Telegram Bot webhook and staff-linking endpoints.

Flow:
  1. Admin generates a deep link for each staff member:
       https://t.me/{BOT_USERNAME}?start=link_{staff_id}_{hmac}
  2. Staff member clicks → Telegram opens → bot receives:
       /start link_{staff_id}_{hmac}
  3. This webhook validates the HMAC, saves telegram_chat_id, replies "✅ Vinculado".
  4. From that point, Telegram notifications route to that chat_id.

Register the webhook with Telegram once after deploy:
  POST https://api.telegram.org/bot{TOKEN}/setWebhook
  Body: {"url": "https://miplantel.app/api/telegram/webhook",
         "secret_token": "{TELEGRAM_WEBHOOK_SECRET}"}
"""
import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.db.models import Staff

router = APIRouter(prefix="/api/telegram")
logger = logging.getLogger("api.telegram")


# ------------------------------------------------------------------ helpers

def _make_link_token(staff_id: int) -> str:
    """HMAC-SHA256 of staff_id using secret_key as key (hex, first 16 chars)."""
    sig = hmac.new(
        settings.secret_key.encode(),
        f"tglink:{staff_id}".encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    return f"link_{staff_id}_{sig}"


def _verify_link_token(token: str) -> int | None:
    """Return staff_id if token is valid, else None."""
    try:
        _, staff_id_str, sig = token.split("_", 2)
        staff_id = int(staff_id_str)
    except (ValueError, AttributeError):
        return None
    expected = _make_link_token(staff_id)
    if not hmac.compare_digest(token, expected):
        return None
    return staff_id


async def _tg_reply(chat_id: int, text: str) -> None:
    if not settings.telegram_bot_token:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
    except Exception:
        logger.exception("Error al responder en Telegram (chat_id=%s)", chat_id)


# ------------------------------------------------------------------ endpoints

@router.get("/deep-link/{staff_id}")
async def get_deep_link(
    staff_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return the Telegram deep link for a staff member (called from admin UI)."""
    staff = await db.get(Staff, staff_id)
    if not staff:
        raise HTTPException(404, "Staff no encontrado")
    token = _make_link_token(staff_id)
    bot = settings.telegram_bot_username
    return {
        "url": f"https://t.me/{bot}?start={token}",
        "staff_id": staff_id,
        "nombre": staff.nombre,
        "telegram_chat_id": staff.telegram_chat_id,
    }


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: str = Header(default=""),
):
    """Receive Telegram Bot API updates."""
    # Verify secret token set during setWebhook
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(403, "Invalid secret token")

    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not message:
        return JSONResponse({"ok": True})

    chat_id: int = message["chat"]["id"]
    text: str = message.get("text", "").strip()

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        payload = parts[1] if len(parts) > 1 else ""
        await _handle_start(db, chat_id, payload)
    else:
        await _tg_reply(
            chat_id,
            "👋 Hola, soy el bot de *Mi Plantel*.\n"
            "Para vincular tu cuenta, usa el enlace que te envió el administrador.",
        )

    return JSONResponse({"ok": True})


async def _handle_start(db: AsyncSession, chat_id: int, payload: str) -> None:
    if not payload.startswith("link_"):
        await _tg_reply(
            chat_id,
            "👋 Hola, soy el bot de *Mi Plantel*.\n"
            "Para vincular tu cuenta de entrenador usa el enlace del panel de administración.",
        )
        return

    staff_id = _verify_link_token(payload)
    if staff_id is None:
        await _tg_reply(chat_id, "❌ Enlace inválido o expirado. Pide uno nuevo al administrador.")
        return

    staff = await db.get(Staff, staff_id)
    if not staff:
        await _tg_reply(chat_id, "❌ Staff no encontrado.")
        return

    if staff.telegram_chat_id == chat_id:
        # Ya estaba vinculado — silencio para no spamear
        return

    staff.telegram_chat_id = chat_id
    await db.commit()

    logger.info("Telegram vinculado: staff_id=%s nombre=%s chat_id=%s", staff_id, staff.nombre, chat_id)
    await _tg_reply(
        chat_id,
        f"✅ *¡Listo, {staff.nombre}!*\n"
        "A partir de ahora recibirás las notificaciones de Mi Plantel aquí en Telegram.",
    )
