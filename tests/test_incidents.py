"""RF06: HTTP y base aislados. SMTP siempre sustituido, sin envíos reales."""
from datetime import datetime, timedelta
from uuid import UUID, uuid4
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app import database, models, incident_mail
from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.security import create_access_token, now_utc, as_utc

BASE = '/api/v1/admin/ops/incidents'
pytestmark = pytest.mark.asyncio

@pytest_asyncio.fixture
async def setup(monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, '_engine', engine)
    monkeypatch.setattr(database, '_session_factory', factory)
    monkeypatch.setattr(get_settings(), 'incident_mail_recipients', '')
    headers = {}
    async with factory() as db:
        for role in ('admin', 'support', 'analyst', 'editor', 'moderator'):
            user = models.AdminUser(full_name=role, role=role, email=f'{role}@example.org', password_hash='test', is_active=True)
            db.add(user); await db.flush()
            headers[role] = {'Authorization': 'Bearer ' + create_access_token(user.id, role)}
        await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        yield client, headers, factory
    await engine.dispose()

def payload(**changes):
    return {'title': 'Incidente de prueba', 'description': 'Descripción original', 'severity': 'degraded',
            'started_at': (now_utc()-timedelta(minutes=2)).isoformat(), **changes}

async def snapshot(factory):
    async with factory() as db:
        return {model.__tablename__: [dict(row) for row in (await db.execute(select(model.__table__))).mappings()]
            for model in (models.Incident, models.AuditLog, models.IncidentEmail)}

@pytest.mark.parametrize('role', ['admin', 'support', 'analyst', 'editor', 'moderator', None])
async def test_permissions_and_no_changes_when_rejected(setup, role):
    client, headers, factory = setup
    inc = (await client.post(BASE, headers=headers['admin'], json=payload())).json()
    actor = headers.get(role, {})
    listing = await client.get(BASE, headers=actor)
    assert listing.status_code == (200 if role in ('admin', 'support', 'analyst') else 401 if role is None else 403)
    before = await snapshot(factory)
    created = await client.post(BASE, headers=actor, json=payload())
    changed = await client.patch(f"{BASE}/{inc['id']}", headers=actor, json={'description': 'Descripción nueva'})
    expected = 200 if role in ('admin', 'support') else 401 if role is None else 403
    assert changed.status_code == expected
    assert created.status_code == (201 if expected == 200 else expected)
    if expected != 200:
        assert await snapshot(factory) == before

async def test_incident_flow_strict_transitions_resolution_and_audit(setup):
    client, headers, factory = setup
    created = await client.post(BASE, headers=headers['admin'], json=payload())
    assert created.status_code == 201, created.text
    inc = created.json(); path = f"{BASE}/{inc['id']}"
    assert inc['status'] == 'investigating' and inc['notification_status'] == 'not_configured'
    assert inc['created_by'] and inc['resolved_at'] is None
    before = await snapshot(factory)
    invalid = await client.patch(path, headers=headers['admin'], json={'status': 'resolved', 'resolution': 'No saltar etapas'})
    assert invalid.status_code == 409 and invalid.json()['error']['code'] == 'INVALID_TRANSITION'
    assert await snapshot(factory) == before
    observed = await client.patch(path, headers=headers['support'], json={'status': 'observing'})
    assert observed.status_code == 200
    before = await snapshot(factory)
    closing = await client.patch(path, headers=headers['support'], json={'status': 'resolved', 'description': 'No debe guardarse'})
    assert closing.status_code == 422 and closing.json()['error']['code'] == 'RESOLUTION_REQUIRED'
    assert await snapshot(factory) == before
    final = await client.patch(path, headers=headers['support'], json={'status': 'resolved', 'resolution': 'Servicio recuperado'})
    assert final.status_code == 200
    result = final.json()
    assert result['resolved_at'] and result['description'] == inc['description']
    assert result['title'] == inc['title'] and result['created_by'] == inc['created_by']
    assert result['updated_at'] != inc['updated_at']
    before = await snapshot(factory)
    assert (await client.patch(path, headers=headers['admin'], json={'status': 'observing'})).status_code == 409
    assert await snapshot(factory) == before
    async with factory() as db:
        logs = (await db.scalars(select(models.AuditLog).where(models.AuditLog.entity_id == UUID(inc['id'])))).all()
        assert len(logs) == 3
        closing = next(log for log in logs if log.after['status'] == 'resolved')
        assert closing.before['status'] == 'observing' and closing.after['resolution'] == 'Servicio recuperado'
        assert all(log.actor_id for log in logs)

async def test_future_only_allowed_for_maintenance_and_maintenance_closes_completed(setup):
    client, headers, factory = setup
    future = payload(started_at=(now_utc()+timedelta(days=2)).isoformat())
    before = await snapshot(factory)
    rejected = await client.post(BASE, headers=headers['admin'], json=future)
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'STARTED_AT_FUTURE'
    assert await snapshot(factory) == before
    created = await client.post(BASE, headers=headers['admin'], json={**future, 'is_maintenance': True})
    assert created.status_code == 201
    inc = created.json(); path = f"{BASE}/{inc['id']}"
    assert inc['status'] == 'observing'
    for target in ('investigating', 'resolved'):
        assert (await client.patch(path, headers=headers['admin'], json={'status': target, 'resolution': 'Nota válida'})).status_code == 409
    assert (await client.patch(path, headers=headers['admin'], json={'status': 'completed'})).status_code == 422
    assert (await client.patch(path, headers=headers['admin'], json={'status': 'completed', 'resolution': 'Mantenimiento finalizado'})).status_code == 200

@pytest.mark.parametrize('changes', [{'title': '  a  '}, {'title': 'a'*161}, {'description': 'a'*4001},
    {'severity': 'critical'}, {'started_at': '2026-10-01T10:00:00'}, {'description': '   '}])
async def test_invalid_creation_preserves_data(setup, changes):
    client, headers, factory = setup
    before = await snapshot(factory)
    assert (await client.post(BASE, headers=headers['admin'], json=payload(**changes))).status_code == 422
    assert await snapshot(factory) == before

@pytest.mark.parametrize('body', [{}, {'description': None}, {'status': None}, {'resolution': None},
    {'resolution': ' '}, {'resolution': 'a'*2001}, {'description': 'a'*4001}])
async def test_invalid_patch_preserves_incident_audit_and_mail(setup, body):
    client, headers, factory = setup
    inc = (await client.post(BASE, headers=headers['admin'], json=payload())).json()
    before = await snapshot(factory)
    assert (await client.patch(f"{BASE}/{inc['id']}", headers=headers['admin'], json=body)).status_code == 422
    assert await snapshot(factory) == before

async def test_filters_pagination_and_empty_list(setup):
    client, headers, _ = setup
    for i in range(3):
        await client.post(BASE, headers=headers['admin'], json=payload(component_key='auth'))
    await client.post(BASE, headers=headers['admin'], json=payload(component_key='database', is_maintenance=True))
    await client.post(BASE, headers=headers['admin'], json=payload(started_at=(now_utc()-timedelta(days=40)).isoformat()))
    query = {'days': 30, 'component': 'auth', 'status': 'investigating', 'page_size': 2}
    first = (await client.get(BASE, headers=headers['analyst'], params=query)).json()
    second = (await client.get(BASE, headers=headers['analyst'], params={**query, 'page': 2})).json()
    assert first['total'] == second['total'] == 3 and len(first['items']) == 2 and len(second['items']) == 1
    assert not set(row['id'] for row in first['items']) & set(row['id'] for row in second['items'])
    empty = await client.get(BASE, headers=headers['analyst'], params={'status': 'completed'})
    assert empty.status_code == 200 and empty.json()['items'] == [] and empty.json()['total'] == 0
    assert (await client.get(BASE, headers=headers['analyst'], params={'days': 365})).json()['total'] == 5
    for params in ({'days': 0}, {'days': 366}, {'page': 0}, {'page_size': 101}, {'component': 'invalid'}, {'status': 'invalid'}):
        assert (await client.get(BASE, headers=headers['analyst'], params=params)).status_code == 422

async def test_optional_mail_queue_is_encrypted_transactional_and_delivered_once(setup, monkeypatch):
    client, headers, factory = setup
    monkeypatch.setattr(get_settings(), 'incident_mail_recipients', 'ops@example.org,ops@example.org,admin@example.org')
    calls = []
    monkeypatch.setattr(incident_mail, 'send_incident', lambda value: calls.append(value))
    inc = (await client.post(BASE, headers=headers['admin'], json=payload())).json()
    assert inc['notification_status'] == 'queued' and calls == []
    async with factory() as db:
        rows = (await db.scalars(select(models.IncidentEmail))).all()
        assert len(rows) == 2 and all(row.payload_encrypted.startswith('enc:') for row in rows)
        assert all('ops@example.org' not in row.payload_encrypted for row in rows)
    assert await incident_mail.deliver_pending()
    assert await incident_mail.deliver_pending()
    assert not await incident_mail.deliver_pending()
    assert len(calls) == 2
    async with factory() as db:
        incident = await db.get(models.Incident, UUID(inc['id']))
        assert incident.notification_status == 'sent'
        assert as_utc(incident.updated_at) == as_utc(datetime.fromisoformat(inc['updated_at']))
        assert all(row.payload_encrypted is None for row in (await db.scalars(select(models.IncidentEmail))).all())

async def test_mail_failures_retry_without_losing_incident(setup, monkeypatch):
    client, headers, factory = setup
    monkeypatch.setattr(get_settings(), 'incident_mail_recipients', 'ops@example.org')
    def fail(_): raise RuntimeError('Error de prueba')
    monkeypatch.setattr(incident_mail, 'send_incident', fail)
    inc = (await client.post(BASE, headers=headers['admin'], json=payload())).json()
    for _ in range(5):
        assert await incident_mail.deliver_pending()
        async with factory() as db:
            await db.execute(update(models.IncidentEmail).values(next_attempt_at=now_utc()-timedelta(seconds=1)))
            await db.commit()
    async with factory() as db:
        assert (await db.get(models.Incident, UUID(inc['id']))).notification_status == 'failed'
        row = await db.scalar(select(models.IncidentEmail))
        assert row.status == 'failed' and row.attempts == 5 and row.payload_encrypted is None

async def test_queue_rolled_back_with_incident(setup, monkeypatch):
    _, _, factory = setup
    monkeypatch.setattr(get_settings(), 'incident_mail_recipients', 'ops@example.org')
    async with factory() as db:
        inc = models.Incident(title='Temporal de prueba', description='No persistir', severity='degraded', status='investigating', started_at=now_utc())
        db.add(inc); await db.flush()
        await incident_mail.queue_incident(db, inc)
        await db.rollback()
    async with factory() as db:
        assert await db.scalar(select(models.Incident.id)) is None
        assert await db.scalar(select(models.IncidentEmail.id)) is None

async def test_invalid_mail_recipient_does_not_prevent_registration(setup, monkeypatch):
    client, headers, factory = setup
    monkeypatch.setattr(get_settings(), 'incident_mail_recipients', 'dirección inválida')
    response = await client.post(BASE, headers=headers['admin'], json=payload())
    assert response.status_code == 201 and response.json()['notification_status'] == 'not_configured'
    async with factory() as db:
        assert await db.scalar(select(models.IncidentEmail.id)) is None

async def test_incident_mail_uses_own_message_without_invitation_or_description(monkeypatch):
    messages = []
    monkeypatch.setattr(incident_mail, 'send_message_smtp', lambda message: messages.append(message))
    incident_mail.send_incident({'email': 'ops@example.org', 'id': 'id-test', 'title': 'Mantenimiento de prueba',
        'maintenance': True, 'severity': 'outage', 'started_at': '2026-10-26T12:00:00Z'})
    assert messages[0]['To'] == 'ops@example.org'
    assert 'mantenimiento' in messages[0]['Subject']
    assert 'Fuera de servicio' in messages[0].get_content()
    assert 'invitación' not in messages[0].get_content()
