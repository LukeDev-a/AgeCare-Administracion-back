"""Configuración de la API de administración de AgeCare."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from app.database_urls import normalize_database_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ADMIN_", extra="ignore", hide_input_in_errors=True)

    app_name: str = "AgeCare Admin API"
    environment: str = "dev"  # dev | staging | prod
    render_allow_dev_credentials: bool = False  # excepción explícita, solo demo dev
    bootstrap_dev_accounts: bool = False  # alta inicial explícita, solo desarrollo
    seed_demo_enabled: bool = False  # Compose dev lo habilita; nunca borra datos
    end_users_demo_enabled: bool = False  # solo dev: directorio ficticio, sin sesiones móviles
    commercial_worker_enabled: bool = True  # solo cálculo local; sin proveedores externos
    allows_origins: str
    database_url: str = "postgresql+asyncpg://agecare:agecare@localhost:5432/agecare_admin"

    @field_validator('database_url')
    @classmethod
    def compatible_database_url(cls, value):
        return normalize_database_url(value)

    # JWT
    jwt_secret: str = "cambia-esto-en-produccion"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_hours: int = 12

    # Login
    max_login_attempts: int = 5
    lockout_minutes: int = 15
    allowed_email_domains: str = "wellq.co.uk,wellq.co"  # separados por coma
    frontend_url: str = "http://localhost:5173"
    invitation_hours: int = 24
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_security: str = "starttls"  # starttls | ssl | none (solo desarrollo)
    mail_from: str = ""
    mail_worker_enabled: bool = True
    incident_mail_recipients: str = ''  # correos internos separados por coma; vacío no envía
    mfa_required_roles: str = "admin"
    mfa_test_exempt_account_ids: str = ""  # UUID explícitos; solo environment=dev
    encryption_key: str = ""  # clave Fernet estable, diferente de la clave JWT

    # Negocio
    business_timezone: str = "America/Santiago"
    game_public_base_url: str = ""  # raíz pública del backend; vacío usa request.base_url
    # Contenido: activar explícitamente tras confirmar el proyecto gratuito.
    content_worker_enabled: bool = False
    gemini_api_key: str = ""
    gemini_free_tier_confirmed: bool = False
    gemini_text_model: str = "gemini-3.5-flash-lite"
    gemini_tts_model: str = "gemini-3.1-flash-tts-preview"
    gemini_tts_voice: str = "Kore"
    content_audio_dir: str = "content_audio"
    news_collection_hour: int = 8
    news_collection_limit: int = 20
    news_adaptation_batch: int = 5
    gemini_text_daily_limit: int = 500
    gemini_text_rpm: int = 15
    gemini_text_input_tpm: int = 250000
    gemini_tts_daily_limit: int = 10
    gemini_tts_rpm: int = 3
    content_new_audio_daily_limit: int = 5

    @property
    def allowed_domains(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
