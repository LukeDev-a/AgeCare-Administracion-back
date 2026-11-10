"""Avisos a cuentas activas admin/support, encolados con el incidente."""
import asyncio
import json
from datetime import timedelta
from email.message import EmailMessage
from email_validator import validate_email, EmailNotValidError
from sqlalchemy import select, update
from app import models
from app.account_security import encrypt, decrypt
from app.config import get_settings
from app.enums import AdminRole
from app.database import get_session_factory
from app.errors import ApiError
from app.invitation_mail import ensure_mail_configured, send_message
from app.security import now_utc


async def queue_incident(db, incident):
    configured = (await db.scalars(select(models.AdminUser.email).where(
        models.AdminUser.is_active.is_(True),
        models.AdminUser.password_hash.is_not(None),
        models.AdminUser.role.in_([AdminRole.admin, AdminRole.support]),
    ))).all()
    if not configured:
        incident.notification_status = 'not_configured'
        return
    try:
        recipients = list(dict.fromkeys(validate_email(value, check_deliverability=False).normalized for value in configured))
        ensure_mail_configured()
    except (EmailNotValidError, ApiError):
        incident.notification_status = 'not_configured'
        return
    # No enviar durante la petición: creación y avisos se confirman juntos.
    for recipient in recipients:
        payload = {'email': recipient, 'id': str(incident.id), 'title': incident.title,
                   'maintenance': incident.is_maintenance, 'severity': incident.severity,
                   'started_at': incident.started_at.isoformat()}
        db.add(models.IncidentEmail(incident_id=incident.id, payload_encrypted=encrypt(json.dumps(payload)),
                                   next_attempt_at=now_utc()))
    incident.notification_status = 'queued'


def send_incident(payload):
    message = EmailMessage()
    message['From'] = get_settings().mail_from
    message['To'] = payload['email']
    message['Subject'] = 'AgeCare: nuevo mantenimiento' if payload['maintenance'] else 'AgeCare: nuevo incidente'
    # Sin descripción libre ni datos clínicos; los detalles se consultan autenticados.
    severity = 'Fuera de servicio' if payload['severity'] == 'outage' else 'Servicio degradado'
    message.set_content(f"Se registró: {payload['title']}\nSeveridad: {severity}\n"
        f"Inicio: {payload['started_at']}\nIdentificador: {payload['id']}\n\n"
        'Ingresa a la consola de AgeCare para consultar los detalles.\n')
    send_message(message)


async def deliver_pending():
    async with get_session_factory()() as db:
        mail = await db.scalar(select(models.IncidentEmail).where(models.IncidentEmail.status == 'queued',
            models.IncidentEmail.next_attempt_at <= now_utc()).order_by(models.IncidentEmail.created_at)
            .limit(1).with_for_update(skip_locked=True))
        if mail is None:
            return False
        try:
            payload = json.loads(decrypt(mail.payload_encrypted))
            recipient = await db.scalar(select(models.AdminUser.id).where(
                models.AdminUser.email == payload['email'], models.AdminUser.is_active.is_(True),
                models.AdminUser.password_hash.is_not(None),
                models.AdminUser.role.in_([AdminRole.admin, AdminRole.support]),
            ))
            if recipient is None:
                mail.status = 'cancelled'
            else:
                await asyncio.to_thread(send_incident, payload)
                mail.status = 'sent'
            mail.payload_encrypted = None
        except Exception:
            # No volcar payloads ni errores SMTP con destinatarios/credenciales.
            mail.attempts += 1
            if mail.attempts >= 5:
                mail.status = 'failed'; mail.payload_encrypted = None
            else:
                mail.next_attempt_at = now_utc() + timedelta(seconds=30 * 2 ** mail.attempts)
        incident = await db.scalar(select(models.Incident).where(models.Incident.id == mail.incident_id).with_for_update())
        await db.flush()
        states = (await db.scalars(select(models.IncidentEmail.status).where(models.IncidentEmail.incident_id == mail.incident_id))).all()
        if incident:
            state = ('queued' if 'queued' in states else 'failed' if 'failed' in states
                     else 'sent' if 'sent' in states else 'not_configured')
            # La entrega técnica no es una edición del contenido del incidente.
            await db.execute(update(models.Incident).where(models.Incident.id == incident.id)
                .values(notification_status=state, updated_at=incident.updated_at))
        await db.commit()
        return True


async def incident_mail_worker():
    while True:
        try:
            found = await deliver_pending()
        except Exception:
            found = False
        await asyncio.sleep(1 if found else 5)
