from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/assist_tracker"

    # App
    secret_key: str = "change-me-in-production"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False
    base_url: str = ""  # public URL for QR codes, e.g. https://tracker.saidcoach.com; empty = derive from request

    # WhatsApp Cloud API
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_verify_token: str = "assist_verify_token"
    whatsapp_api_version: str = "v19.0"

    # Admin
    admin_password: str = "admin123"

    # OpenAI (para parsing de mensajes del entrenador)
    openai_api_key: str = ""

    @property
    def whatsapp_api_url(self) -> str:
        return f"https://graph.facebook.com/{self.whatsapp_api_version}/{self.whatsapp_phone_id}/messages"

    @property
    def use_fake_messaging(self) -> bool:
        return self.environment in ("development", "test") or not self.whatsapp_token


settings = Settings()
