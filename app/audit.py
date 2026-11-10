"""Eventos explícitos de negocio, autenticación y lectura sensible; nunca clics."""
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import models

SENSITIVE_KEYS = {"password", "password_hash", "mfa_secret", "refresh_hash", "token",
                  "access_token", "refresh_token", "otp_code", "authorization",
                  "cookie", "secret", "api_key", "recovery_code", "recovery_codes",
                  "recovery_hashes", "enrollment_token", "secret_encrypted", "payload_encrypted"}
SENSITIVE_KEYS |= {"smtp_password", "brevo_api_key", "gemini_api_key", "encryption_key", "jwt_secret",
                   "totp", "otp", "mfa_qr", "qr_code", "qr_data_url", "otpauth_uri",
                   "client_secret", "invitation_token", "reset_token"}

# Una consulta, un clic o la gestión técnica de una sesión no son cambios de negocio.
BUSINESS_ACTIONS = {
    'end_users.demo_deactivate': ('Desactivó una cuenta de prueba', 'Usuarios y pacientes · demostración'),
    "games.create": ("Creó un juego o aplicación", "Juegos y aplicaciones"),
    "games.update": ("Modificó un juego o aplicación", "Juegos y aplicaciones"),
    "games.delete": ("Eliminó un juego o aplicación", "Juegos y aplicaciones"),
    "games.activate": ("Activó un juego o aplicación", "Juegos y aplicaciones"),
    "games.deactivate": ("Desactivó un juego o aplicación", "Juegos y aplicaciones"),
    "games.toggle": ("Cambió el estado de un juego o aplicación", "Juegos y aplicaciones"),
    "ticket.create": ("Creó un ticket", "Soporte"),
    "ticket.update": ("Modificó un ticket", "Soporte"),
    "ticket.reply": ("Respondió un ticket", "Soporte"),
    "content.create": ("Creó contenido", "Contenido"),
    "content.update": ("Modificó contenido", "Contenido"),
    "content.publish": ("Publicó contenido", "Contenido"),
    "content.unpublish": ("Retiró contenido", "Contenido"),
    "content.delete": ("Eliminó contenido", "Contenido"),
    "content.approve": ("Aprobó el texto editorial", "Contenido"),
    "content.audio_retry": ("Solicitó regenerar audio", "Contenido"),
    "content.candidate_review": ("Revisó una noticia recopilada", "Contenido"),
    "content.adaptation_request": ("Solicitó adaptar una noticia", "Contenido"),
    "content.collection_request": ("Solicitó recopilar noticias", "Contenido"),
    "marketplace.product_create": ("Creó un producto", "Marketplace"),
    "marketplace.product_update": ("Modificó un producto", "Marketplace"),
    "marketplace.caregiver_update": ("Modificó un perfil de cuidador", "Marketplace"),
    "moderation.approve": ("Aprobó contenido reportado", "Moderación"),
    "moderation.reject": ("Rechazó contenido reportado", "Moderación"),
    "ops.incident_create": ("Creó un incidente", "Estado operativo"),
    "ops.incident_update": ("Modificó un incidente", "Estado operativo"),
    "settings.update": ("Modificó la configuración", "Configuración"),
    "legal.version_create": ("Creó una versión de documento legal", "Documentos legales"),
    "legal.version_publish": ("Publicó un documento legal", "Documentos legales"),
    "staff.create": ("Creó una cuenta de administración", "Administradores"),
    "staff.update": ("Modificó una cuenta de administración", "Administradores"),
    "staff.delete": ("Eliminó una cuenta de administración", "Administradores"),
    "staff.invitation_accept": ("Aceptó la invitación a la consola", "Administradores"),
    "staff.invitation_resend": ("Reenvió una invitación", "Administradores"),
    "staff.invitation_cancel": ("Canceló una invitación", "Administradores"),
    "staff.mfa_enable": ("Activó la verificación en dos pasos", "Seguridad de cuentas"),
    "staff.mfa_disable": ("Desactivó la verificación en dos pasos", "Seguridad de cuentas"),
    "staff.mfa_recovery": ("Renovó sus códigos de recuperación", "Seguridad de cuentas"),
}

SECURITY_ACTIONS = {
    'auth.password_reset_request': ('Solicitó recuperación de contraseña', 'Seguridad de cuentas'),
    'auth.password_reset': ('Restableció su contraseña', 'Seguridad de cuentas'),
    'end_users.demo_list': ('Consultó el listado de cuentas de prueba', 'Usuarios y pacientes · demostración'),
    'patients.demo_list': ('Consultó el listado de pacientes de prueba', 'Usuarios y pacientes · demostración'),
    'end_users.demo_read': ('Consultó una cuenta de prueba', 'Usuarios y pacientes · demostración'),
    'patients.demo_read': ('Consultó un paciente de prueba', 'Usuarios y pacientes · demostración'),
    "auth.login": ("Inició sesión", "Acceso a la consola"),
    "auth.login_failed": ("Intento de acceso rechazado", "Acceso a la consola"),
    "ticket.conversation_read": ("Consultó una conversación de soporte", "Soporte"),
}
AUDIT_ACTIONS = {**BUSINESS_ACTIONS, **SECURITY_ACTIONS}
SENSITIVE_READ_ACTIONS = {'ticket.conversation_read', 'end_users.demo_read', 'patients.demo_read',
                          'end_users.demo_list', 'patients.demo_list'}


def _mask(data):
    if isinstance(data, dict):
        return {k: ("***" if k.lower().removeprefix('admin_') in SENSITIVE_KEYS else _mask(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [_mask(v) for v in data]
    return data


async def audit(db: AsyncSession, request: Request, action: str,
                entity_type: str | None = None, entity_id: UUID | None = None,
                before: dict | None = None, after: dict | None = None,
                actor: models.AdminUser | None = None,
                metadata: dict | None = None, record_id: UUID | None = None) -> None:
    allowed_method = (request.method == "GET" if action in SENSITIVE_READ_ACTIONS
                      else request.method in {"POST", "PUT", "PATCH", "DELETE"})
    if action not in AUDIT_ACTIONS or not allowed_method:
        return
    actor = actor or getattr(request.state, "actor", None)
    db.add(models.AuditLog(
        id=record_id, actor_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else None, actor_role=actor.role if actor else None,
        action=action, entity_type=entity_type, entity_id=entity_id,
        before=_mask(before), after=_mask(after),
        event_metadata=_mask({k: v for k, v in (metadata or {}).items()
                              if k in {"outcome", "reason", "page", "page_size"}}) or None,
        ip=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:300],
    ))
