import logging
import uuid
from dataclasses import dataclass, field

from app.messaging.base import MessagingProvider, SendResult
from app.messaging.templates import render

logger = logging.getLogger("messaging.fake")


@dataclass
class FakeProvider(MessagingProvider):
    """Console-logging provider for development and tests.

    Keeps every send in `sent` so tests can assert on messages.
    Set `fail_times` > 0 to make the next N sends fail (retry testing).
    """

    sent: list[dict] = field(default_factory=list)
    fail_times: int = 0

    async def send_template(self, to: str, template: str, variables: list[str]) -> SendResult:
        if self.fail_times > 0:
            self.fail_times -= 1
            logger.warning("FAKE WhatsApp FALLO simulado → %s [%s]", to, template)
            return SendResult(ok=False, message_id=None, response="fake_error: simulated failure")

        preview = render(template, variables)
        self.sent.append({"to": to, "template": template, "variables": variables, "preview": preview})
        wamid = f"wamid.fake-{uuid.uuid4().hex[:12]}"
        logger.info("FAKE WhatsApp → %s [%s]\n%s", to, template, preview)
        return SendResult(ok=True, message_id=wamid, response='{"fake": true}')
