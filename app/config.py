"""Configuración de la API de administración de AgeCare."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ADMIN_", extra="ignore")

    app_name: str = "AgeCare Admin API"
    environment: str = "dev"  # dev | staging | prod
    database_url: str = "postgresql+asyncpg://agecare:agecare@localhost:5432/agecare_admin"

    # JWT
    jwt_secret: str = "cambia-esto-en-produccion"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_hours: int = 12

    # Login
    max_login_attempts: int = 5
    lockout_minutes: int = 15
    allowed_email_domains: str = "wellq.co.uk,wellq.co"  # separados por coma

    # Negocio
    business_timezone: str = "America/Santiago"

    @property
    def allowed_domains(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
