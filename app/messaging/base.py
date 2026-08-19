from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class SendResult:
    ok: bool
    message_id: Optional[str]  # wamid from Meta, None on failure
    response: str              # raw API response (JSON/text) for alertas_log


class MessagingProvider(ABC):
    """Abstraction over the messaging channel used to reach staff.

    Implementations must be stateless per-send: one call, one message,
    one SendResult. Retries are handled by the alert service, not here.
    """

    @abstractmethod
    async def send_template(self, to: str, template: str, variables: list[str]) -> SendResult:
        """Send a pre-approved template message.

        to: phone in international format without '+' (e.g. 56912345678)
        template: template name registered with the provider
        variables: positional values for the template placeholders {{1}}, {{2}}, ...
        """
