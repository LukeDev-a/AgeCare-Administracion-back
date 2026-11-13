"""Recuperación MFA: contraseña, confirmación por correo y decisión de otro admin."""
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
from app.errors import conflict, invalid
from app.invitation_mail import ensure_mail_configured, send_message
from app.login_attempts import is_locked, record_failure, reset_attempts
from app.password_reset import cancel_resets
from app.security import as_utc, hash_password, hash_refresh, now_utc, verify_password

ACTIVE = ('awaiting_email', 'pending')
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def current(row, user):
    return bool(user and user.is_active and user.password_hash and user.mfa_enabled
                and row.auth_version == user.auth_version
                and decrypt(row.email_encrypted) == user.email
                and as_utc(row.expires_at) > now_utc())


def queue(db, row, recipient, kind, **extra):
    db.add(models.MfaRecoveryEmail(recovery_id=row.id, recipient_id=recipient.id, kind=kind,
        payload_encrypted=encrypt(json.dumps({'email': recipient.email, **extra})), next_attempt_at=now_utc()))


async def request_recovery(db, email, password, reason, request):
    ensure_mail_configured()
    user = await db.scalar(select(models.AdminUser).where(models.AdminUser.email == email.lower()).with_for_update())
    # Verificación de hash incluso para cuentas inexistentes; respuesta pública genérica.
    valid = verify_password(password, user.password_hash if user and user.password_hash else DUMMY_HASH)
    if not user or not user.is_active or is_locked(user):
        return
    if not valid:
        record_failure(user)
        await audit(db, request, 'auth.mfa_recovery_failed', 'admin_user', user.id,
                    metadata={'outcome': 'failure'})
        return
    if not user.mfa_enabled:
        return
    recent = (await db.scalars(select(models.AdminMfaRecovery).where(
        models.AdminMfaRecovery.admin_id == user.id,
        models.AdminMfaRecovery.created_at > now_utc() - timedelta(hours=1)
    ).order_by(models.AdminMfaRecovery.created_at.desc()))).all()
    if len(recent) >= 3 or (recent and now_utc() - as_utc(recent[0].created_at) < timedelta(minutes=1)):
        return
    # No reiniciar el contador de fallos: conocer la contraseña no demuestra MFA.
    old_ids = select(models.AdminMfaRecovery.id).where(models.AdminMfaRecovery.admin_id == user.id,
        models.AdminMfaRecovery.status.in_(ACTIVE))
    await db.execute(update(models.MfaRecoveryEmail).where(models.MfaRecoveryEmail.recovery_id.in_(old_ids),
        models.MfaRecoveryEmail.status == 'queued').values(status='cancelled', payload_encrypted=None))
    await db.execute(update(models.AdminMfaRecovery).where(models.AdminMfaRecovery.admin_id == user.id,
        models.AdminMfaRecovery.status.in_(ACTIVE)).values(status='cancelled'))
    token = secrets.token_urlsafe(48)
    row = models.AdminMfaRecovery(admin_id=user.id, token_hash=hash_refresh(token), auth_version=user.auth_version,
        email_encrypted=encrypt(user.email), reason=reason, expires_at=now_utc() + timedelta(minutes=30))
    db.add(row)
    await db.flush()
    queue(db, row, user, 'verify', url=get_settings().frontend_url.rstrip('/') + '/recuperar-mfa#token=' + token)
    await audit(db, request, 'auth.mfa_recovery_request', 'admin_user', user.id,
                after={'request_id': str(row.id), 'full_name': user.full_name, 'reason': reason, 'status': 'awaiting_email'},
                metadata={'request_id': str(row.id), 'reason': reason})


async def confirm_recovery(db, token, request):
    row = await db.scalar(select(models.AdminMfaRecovery).where(models.AdminMfaRecovery.token_hash == hash_refresh(token)))
    if row is None:
        raise invalid('INVALID_MFA_RECOVERY', 'El enlace no es válido, venció o ya fue utilizado.')
    user = await db.scalar(select(models.AdminUser).where(models.AdminUser.id == row.admin_id).with_for_update())
    await db.refresh(row, with_for_update=True)
    if row.status != 'awaiting_email' or not current(row, user):
        raise invalid('INVALID_MFA_RECOVERY', 'El enlace no es válido, venció o ya fue utilizado.')
    row.status = 'pending'
    row.confirmed_at = now_utc()
    row.expires_at = now_utc() + timedelta(hours=24)
    admins = (await db.scalars(select(models.AdminUser).where(models.AdminUser.is_active.is_(True),
        models.AdminUser.role == 'admin', models.AdminUser.password_hash.is_not(None), models.AdminUser.id != user.id))).all()
    for admin in admins:
        queue(db, row, admin, 'review')
    await audit(db, request, 'auth.mfa_recovery_confirm', 'admin_user', user.id,
                actor=user,
                after={'request_id': str(row.id), 'full_name': user.full_name, 'reason': row.reason, 'status': 'pending'},
                metadata={'request_id': str(row.id), 'reason': row.reason})


async def decide(db, row, user, actor, approved, note, request):
    if user.id == actor.id:
        raise conflict('CANNOT_RECOVER_SELF', 'Otro administrador debe revisar tu solicitud.')
    if row.status != 'pending' or not current(row, user):
        raise conflict('MFA_RECOVERY_NOT_PENDING', 'La solicitud ya fue resuelta, venció o dejó de ser válida.')
    row.status = 'approved' if approved else 'rejected'
    row.decided_at = now_utc()
    row.decided_by = actor.id
    row.decided_by_name = actor.full_name
    row.decision_note = note
    if approved:
        user.mfa_enabled = False
        user.mfa_secret = None
        user.mfa_last_step = None
        user.recovery_hashes = []
        user.mfa_required = True
        user.auth_version += 1
        reset_attempts(user)
        await db.execute(update(models.AdminSession).where(models.AdminSession.admin_id == user.id).values(revoked_at=now_utc()))
        await db.execute(update(models.MfaEnrollment).where(models.MfaEnrollment.admin_id == user.id,
            models.MfaEnrollment.used_at.is_(None)).values(used_at=now_utc(), secret_encrypted=''))
        await cancel_resets(db, user.id)
    queue(db, row, user, 'decision')
    await audit(db, request, 'staff.mfa_recovery_approve' if approved else 'staff.mfa_recovery_reject',
        'admin_user', user.id, after={'request_id': str(row.id), 'full_name': user.full_name, 'decision': row.status, 'note': note},
        metadata={'request_id': str(row.id), 'reason': note,
        'identity_verified': approved, 'outcome': row.status})


def send_mail(payload, kind, row):
    message = EmailMessage()
    message['From'] = get_settings().mail_from
    message['To'] = payload['email']
    if kind == 'verify':
        message['Subject'] = 'AgeCare: confirma tu solicitud de recuperación MFA'
        text = ('Solicitaste recuperar el acceso por pérdida del autenticador y los códigos.\n'
            'Confirma tu solicitud en el siguiente enlace (vence en 30 minutos y es de un uso):\n'
            + payload['url'] + '\nLa confirmación no elimina tu MFA: otro administrador debe verificar tu identidad.\n'
            'Si no lo solicitaste, ignora el mensaje y contacta al administrador.')
    elif kind == 'review':
        message['Subject'] = 'AgeCare: solicitud MFA pendiente de revisión'
        text = ('Hay una solicitud de recuperación MFA confirmada por correo.\n'
            'Revisa Cuentas de la consola → Recuperación MFA y verifica la identidad por un canal conocido.\n'
            + get_settings().frontend_url.rstrip('/') + '/cuentas\nSolicitud: ' + str(row.id))
    else:
        message['Subject'] = 'AgeCare: decisión sobre tu recuperación MFA'
        text = ('La solicitud fue aprobada. Las sesiones y el MFA anterior fueron invalidados. '
            'Inicia sesión con tu contraseña para configurar y verificar un nuevo autenticador.'
            if row.status == 'approved' else 'La solicitud fue rechazada. Contacta al administrador para aclarar tu identidad.')
    message.set_content(text)
    send_message(message)


async def deliver_pending():
    async with get_session_factory()() as db:
        mail = await db.scalar(select(models.MfaRecoveryEmail).where(models.MfaRecoveryEmail.status == 'queued',
            models.MfaRecoveryEmail.next_attempt_at <= now_utc()).order_by(models.MfaRecoveryEmail.created_at).limit(1))
        if mail is None:
            return False
        recipient = await db.scalar(select(models.AdminUser).where(models.AdminUser.id == mail.recipient_id)
                                  .with_for_update(skip_locked=True))
        if recipient is None:
            return False
        await db.refresh(mail, with_for_update=True)
        if mail.status != 'queued':
            return True
        try:
            row = await db.get(models.AdminMfaRecovery, mail.recovery_id)
            target = await db.get(models.AdminUser, row.admin_id) if row else None
            payload = json.loads(decrypt(mail.payload_encrypted))
            valid = recipient.is_active and recipient.password_hash and payload['email'] == recipient.email
            if mail.kind == 'verify':
                valid = valid and row.status == 'awaiting_email' and current(row, target)
            elif mail.kind == 'review':
                valid = valid and recipient.role == 'admin' and recipient.id != row.admin_id and row.status == 'pending' and current(row, target)
            else:
                valid = valid and row.status in ('approved', 'rejected') and decrypt(row.email_encrypted) == recipient.email
            if not valid:
                mail.status = 'cancelled'
            else:
                await asyncio.to_thread(send_mail, payload, mail.kind, row)
                mail.status = 'sent'
            mail.payload_encrypted = None
        except Exception:
            mail.attempts += 1
            if mail.attempts >= 5:
                mail.status = 'failed'
                mail.payload_encrypted = None
            else:
                mail.next_attempt_at = now_utc() + timedelta(seconds=30 * 2 ** mail.attempts)
        await db.commit()
        return True


async def recovery_mail_worker():
    while True:
        try:
            found = await deliver_pending()
        except Exception:
            found = False
        await asyncio.sleep(1 if found else 5)
