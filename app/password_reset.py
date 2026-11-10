"""Recuperación de contraseña por enlace temporal y cola transaccional."""
import asyncio
import json
import secrets
from datetime import timedelta
from email.message import EmailMessage

from sqlalchemy import select, update

from app import models
from app.account_security import decrypt, encrypt
from app.audit import audit
from app.config import get_settings
from app.database import get_session_factory
from app.errors import invalid
from app.invitation_mail import ensure_mail_configured, send_message
from app.login_attempts import reset_attempts
from app.security import as_utc, hash_password, hash_refresh, now_utc


async def cancel_resets(db, admin_id):
    await db.execute(update(models.AdminPasswordReset).where(
        models.AdminPasswordReset.admin_id == admin_id,
        models.AdminPasswordReset.used_at.is_(None), models.AdminPasswordReset.revoked_at.is_(None),
    ).values(revoked_at=now_utc(), status='cancelled', payload_encrypted=None))


async def request_reset(db, email, request):
    ensure_mail_configured()
    user = await db.scalar(select(models.AdminUser).where(models.AdminUser.email == email.lower()).with_for_update())
    # Preparar el material criptográfico también para cuentas inexistentes.
    token = secrets.token_urlsafe(48)
    digest = hash_refresh(token)
    payload = encrypt(json.dumps({'email': email.lower(), 'url': get_settings().frontend_url.rstrip('/')
                                 + '/recuperar-contrasena#token=' + token}))
    if user is None or not user.is_active or user.password_hash is None:
        return
    recent = (await db.scalars(select(models.AdminPasswordReset).where(
        models.AdminPasswordReset.admin_id == user.id,
        models.AdminPasswordReset.created_at > now_utc() - timedelta(hours=1),
    ).order_by(models.AdminPasswordReset.created_at.desc()))).all()
    if len(recent) >= 3 or (recent and now_utc() - as_utc(recent[0].created_at) < timedelta(minutes=1)):
        return
    await cancel_resets(db, user.id)
    db.add(models.AdminPasswordReset(admin_id=user.id, token_hash=digest, auth_version=user.auth_version,
        expires_at=now_utc() + timedelta(minutes=30), next_attempt_at=now_utc(), payload_encrypted=payload))
    await audit(db, request, 'auth.password_reset_request', 'admin_user', user.id)


async def confirm_reset(db, token, password, request):
    row = await db.scalar(select(models.AdminPasswordReset).where(models.AdminPasswordReset.token_hash == hash_refresh(token)))
    if row is None:
        raise invalid('INVALID_PASSWORD_RESET', 'El enlace no es válido, venció o ya fue utilizado. Solicita uno nuevo.')
    user = await db.scalar(select(models.AdminUser).where(models.AdminUser.id == row.admin_id).with_for_update())
    await db.refresh(row, with_for_update=True)
    if (user is None or not user.is_active or user.password_hash is None or row.used_at or row.revoked_at
            or as_utc(row.expires_at) <= now_utc() or row.auth_version != user.auth_version):
        raise invalid('INVALID_PASSWORD_RESET', 'El enlace no es válido, venció o ya fue utilizado. Solicita uno nuevo.')
    # Un cambio de correo también invalida el destino previamente verificado.
    # El correo se conserva cifrado aun después de enviar el enlace.
    payload = json.loads(decrypt(row.payload_encrypted)) if row.payload_encrypted else None
    if payload is None or payload['email'] != user.email:
        raise invalid('INVALID_PASSWORD_RESET', 'El enlace ya no está disponible. Solicita uno nuevo.')
    user.password_hash = hash_password(password)
    user.auth_version += 1
    reset_attempts(user)
    row.used_at = now_utc()
    row.auth_version = user.auth_version
    row.status = 'queued'
    row.attempts = 0
    row.next_attempt_at = now_utc()
    row.payload_encrypted = encrypt(json.dumps({'email': user.email, 'completed': True}))
    await cancel_resets(db, user.id)
    await db.execute(update(models.AdminSession).where(models.AdminSession.admin_id == user.id).values(revoked_at=now_utc()))
    await db.execute(update(models.MfaEnrollment).where(models.MfaEnrollment.admin_id == user.id,
        models.MfaEnrollment.used_at.is_(None)).values(used_at=now_utc(), secret_encrypted=''))
    await audit(db, request, 'auth.password_reset', 'admin_user', user.id, actor=user,
                metadata={'outcome': 'success'})


def send_reset(payload):
    message = EmailMessage()
    message['From'] = get_settings().mail_from
    message['To'] = payload['email']
    if payload.get('completed'):
        message['Subject'] = 'AgeCare: contraseña actualizada'
        message.set_content('Tu contraseña de la consola de AgeCare fue actualizada y las sesiones anteriores se cerraron.\n'
                            'Si no realizaste este cambio, contacta al administrador.\n')
    else:
        message['Subject'] = 'Recupera tu contraseña de AgeCare'
        message.set_content('Solicitaste cambiar tu contraseña de la consola de AgeCare.\n\n'
                            f"Abre este enlace para establecer una nueva:\n{payload['url']}\n\n"
                            'El enlace vence en 30 minutos y puede utilizarse una vez.\n'
                            'Si no solicitaste el cambio, puedes ignorar este correo.\n')
    send_message(message)


async def deliver_pending():
    async with get_session_factory()() as db:
        row = await db.scalar(select(models.AdminPasswordReset).where(
            models.AdminPasswordReset.status == 'queued', models.AdminPasswordReset.next_attempt_at <= now_utc(),
        ).order_by(models.AdminPasswordReset.created_at).limit(1))
        if row is None:
            return False
        user = await db.scalar(select(models.AdminUser).where(models.AdminUser.id == row.admin_id)
                               .with_for_update(skip_locked=True))
        if user is None:
            return False
        await db.refresh(row, with_for_update=True)
        if row.status != 'queued':
            return True
        if (not user.is_active or row.revoked_at or user.auth_version != row.auth_version
                or (not row.used_at and as_utc(row.expires_at) <= now_utc())):
            row.status = 'cancelled'
            row.payload_encrypted = None
        else:
            try:
                payload = json.loads(decrypt(row.payload_encrypted))
                if payload['email'] != user.email:
                    row.status = 'cancelled'
                    row.payload_encrypted = None
                else:
                    await asyncio.to_thread(send_reset, payload)
                    row.status = 'sent'
                    # Conservar solo el destino cifrado para validar el enlace.
                    row.payload_encrypted = None if row.used_at else encrypt(json.dumps({'email': user.email}))
            except Exception:
                row.attempts += 1
                if row.attempts >= 5:
                    row.status = 'failed'
                    row.payload_encrypted = None
                else:
                    row.next_attempt_at = now_utc() + timedelta(seconds=30 * 2 ** row.attempts)
        await db.commit()
        return True


async def password_reset_worker():
    while True:
        try:
            found = await deliver_pending()
        except Exception:
            found = False
        await asyncio.sleep(1 if found else 5)
