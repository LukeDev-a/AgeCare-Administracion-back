"""Migración y carreras RF06 SOLO en base temporal agecare_seed_check_inc_*.

SMTP simulado. No ejecutar contra una base con datos de trabajo.
"""
import asyncio
import subprocess
from uuid import UUID
from starlette.requests import Request
from sqlalchemy import select, text, func
from app import database, models, incident_mail
from app.config import get_settings
from app.errors import ApiError
from app.routers.ops import patch_incident
from app.schemas.ops import IncidentPatchIn

ID = UUID('00000000-0000-0000-0000-000000000009')

def target():
    url = database.get_engine().url
    assert url.database.startswith('agecare_seed_check_inc_') and url.database != 'agecare_admin'
    assert url.host == 'db' and url.username == 'agecare'

async def prepare():
    target()
    async with database.get_engine().begin() as conn:
        await conn.run_sync(lambda bind: models.IncidentEmail.__table__.drop(bind, checkfirst=True))
        await conn.execute(text('ALTER TABLE ops_incidents DROP COLUMN IF EXISTS notification_status'))
        await conn.execute(text("INSERT INTO ops_incidents (id, title, severity, status, description, is_maintenance, started_at, created_at, updated_at) VALUES ('00000000-0000-0000-0000-000000000009', 'Legado temporal', 'degraded', 'investigating', 'Conservar descripción', false, '2026-10-01T12:00:00Z', now(), now())"))
        before = dict((await conn.execute(text('SELECT * FROM ops_incidents'))).mappings().one())
    await database.get_engine().dispose()
    return before

async def verify(before):
    target()
    factory = database.get_session_factory()
    async with factory() as db:
        after = dict((await db.execute(text('SELECT * FROM ops_incidents'))).mappings().one())
        assert after.pop('notification_status') == 'not_configured' and after == before
        actor = models.AdminUser(full_name='Admin de prueba', email='temp@example.org', role='admin', password_hash='test')
        db.add(actor); await db.flush(); actor_id = actor.id; await db.commit()
    async def change(state, resolution=None):
        async with factory() as db:
            actor = await db.get(models.AdminUser, actor_id)
            request = Request({'type': 'http', 'method': 'PATCH', 'headers': []})
            request.state.actor = actor
            body = IncidentPatchIn(**({'status': state, 'resolution': resolution} if resolution else {'status': state}))
            try:
                await patch_incident(ID, body, request, db, actor)
                await db.commit()
                return 200
            except ApiError as error:
                await db.rollback()
                return error.status_code
    assert sorted(await asyncio.gather(change('observing'), change('observing'))) == [200, 409]
    result = await asyncio.gather(change('resolved', 'Resuelto en prueba'), change('resolved'))
    assert 200 in result and (409 in result or 422 in result)
    settings = get_settings()
    settings.incident_mail_recipients = 'ops@example.org,admin@example.org'
    async with factory() as db:
        incident = await db.get(models.Incident, ID)
        assert incident.status == 'resolved' and incident.description == before['description']
        assert await db.scalar(select(func.count()).select_from(models.AuditLog)) == 2
        await incident_mail.queue_incident(db, incident); await db.commit()
    sent = []
    incident_mail.send_incident = lambda payload: sent.append(payload['email'])
    await asyncio.gather(*(incident_mail.deliver_pending() for _ in range(3)))
    assert sorted(sent) == ['admin@example.org', 'ops@example.org']
    async with factory() as db:
        assert (await db.get(models.Incident, ID)).notification_status == 'sent'
    await database.get_engine().dispose()
    print('PostgreSQL OK: 0008→0009 conserva el legado; transiciones y correo concurrentes sin duplicación durante la prueba. SMTP simulado.')

if __name__ == '__main__':
    target()
    subprocess.run(['alembic', 'upgrade', '0008'], check=True)
    before = asyncio.run(prepare())
    subprocess.run(['alembic', 'upgrade', 'head'], check=True)
    asyncio.run(verify(before))
