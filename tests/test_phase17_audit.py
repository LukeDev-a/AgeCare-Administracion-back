from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app import database, models
from app.audit import audit
from app.database import Base
from app.security import create_access_token, hash_password, now_utc

BASE = '/api/v1/admin'
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def audit_env(client, monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(database, '_session_factory', factory)
    async with factory() as db:
        actor = models.AdminUser(full_name='Actor histórico', email='audit@example.cl', role='admin',
                                 is_active=True, password_hash=hash_password('Prueba123!'))
        db.add(actor); await db.commit()
        identity = actor.id
        headers = {'Authorization': 'Bearer ' + create_access_token(identity, 'admin')}
    yield factory, headers, identity
    await engine.dispose()


async def test_success_failure_unknown_locked_and_secret_exclusion(client, audit_env):
    factory, headers, identity = audit_env
    body = {'email': 'audit@example.cl', 'password': 'Prueba123!'}
    assert (await client.post(BASE + '/auth/login', json=body, headers={'User-Agent': 'Audit test'})).status_code == 200
    assert (await client.post(BASE + '/auth/login', json={**body, 'password': 'Incorrecta123!'})).status_code == 401
    assert (await client.post(BASE + '/auth/login', json={**body, 'email': 'unknown@example.cl'})).status_code == 401
    async with factory() as db:
        actor = await db.get(models.AdminUser, identity)
        actor.locked_until = now_utc() + timedelta(minutes=15)
        await db.commit()
    assert (await client.post(BASE + '/auth/login', json=body)).status_code == 423
    result = await client.get(BASE + '/audit-log', headers=headers)
    rows = result.json()['items']
    assert len(rows) == 4
    assert next(r for r in rows if r['action'] == 'auth.login')['user_agent'] == 'Audit test'
    assert all(r['ip'] and r['created_at'].endswith('Z') for r in rows)
    assert any(r['actor']['admin_id'] is None for r in rows)
    assert any(r['metadata']['reason'] == 'ACCOUNT_LOCKED' for r in rows if r['action'] == 'auth.login_failed')
    for secret in ('Prueba123!', 'Incorrecta123!', 'unknown@example.cl', 'refresh_token', 'password_hash'):
        assert secret not in result.text


async def test_mfa_and_recovery_rejections_are_audited_without_changing_failure_policy(client, audit_env):
    factory, headers, identity = audit_env
    async with factory() as db:
        actor = await db.get(models.AdminUser, identity)
        actor.mfa_enabled = True
        await db.commit()
    body = {'email': 'audit@example.cl', 'password': 'Prueba123!'}
    for extra, reason in [({}, 'OTP_REQUIRED'), ({'otp_code': '000000'}, 'OTP_INVALID'), ({'recovery_code': 'WRONG-RECOVERY-CODE'}, 'OTP_INVALID')]:
        response = await client.post(BASE + '/auth/login', json={**body, **extra})
        assert response.json()['error']['code'] == reason
    async with factory() as db:
        rows = (await db.scalars(select(models.AuditLog))).all()
        assert len(rows) == 3 and {r.event_metadata['reason'] for r in rows} == {'OTP_REQUIRED', 'OTP_INVALID'}
        assert (await db.get(models.AdminUser, identity)).failed_attempts == 2
        assert '000000' not in str([r.after for r in rows])


async def test_sensitive_read_logs_each_requested_page_but_not_navigation(client, audit_env):
    factory, headers, identity = audit_env
    async with factory() as db:
        ticket = models.Ticket(number=9001, subject='Consulta', description='Texto privado no duplicado',
                               requester_name='Solicitante', requester_email='requester@example.cl',
                               category='other', priority='low', status='open', channel='console')
        db.add(ticket); await db.commit()
        ticket_id = str(ticket.id)
    assert (await client.get(BASE + '/support/tickets/' + ticket_id, headers=headers)).status_code == 200
    for page in (1, 2):
        assert (await client.get(BASE + '/support/tickets/' + ticket_id + '/replies', headers=headers, params={'page': page})).status_code == 200
    assert (await client.get(BASE + '/support/tickets/' + str(uuid4()) + '/replies', headers=headers)).status_code == 404
    result = (await client.get(BASE + '/audit-log', headers=headers, params={'action': 'ticket.conversation_read', 'entity_id': ticket_id})).json()
    assert result['total'] == 2
    assert {r['metadata']['page'] for r in result['items']} == {1, 2}
    assert all(r['before'] is None and r['after'] is None and r['actor']['admin_id'] == str(identity) for r in result['items'])
    assert 'Texto privado' not in str(result)


async def test_historical_actor_survives_permanent_account_deletion(client, audit_env):
    factory, headers, _ = audit_env
    async with factory() as db:
        actor = models.AdminUser(full_name='Nombre eliminado', email='deleted@example.cl', role='editor', is_active=True)
        db.add(actor); await db.flush()
        identity = actor.id
        request = Request({'type': 'http', 'method': 'POST', 'headers': []})
        await audit(db, request, 'games.create', 'game_app', uuid4(), actor=actor, after={'title': 'Juego histórico'})
        await db.commit()
    assert (await client.delete(BASE + '/users/' + str(identity), headers=headers)).status_code == 204
    result = (await client.get(BASE + '/audit-log', headers=headers, params={'actor_id': str(identity)})).json()
    assert result['total'] == 1
    assert result['items'][0]['actor'] == {'admin_id': str(identity), 'name': 'Nombre eliminado', 'role': 'editor'}


async def test_read_masks_legacy_secrets_and_drops_untrusted_metadata(client, audit_env):
    factory, headers, _ = audit_env
    async with factory() as db:
        db.add(models.AuditLog(action='settings.update', before={'nested': [{'SMTP_PASSWORD': 'OLDSECRET'}]},
                               after={'GEMINI_API_KEY': 'OLDKEY', 'qr_data_url': 'QRSECRET', 'ADMIN_ENCRYPTION_KEY': 'CIPHERSECRET'},
                               event_metadata={'path': '/internal', 'token': 'HIDDEN'}))
        await db.commit()
    response = await client.get(BASE + '/audit-log', headers=headers)
    assert 'OLDSECRET' not in response.text and 'OLDKEY' not in response.text and 'HIDDEN' not in response.text
    assert 'QRSECRET' not in response.text and 'CIPHERSECRET' not in response.text
    assert response.json()['items'][0]['metadata'] == {}
    assert (await client.get(BASE + '/audit-log', headers=headers, params={'q': 'OLDSECRET'})).json()['total'] == 0


async def test_date_defaults_single_bound_limits_and_entity_filters(client, audit_env):
    factory, headers, _ = audit_env
    now = now_utc()
    ids = [uuid4(), uuid4()]
    async with factory() as db:
        for days, identity in [(1, ids[0]), (80, ids[1])]:
            db.add(models.AuditLog(action='games.create', entity_type='game_app', entity_id=identity, created_at=now-timedelta(days=days)))
        await db.commit()
    assert (await client.get(BASE + '/audit-log', headers=headers)).json()['total'] == 1
    assert (await client.get(BASE + '/audit-log', headers=headers, params={'date_to': now.isoformat()})).json()['total'] == 2
    assert (await client.get(BASE + '/audit-log', headers=headers, params={'entity_type': 'game_app', 'entity_id': str(ids[0])})).json()['total'] == 1
    for path in ('/audit-log', '/audit-log/export'):
        for params, code in [({'date_from': (now-timedelta(days=91)).isoformat()}, 'RANGE_TOO_WIDE'),
                             ({'date_from': (now+timedelta(days=1)).isoformat()}, 'INVALID_DATE_RANGE')]:
            response = await client.get(BASE + path, headers=headers, params=params)
            assert response.status_code == 422 and response.json()['error']['code'] == code
        assert (await client.get(BASE + path, headers=headers, params={'date_from': (now-timedelta(days=90)).isoformat(), 'date_to': now.isoformat()})).status_code == 200


@pytest.mark.parametrize('role,status', [(None, 401), ('analyst', 403), ('support', 403), ('editor', 403), ('moderator', 403), ('admin', 200)])
async def test_audit_exclusive_admin_no_mutation_endpoints(client, audit_env, role, status):
    factory, _, _ = audit_env
    async with factory() as db:
        actor = models.AdminUser(full_name='Rol', email=f'{uuid4()}@example.cl', role=role or 'admin', is_active=True)
        db.add(actor); await db.commit()
        headers = {'Authorization': 'Bearer ' + create_access_token(actor.id, role)} if role else {}
    for path in ('/audit-log', '/audit-log/export'):
        assert (await client.get(BASE + path, headers=headers)).status_code == status
    if role == 'admin':
        for method in ('post', 'put', 'patch', 'delete'):
            assert (await getattr(client, method)(BASE + '/audit-log', headers=headers)).status_code == 405
