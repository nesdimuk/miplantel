import json

import httpx

from app.config import settings
from app.messaging.base import MessagingProvider, SendResult


class WhatsAppCloudProvider(MessagingProvider):
    """Sends template messages through Meta's WhatsApp Cloud API."""

    def __init__(self, lang: str = "es_CL"):
        self.lang = lang

    async def send_template(self, to: str, template: str, variables: list[str]) -> SendResult:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": self.lang},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": str(v)} for v in variables],
                    }
                ],
            },
        }
        headers = {
            "Authorization": f"Bearer {settings.whatsapp_token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(settings.whatsapp_api_url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            return SendResult(ok=False, message_id=None, response=f"http_error: {exc}")

        body = resp.text
        if resp.status_code == 200:
            try:
                wamid = resp.json()["messages"][0]["id"]
            except (KeyError, IndexError, json.JSONDecodeError):
                wamid = None
            return SendResult(ok=True, message_id=wamid, response=body)
        return SendResult(ok=False, message_id=None, response=f"status={resp.status_code} body={body}")
