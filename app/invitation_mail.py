"""Cola transaccional de invitaciones y envío SMTP o Brevo HTTPS."""
import asyncio
import json
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from email.utils import parseaddr
from email_validator import validate_email, EmailNotValidError
from urllib.parse import urlparse

from sqlalchemy import select

from app import models
from app.account_security import cipher, decrypt, encrypt
from app.config import get_settings
from app.brevo_mail import send_message_brevo
from app.database import get_session_factory
from app.errors import ApiError
from app.security import as_utc, now_utc


def ensure_mail_configured():
    settings = get_settings()
    cipher()
    url = urlparse(settings.frontend_url)
    if not settings.mail_from or url.scheme not in {"http", "https"} or not url.netloc:
        raise ApiError(503, "MAIL_NOT_CONFIGURED", "El servidor todavía no tiene configurado el envío de invitaciones.")
    if url.username or url.password or url.query or url.fragment:
        raise ApiError(503, "MAIL_NOT_CONFIGURED", "Revisa la dirección del frontend y las credenciales del correo.")
    try:
        validate_email(parseaddr(settings.mail_from)[1], check_deliverability=False)
    except EmailNotValidError:
        raise ApiError(503, "MAIL_NOT_CONFIGURED", "Revisa el correo remitente.") from None
    if settings.environment != "dev" and url.scheme != "https":
        raise ApiError(503, "MAIL_NOT_CONFIGURED", "Las invitaciones requieren una dirección HTTPS.")
    if settings.mail_provider == 'brevo':
        if not settings.brevo_api_key.strip():
            raise ApiError(503, "MAIL_NOT_CONFIGURED", "Falta configurar la clave API de Brevo.")
        return
    if settings.mail_provider != 'smtp' or not settings.smtp_host or (settings.smtp_username and not settings.smtp_password):
        raise ApiError(503, "MAIL_NOT_CONFIGURED", "Revisa el proveedor y las credenciales del correo.")
    if settings.smtp_security not in {"ssl", "starttls", "none"}:
        raise ApiError(503, "MAIL_NOT_CONFIGURED", "La configuración de correo no es válida.")
    if settings.environment != "dev" and settings.smtp_security == "none":
        raise ApiError(503, "MAIL_NOT_CONFIGURED", "El correo y las invitaciones requieren conexiones seguras.")


def send_smtp(payload: dict):
    settings = get_settings()
    ensure_mail_configured()
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = payload["email"]
    message["Subject"] = "Invitación a la consola de AgeCare"
    message.set_content(
        f"Hola {payload['name']},\n\nTe han invitado a la consola de AgeCare.\n"
        f"Acepta la invitación y configura tu contraseña aquí:\n{payload['url']}\n\n"
        f"Este enlace vence el {payload['expires_at']} (UTC) y solo puede usarse una vez.\n"
        "Si no esperabas esta invitación, contacta al administrador.\n")
    send_message(message)


def send_message(message):
    ensure_mail_configured()
    if get_settings().mail_provider == 'brevo':
        send_message_brevo(message)
    else:
        send_message_smtp(message)


def send_message_smtp(message):
    """Transporte compartido; el contenido lo prepara cada módulo."""
    settings = get_settings()
    ensure_mail_configured()
    transport = smtplib.SMTP_SSL if settings.smtp_security == "ssl" else smtplib.SMTP
    kwargs = {"timeout": 20}
    if settings.smtp_security == "ssl":
        kwargs["context"] = ssl.create_default_context()
    with transport(settings.smtp_host, settings.smtp_port, **kwargs) as server:
        if settings.smtp_security == "starttls":
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        if server.send_message(message):
            raise RuntimeError("El destinatario rechazó el mensaje.")


async def queue_invitation(db, user, invitation, token):
    payload = {"email": user.email, "name": user.full_name,
               "url": get_settings().frontend_url.rstrip("/") + "/aceptar-invitacion#token=" + token,
               "expires_at": as_utc(invitation.expires_at).isoformat()}
    db.add(models.InvitationEmail(invitation_id=invitation.id,
           payload_encrypted=encrypt(json.dumps(payload)), next_attempt_at=now_utc()))
    user.invitation_delivery_status = "queued"


async def deliver_pending():
    # Mantiene el bloqueo durante el envío para evitar dos envíos simultáneos.
    async with get_session_factory()() as db:
        mail = await db.scalar(select(models.InvitationEmail).where(
            models.InvitationEmail.status == "queued", models.InvitationEmail.next_attempt_at <= now_utc())
            .order_by(models.InvitationEmail.created_at).limit(1))
        if mail is None:
            return False
        invitation = await db.get(models.AdminInvitation, mail.invitation_id)
        user = await db.scalar(select(models.AdminUser).where(models.AdminUser.id == invitation.admin_id)
                               .with_for_update(skip_locked=True)) if invitation else None
        if user is None:
            return False
        await db.refresh(invitation, with_for_update=True)
        await db.refresh(mail, with_for_update=True)
        if mail.status != "queued":
            return True
        if not user or invitation.revoked_at or invitation.accepted_at or as_utc(invitation.expires_at) <= now_utc():
            mail.status = "cancelled"; mail.payload_encrypted = None
        else:
            try:
                await asyncio.to_thread(send_smtp, json.loads(decrypt(mail.payload_encrypted)))
                mail.status = "sent"; mail.payload_encrypted = None
                user.invitation_delivery_status = "sent"
            except Exception:
                # No registra el mensaje SMTP: puede contener credenciales o enlaces.
                mail.attempts += 1
                if mail.attempts >= 5:
                    mail.status = "failed"; mail.payload_encrypted = None
                    user.invitation_delivery_status = "failed"
                else:
                    mail.next_attempt_at = now_utc() + timedelta(seconds=30 * 2 ** mail.attempts)
        await db.commit()
        return True


async def mail_worker():
    while True:
        try:
            found = await deliver_pending()
        except Exception:
            found = False
        await asyncio.sleep(1 if found else 5)
