from typing import Optional

from app.config import settings
from app.messaging.base import MessagingProvider, SendResult
from app.messaging.fake import FakeProvider
from app.messaging.telegram_provider import TelegramProvider
from app.messaging.whatsapp_cloud import WhatsAppCloudProvider

__all__ = [
    "MessagingProvider", "SendResult", "FakeProvider",
    "WhatsAppCloudProvider", "TelegramProvider",
    "get_provider", "get_providers",
]

_provider: Optional[MessagingProvider] = None
_providers: Optional[list[MessagingProvider]] = None


def get_provider() -> MessagingProvider:
    """Singleton primary provider (first in the active list). Used by legacy callers."""
    return get_providers()[0]


def get_providers() -> list[MessagingProvider]:
    """All active providers for the current MESSAGING_PROVIDER setting.

    Returns a FakeProvider list in development/test or when no credentials exist.
    In production returns one or two real providers depending on `messaging_provider`.
    """
    global _providers
    if _providers is not None:
        return _providers

    if settings.use_fake_messaging:
        _providers = [FakeProvider()]
        return _providers

    mp = settings.messaging_provider
    if mp == "telegram":
        _providers = [TelegramProvider()]
    elif mp == "both":
        _providers = [WhatsAppCloudProvider(), TelegramProvider()]
    else:  # "whatsapp" (default)
        _providers = [WhatsAppCloudProvider()]

    return _providers
