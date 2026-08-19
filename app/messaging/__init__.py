from typing import Optional

from app.config import settings
from app.messaging.base import MessagingProvider, SendResult
from app.messaging.fake import FakeProvider
from app.messaging.whatsapp_cloud import WhatsAppCloudProvider

__all__ = ["MessagingProvider", "SendResult", "FakeProvider", "WhatsAppCloudProvider", "get_provider"]

_provider: Optional[MessagingProvider] = None


def get_provider() -> MessagingProvider:
    """Singleton provider: fake in dev/test, WhatsApp Cloud when credentials exist."""
    global _provider
    if _provider is None:
        _provider = FakeProvider() if settings.use_fake_messaging else WhatsAppCloudProvider()
    return _provider
