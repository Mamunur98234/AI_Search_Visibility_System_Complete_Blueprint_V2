from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://aisv_app:change-me-app@localhost:5432/aisv"
    migration_database_url: str = "postgresql+psycopg://aisv_owner:change-me-owner@localhost:5432/aisv"
    redis_url: str = ""
    encryption_keys: str = ""
    allowed_origins: str = "http://localhost:3000"
    public_web_url: str = "http://localhost:3000"
    allow_signup: bool = True

    email_backend: Literal["console", "file", "smtp", "memory"] = "console"
    email_file_dir: str = "./var/outbox"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@localhost"

    session_idle_minutes: int = 12 * 60
    session_absolute_hours: int = 7 * 24
    invitation_ttl_hours: int = 72
    password_reset_ttl_minutes: int = 60
    login_rate_limit_per_ip: int = 20
    login_rate_limit_per_account: int = 8
    login_rate_window_seconds: int = 900

    @field_validator("encryption_keys")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def session_cookie_name(self) -> str:
        # __Host- prefix requires Secure + Path=/ + no Domain: only usable over HTTPS.
        return "__Host-aisv_session" if self.is_production else "aisv_session"

    @property
    def csrf_cookie_name(self) -> str:
        return "__Host-aisv_csrf" if self.is_production else "aisv_csrf"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production:
        if not s.encryption_keys:
            raise RuntimeError("ENCRYPTION_KEYS must be set in production")
        if s.email_backend in ("console", "file", "memory"):
            raise RuntimeError("EMAIL_BACKEND must be smtp in production")
        if not s.redis_url:
            raise RuntimeError("REDIS_URL must be set in production (rate limiting)")
    return s
