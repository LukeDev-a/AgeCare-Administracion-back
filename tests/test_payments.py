from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from app import database, models
from app.database import Base
from app.config import get_settings
from app.end_users_demo import seed_demo_directory
from app.security import create_access_token

BASE = '/api/v1/admin/payments'
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def payments(client, monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, '_engine', engine)
    monkeypatch.setattr(database, '_session_factory', factory)
    monkeypatch.setattr(get_settings(), 'environment', 'dev')
    monkeypatch.setattr(get_settings(), 'end_users_demo_enabled', True)
    async with factory() as db:
        admin = models.AdminUser(full_name='Administrador', email='admin@example.test', role='admin', is_active=True)
        db.add(admin); await db.flush()
        await seed_demo_directory(db); await db.commit()
        headers = {'Authorization': 'Bearer '+create_access_token(admin.id, 'admin')}
    yield factory, headers
    await engine.dispose()


async def start(client, headers):
    response = await client.post(BASE+'/initialize', headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def operation(action, row, **kwargs):
    return dict(action=action, version=row['version'], reason='Solicitud revisada por administración', confirmed=True, **kwargs)


async def test_initialize_preserves_directory_and_is_idempotent(client, payments):
    factory, headers = payments
    assert (await client.get(BASE, headers=headers)).json()['subscriptions'] == []
    data = await start(client, headers)
    assert len(data['subscriptions']) == 32 and len(data['charges']) == 64
    assert data == await start(client, headers)
    assert data == (await client.get(BASE, headers=headers)).json()
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(models.AppAccount)) == 32
        audits = (await db.scalars(select(models.AuditLog).where(models.AuditLog.action == 'payments.initialize'))).all()
        assert len(audits) == 1
        s = data['subscriptions'][0]
        from uuid import UUID
        account = await db.get(models.AppAccount, UUID(s['userId']))
        assert account.full_name == s['name'] and account.email == s['email']
        account.full_name = 'Nombre actualizado'; await db.commit()
    assert (await client.get(BASE, headers=headers)).json()['subscriptions'][0]['name'] == 'Nombre actualizado'


async def test_cancel_extend_refund_persist_across_new_requests_and_audit(client, payments):
    factory, headers = payments
    data = await start(client, headers)
    s = next(s for s in data['subscriptions'] if s['state'] == 'active')
    url = BASE+'/subscriptions/'+s['id']+'/operate'
    extended = await client.post(url, headers=headers, json=operation('extend', s, days=7))
    assert extended.status_code == 200, extended.text
    updated = next(r for r in extended.json()['subscriptions'] if r['id'] == s['id'])
    from datetime import datetime
    assert (datetime.fromisoformat(updated['endsAt'])-datetime.fromisoformat(s['endsAt'])).days == 7
    assert updated['version'] == 2 and len(updated['history']) == 1
    stale = await client.post(url, headers=headers, json=operation('cancel', s))
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'VERSION_CONFLICT'
    cancelled = await client.post(url, headers=headers, json=operation('cancel', updated))
    assert cancelled.status_code == 200
    c = next(c for c in data['charges'] if c['state'] == 'approved')
    refund_url = BASE+'/charges/'+c['id']+'/operate'
    refunded = await client.post(refund_url, headers=headers, json=operation('refund', c))
    assert refunded.status_code == 200
    saved = (await client.get(BASE, headers=headers)).json()
    s_after = next(r for r in saved['subscriptions'] if r['id'] == s['id'])
    c_after = next(r for r in saved['charges'] if r['id'] == c['id'])
    assert s_after['state'] == 'cancelled' and s_after['endsAt'] == updated['endsAt']
    assert len(s_after['history']) == 2 and c_after['state'] == 'refunded'
    assert (await client.post(refund_url, headers=headers, json=operation('refund', c_after))).status_code == 409
    async with factory() as db:
        actions = set((await db.scalars(select(models.AuditLog.action).where(models.AuditLog.action.like('payments.%')))).all())
        assert actions == {'payments.initialize', 'payments.read', 'payments.cancel', 'payments.extend', 'payments.refund'}
        assert await db.scalar(select(func.count()).select_from(models.AppAccount).where(models.AppAccount.is_active)) == 31


async def test_invalid_requests_do_not_modify_records(client, payments):
    _, headers = payments
    data = await start(client, headers)
    s = next(s for s in data['subscriptions'] if s['state'] == 'active')
    url = BASE+'/subscriptions/'+s['id']+'/operate'
    for patch in [dict(confirmed=False), dict(confirmed='true'), dict(reason='hola'), dict(reason='x'*501),
                  dict(version=0), dict(version=True), dict(action='refund'), dict(days=5), dict(extra=True)]:
        body = operation('cancel', s); body.update(patch)
        assert (await client.post(url, headers=headers, json=body)).status_code == 422
    for days in [0, 91, 1.5, True, '7', None]:
        assert (await client.post(url, headers=headers, json=operation('extend', s, days=days))).status_code == 422
    assert (await client.get(BASE, headers=headers)).json() == data
    assert (await client.post(BASE+'/subscriptions/'+str(uuid4())+'/operate', headers=headers, json=operation('cancel', s))).status_code == 404


async def test_permissions_and_demo_guard(client, payments):
    factory, headers = payments
    assert (await client.get(BASE)).status_code == 401
    for role in ['editor', 'analyst', 'support', 'moderator']:
        async with factory() as db:
            user = models.AdminUser(full_name=role, email=role+'@example.test', role=role, is_active=True)
            db.add(user); await db.commit()
            other = {'Authorization': 'Bearer '+create_access_token(user.id, role)}
        assert (await client.get(BASE, headers=other)).status_code == 403
        assert (await client.post(BASE+'/initialize', headers=other)).status_code == 403
        assert (await client.post(BASE+'/subscriptions/'+str(uuid4())+'/operate', headers=other,
            json={'action': 'cancel', 'version': 1, 'reason': 'Intento sin acceso', 'confirmed': True})).status_code == 403
    get_settings().end_users_demo_enabled = False
    assert (await client.get(BASE, headers=headers)).status_code == 503
    assert (await client.post(BASE+'/initialize', headers=headers)).status_code == 503


async def test_rollback_when_audit_fails(client, payments, monkeypatch):
    from app.routers import payments as router
    original_audit = router.audit
    _, headers = payments
    data = await start(client, headers)
    s = next(s for s in data['subscriptions'] if s['state'] == 'active')
    async def fail(*args, **kwargs):
        raise RuntimeError('Fallo de auditoría simulado')
    monkeypatch.setattr(router, 'audit', fail)
    with pytest.raises(RuntimeError):
        await client.post(BASE+'/subscriptions/'+s['id']+'/operate', headers=headers, json=operation('cancel', s))
    monkeypatch.setattr(router, 'audit', original_audit)
    assert (await client.get(BASE, headers=headers)).json() == data
