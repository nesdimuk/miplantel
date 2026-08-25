"""Telegram Bot API provider — free text + inline keyboard button."""
import json
import logging

import httpx

from app.config import settings
from app.messaging.base import MessagingProvider, SendResult
from app.messaging.templates import render

logger = logging.getLogger("messaging.telegram")

_TG_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramProvider(MessagingProvider):
    """Sends messages via Telegram Bot API.

    `to` must be the staff member's telegram_chat_id (as string).
    The last variable in every template is expected to be a URL;
    it is surfaced as an inline "Ver informe →" button instead of
    appearing in the message body, keeping the text clean.
    """

    async def send_template(self, to: str, template: str, variables: list[str]) -> SendResult:
        text, url = self._split_text_url(template, variables)
        payload: dict = {
            "chat_id": int(to),
            "text": text,
            "parse_mode": "Markdown",
        }
        if url:
            payload["reply_markup"] = {
                "inline_keyboard": [[{"text": "Ver informe →", "url": url}]]
            }
        return await self._send("sendMessage", payload)

    # ------------------------------------------------------------------ helpers

    def _split_text_url(self, template: str, variables: list[str]) -> tuple[str, str]:
        """Return (message_text, button_url).

        If the last variable looks like a URL, remove it from the body and
        return it separately so it becomes an inline button rather than
        cluttering the message text.
        """
        if variables and variables[-1].startswith("http"):
            url = variables[-1]
            body_vars = variables[:-1]
            # Render only the non-URL variables; drop the 📊 {{2}} line from templates
            text = render(template, body_vars + [""])
            # Strip the trailing "📊 " line that had the URL placeholder
            text = text.replace("\n📊 ", "").strip()
        else:
            url = ""
            text = render(template, variables)
        return text, url

    async def _send(self, method: str, payload: dict) -> SendResult:
        url = _TG_API.format(token=settings.telegram_bot_token, method=method)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            return SendResult(ok=False, message_id=None, response=f"http_error: {exc}")

        body = resp.text
        if resp.status_code == 200:
            try:
                msg_id = str(resp.json()["result"]["message_id"])
            except (KeyError, json.JSONDecodeError):
                msg_id = None
            return SendResult(ok=True, message_id=msg_id, response=body)
        return SendResult(ok=False, message_id=None, response=f"status={resp.status_code} body={body}")
