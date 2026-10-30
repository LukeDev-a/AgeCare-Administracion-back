from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from app import database, models
from app.config import get_settings
from app.database import Base
from app.end_users_demo import demo_id, seed_demo_directory
from app.security import create_access_token, now_utc

BASE = '/api/v1/admin'
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def directory(client, monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, '_engine', engine)
    monkeypatch.setattr(database, '_session_factory', factory)
    monkeypatch.setattr(get_settings(), 'environment', 'dev')
    monkeypatch.setattr(get_settings(), 'end_users_demo_enabled', True)
    async with factory() as db:
        admin = models.AdminUser(full_name='Administrador interno', email='staff@example.cl', role='admin', is_active=True)
        db.add(admin); await db.flush()
        await seed_demo_directory(db); await db.commit()
        headers = {'Authorization': 'Bearer ' + create_access_token(admin.id, 'admin')}
        admin_id = admin.id
    yield factory, headers, admin_id
    await engine.dispose()


async def test_search_paging_literal_filters_and_staff_separation(client, directory):
    factory, headers, admin_id = directory
    first = (await client.get(BASE + '/end-users', headers=headers)).json()
    second = (await client.get(BASE + '/end-users?page=2', headers=headers)).json()
    assert first['data_origin'] == 'demo' and first['deactivation_effect'] == 'demo_only'
    assert first['total'] == second['total'] == 32
    assert len(first['items']) == 25 and len(second['items']) == 7
    assert {r['user_id'] for r in first['items']}.isdisjoint(r['user_id'] for r in second['items'])
    for query, count in [('PERSONA01@EXAMPLE.TEST', 1), ('Persona de prueba 01', 1), ('%', 0), ('_', 0), ('sin coincidencias', 0)]:
        response = await client.get(BASE + '/end-users', headers=headers, params={'q': query})
        assert response.status_code == 200 and response.json()['total'] == count
    inactive = (await client.get(BASE + '/end-users?is_active=false', headers=headers)).json()
    assert inactive['total'] == 1 and inactive['items'][0]['is_active'] is False
    internal = (await client.get(BASE + '/users', headers=headers)).json()['items']
    assert len(internal) == 1 and internal[0]['email'] == 'staff@example.cl'
    assert not any(r['email'] == 'staff@example.cl' for r in first['items'] + second['items'])
    assert (await client.post(BASE + '/end-users/'+str(admin_id)+'/deactivate', headers=headers,
        json={'confirmation_user_id': str(admin_id), 'reason': 'No afectar personal'})).status_code == 404
    async with factory() as db:
        assert (await db.get(models.AdminUser, admin_id)).is_active


async def test_patient_search_unique_by_linked_email_and_minimal_detail(client, directory):
    factory, headers, _ = directory
    filtered = (await client.get(BASE + '/patients', headers=headers, params={'q': 'persona01@example.test'})).json()
    assert filtered['total'] == 2 and len(filtered['items']) == 2
    broad = (await client.get(BASE + '/patients', headers=headers, params={'q': '@example.test'})).json()
    assert broad['total'] == 6 and len({r['patient_id'] for r in broad['items']}) == 6
    user = (await client.get(BASE + '/end-users/' + str(demo_id('user-1')), headers=headers)).json()
    assert {m['role'] for m in user['memberships']} == {'family', 'caregiver'}
    assert 'role' not in user  # El perfil pertenece a cada vínculo.
    patient = (await client.get(BASE + '/patients/' + str(demo_id('patient-1')), headers=headers)).json()
    assert len(patient['members']) == 4 and {m['role'] for m in patient['members']} == {'family', 'caregiver', 'elder', 'doctor'}
    empty = (await client.get(BASE + '/patients/' + str(demo_id('patient-7')), headers=headers)).json()
    assert empty['members'] == [] and empty['members_count'] == 0
    for sensitive in ('password', 'token', 'conditions', 'birth_date', 'prescriptions', 'notes'):
        assert sensitive not in str(user) and sensitive not in str(patient)
    async with factory() as db:
        logs = (await db.scalars(select(models.AuditLog))).all()
        assert {r.action for r in logs} == {'patients.demo_list', 'end_users.demo_read', 'patients.demo_read'}
        assert len(logs) == 5 and all(r.before is None and r.after is None for r in logs)
        assert all('persona01@example.test' not in str(r.event_metadata) for r in logs)


async def test_deactivate_demo_preserves_links_internal_sessions_and_audits_atomically(client, directory):
    factory, headers, admin_id = directory
    identity = demo_id('user-1')
    async with factory() as db:
        session = models.AdminSession(admin_id=admin_id, refresh_hash='test-hash', expires_at=now_utc())
        db.add(session); await db.commit()
        session_id = session.id
    url = BASE + '/end-users/' + str(identity) + '/deactivate'
    result = await client.post(url, headers=headers, json={'confirmation_user_id': str(identity), 'reason': '  Solicitud de prueba  '})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['data_origin'] == 'demo' and data['mobile_sessions_revoked'] is False
    assert data['user']['is_active'] is False and len(data['user']['memberships']) == 2
    assert data['user']['deactivation_reason'] == 'Solicitud de prueba' and data['user']['deactivated_at'].endswith('Z')
    async with factory() as db:
        assert (await db.get(models.AdminSession, session_id)).revoked_at is None
        assert (await db.get(models.AdminUser, admin_id)).is_active
        assert await db.scalar(select(func.count()).select_from(models.DemoPatient)) == 7
        assert await db.scalar(select(func.count()).select_from(models.DemoPatientMember)) == 14
        log = await db.scalar(select(models.AuditLog).where(models.AuditLog.action == 'end_users.demo_deactivate'))
        assert log.before['is_active'] is True and log.after['is_active'] is False
        assert log.after['effect'] == 'demo_only' and log.after['reason'] == 'Solicitud de prueba'
        assert log.actor_id == admin_id and log.actor_role == 'admin'
    assert (await client.post(url, headers=headers, json={'confirmation_user_id': str(identity), 'reason': 'Segundo intento'})).json()['error']['code'] == 'ACCOUNT_ALREADY_INACTIVE'
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(models.AuditLog)) == 1
    # Las membresías/otros miembros del círculo no se desactivan.
    patient = (await client.get(BASE + '/patients/' + str(demo_id('patient-1')), headers=headers)).json()
    assert sum(not m['is_active'] for m in patient['members']) == 1


@pytest.mark.parametrize('body', [
    {'reason': 'Válido pero sin confirmar'}, {'reason': '   '}, {'reason': 'abcd'}, {'reason': 'a'*501},
    {'reason': None}, {'reason': 'Motivo correcto', 'is_active': True},
])
async def test_invalid_deactivation_has_no_effect(client, directory, body):
    factory, headers, _ = directory
    identity = demo_id('user-1')
    payload = {'confirmation_user_id': str(identity), **body}
    if body == {'reason': 'Válido pero sin confirmar'}:
        payload.pop('confirmation_user_id')
    response = await client.post(BASE + '/end-users/' + str(identity) + '/deactivate', headers=headers, json=payload)
    assert response.status_code == 422
    async with factory() as db:
        assert (await db.get(models.DemoEndUser, identity)).is_active
        assert await db.scalar(select(func.count()).select_from(models.AuditLog)) == 0


async def test_wrong_confirmation_missing_ids_and_limits(client, directory):
    factory, headers, _ = directory
    identity = demo_id('user-1')
    response = await client.post(BASE + '/end-users/' + str(identity) + '/deactivate', headers=headers,
        json={'confirmation_user_id': str(uuid4()), 'reason': 'Solicitud válida'})
    assert response.status_code == 422 and response.json()['error']['code'] == 'CONFIRMATION_MISMATCH'
    for path in ('/end-users/', '/patients/'):
        assert (await client.get(BASE + path + str(uuid4()), headers=headers)).status_code == 404
    for path in ('/end-users?page_size=101', '/patients?page=0', '/end-users?is_active=invalid', '/patients?q='+'a'*121):
        assert (await client.get(BASE + path, headers=headers)).status_code == 422
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(models.AuditLog)) == 0


@pytest.mark.parametrize('role,expected', [(None, 401), ('analyst', 403), ('support', 403), ('editor', 403), ('moderator', 403), ('admin', 200)])
async def test_only_admin_and_no_extra_management_routes(client, directory, role, expected):
    factory, headers, _ = directory
    if role != 'admin':
        async with factory() as db:
            actor = models.AdminUser(full_name='Rol de prueba', email=f'{uuid4()}@example.cl', role=role or 'admin', is_active=True)
            db.add(actor); await db.commit()
            headers = {'Authorization': 'Bearer ' + create_access_token(actor.id, role)} if role else {}
    for path in ('/end-users', '/patients', '/end-users/'+str(demo_id('user-1')), '/patients/'+str(demo_id('patient-1'))):
        assert (await client.get(BASE + path, headers=headers)).status_code == expected
    result = await client.post(BASE + '/end-users/'+str(demo_id('user-1'))+'/deactivate', headers=headers,
        json={'confirmation_user_id': str(demo_id('user-1')), 'reason': 'Prueba de permisos'})
    assert result.status_code == expected
    if expected != 200:
        async with factory() as db:
            assert (await db.get(models.DemoEndUser, demo_id('user-1'))).is_active
            assert await db.scalar(select(func.count()).select_from(models.AuditLog)) == 0
    if role == 'admin':
        for method, path in [('post', '/end-users'), ('patch', '/end-users/'+str(demo_id('user-1'))),
                             ('delete', '/patients/'+str(demo_id('patient-1'))), ('post', '/end-users/'+str(demo_id('user-1'))+'/reactivate')]:
            assert (await getattr(client, method)(BASE + path, headers=headers)).status_code in (404, 405)


@pytest.mark.parametrize('environment,enabled', [('prod', True), ('staging', True), ('dev', False)])
async def test_not_available_outside_explicit_dev_demo(client, directory, monkeypatch, environment, enabled):
    factory, headers, _ = directory
    monkeypatch.setattr(get_settings(), 'environment', environment)
    monkeypatch.setattr(get_settings(), 'end_users_demo_enabled', enabled)
    for path in ('/end-users', '/patients', '/end-users/'+str(demo_id('user-1'))):
        response = await client.get(BASE + path, headers=headers)
        assert response.status_code == 503 and response.json()['error']['code'] == 'END_USERS_UNAVAILABLE'
    assert (await client.post(BASE + '/end-users/'+str(demo_id('user-1'))+'/deactivate', headers=headers,
        json={'confirmation_user_id': str(demo_id('user-1')), 'reason': 'No modificar fuera de demo'})).status_code == 503
    async with factory() as db:
        assert await seed_demo_directory(db) is False
        assert (await db.get(models.DemoEndUser, demo_id('user-1'))).is_active
        assert await db.scalar(select(func.count()).select_from(models.AuditLog)) == 0


async def test_safe_demo_seed_preserves_changes_and_partial_group(directory):
    factory, _, _ = directory
    async with factory() as db:
        user = await db.get(models.DemoEndUser, demo_id('user-1'))
        user.is_active = False; user.deactivation_reason = 'Conservar modificación'
        await db.commit()
        assert await seed_demo_directory(db) is False
        await db.commit()
        assert (await db.get(models.DemoEndUser, user.id)).deactivation_reason == 'Conservar modificación'
    # Grupo parcialmente poblado: no rellenar datos faltantes.
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine)() as db:
        db.add(models.DemoPatient(full_name='Ejemplo existente'))
        await db.commit()
        assert await seed_demo_directory(db) is False
        assert await db.scalar(select(func.count()).select_from(models.DemoEndUser)) == 0
    await engine.dispose()


async def test_audit_failure_rolls_back_demo_deactivation(client, directory, monkeypatch):
    factory, headers, _ = directory
    identity = demo_id('user-1')
    async def fail_audit(*args, **kwargs):
        raise RuntimeError('Fallo aislado de auditoría')
    monkeypatch.setattr('app.routers.end_users.audit', fail_audit)
    with pytest.raises(RuntimeError):
        await client.post(BASE + '/end-users/'+str(identity)+'/deactivate', headers=headers,
                          json={'confirmation_user_id': str(identity), 'reason': 'Prueba de rollback'})
    async with factory() as db:
        user = await db.get(models.DemoEndUser, identity)
        assert user.is_active and user.deactivated_at is None
        assert await db.scalar(select(func.count()).select_from(models.AuditLog)) == 0


async def test_compose_safe_seed_loads_empty_directory_and_preserves_deactivation(directory, monkeypatch):
    from scripts.seed import seed
    factory, _, _ = directory
    monkeypatch.setattr(get_settings(), 'seed_demo_enabled', True)
    async with factory() as db:
        for model in (models.DemoPatientMember, models.DemoEndUser, models.DemoPatient):
            await db.execute(delete(model))
        db.add(models.AuditLog(action='staff.create', actor_name='Historia existente'))
        await db.commit()
    await seed(only_empty=True)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(models.DemoEndUser)) == 32
        user = await db.get(models.DemoEndUser, demo_id('user-1'))
        user.is_active = False; user.deactivation_reason = 'No reactivar en arranque'
        await db.commit()
    await seed(only_empty=True)
    async with factory() as db:
        assert not (await db.get(models.DemoEndUser, demo_id('user-1'))).is_active
        assert await db.scalar(select(func.count()).select_from(models.AuditLog)) == 1
