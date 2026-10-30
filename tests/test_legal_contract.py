from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app import database, models
from app.database import Base
from app.security import create_access_token
from app.legal_documents import effective_at, earliest_major_date

BASE = '/api/v1/admin'
NOW = datetime(2026, 10, 27, 15, tzinfo=timezone.utc)
TEXT = '# Documento de prueba\n\n' + 'Condiciones de prueba para usuarios. ' * 5
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def legal_env(client, monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(database, '_session_factory', factory)
    clock = [NOW]
    monkeypatch.setattr('app.routers.system.now_utc', lambda: clock[0])
    async with factory() as db:
        admin = models.AdminUser(full_name='Admin legal', email='legal@example.cl', role='admin', is_active=True)
        old = models.LegalVersion(doc_type='terms', semver='1.0', status='published', content_md=TEXT,
                                  changelog='Versión inicial', effective_date=date(2026, 1, 1),
                                  published_at=NOW - timedelta(days=300), requires_reacceptance=True)
        db.add_all([admin, old]); await db.commit()
        headers = {'Authorization': 'Bearer ' + create_access_token(admin.id, 'admin')}
        original_id = str(old.id)
    yield factory, headers, clock, original_id
    await engine.dispose()


async def draft(client, headers, version, day, doc='terms'):
    return await client.post(BASE + f'/legal/documents/{doc}/versions', headers=headers,
                             json={'semver': version, 'content_md': TEXT, 'changelog': 'Resumen de los cambios', 'effective_date': day})


async def publish(client, headers, identity):
    return await client.post(BASE + f'/legal/versions/{identity}/publish', headers=headers)


async def document(client, headers):
    result = await client.get(BASE + '/legal/documents?doc_type=terms', headers=headers)
    assert result.status_code == 200, result.text
    return result.json()['documents'][0]


async def test_scheduled_current_history_midnight_and_immutable_text(client, legal_env):
    _, headers, clock, old_id = legal_env
    created = await draft(client, headers, '1.1', '2026-10-28')
    assert created.status_code == 201, created.text
    identity = created.json()['version_id']
    assert not created.json()['requires_reacceptance']
    assert (await publish(client, headers, identity)).status_code == 200
    before = await document(client, headers)
    assert before['current']['version_id'] == old_id
    assert next(row for row in before['versions'] if row['version_id'] == identity)['display_state'] == 'scheduled'
    boundary = effective_at(date(2026, 10, 28))
    assert boundary == datetime(2026, 10, 28, 3, tzinfo=timezone.utc)
    clock[0] = boundary - timedelta(seconds=1)
    assert (await document(client, headers))['current']['version_id'] == old_id
    clock[0] = boundary
    after = await document(client, headers)
    assert after['current']['version_id'] == identity
    old = next(row for row in after['versions'] if row['version_id'] == old_id)
    assert old['display_state'] == 'historical' and old['content_md'] == TEXT
    duplicate = await publish(client, headers, identity)
    assert duplicate.status_code == 409 and duplicate.json()['error']['code'] == 'ALREADY_PUBLISHED'
    logs = (await client.get(BASE + '/audit-log', headers=headers, params={'entity_id': identity})).json()['items']
    assert len(logs) == 2 and {row['action'] for row in logs} == {'legal.version_create', 'legal.version_publish'}


async def test_numeric_order_multiple_future_versions_and_date_order(client, legal_env):
    _, headers, _, _ = legal_env
    for number, day in [('1.9', '2026-10-29'), ('1.10', '2026-10-30')]:
        created = await draft(client, headers, number, day)
        assert created.status_code == 201, created.text
        assert (await publish(client, headers, created.json()['version_id'])).status_code == 200
    result = await document(client, headers)
    assert result['current']['semver'] == '1.0'
    assert [row['semver'] for row in result['versions'] if row['display_state'] == 'scheduled'] == ['1.10', '1.9']
    for number in ['1.8', '01.10']:
        rejected = await draft(client, headers, number, '2026-10-31')
        assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'SEMVER_NOT_GREATER'
    rejected = await draft(client, headers, '1.11', '2026-10-30')
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'EFFECTIVE_DATE_ORDER'


async def test_notice_rechecked_at_publication_and_past_date_preserves_draft(client, legal_env):
    factory, headers, clock, _ = legal_env
    day = earliest_major_date(NOW)
    created = await draft(client, headers, '2.0', day.isoformat())
    assert created.status_code == 201 and created.json()['requires_reacceptance']
    identity = created.json()['version_id']
    clock[0] = NOW + timedelta(days=2)
    rejected = await publish(client, headers, identity)
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'NOTICE_PERIOD'
    clock[0] = NOW
    minor = (await draft(client, headers, '1.1', '2026-10-28')).json()
    clock[0] = NOW + timedelta(days=5)
    expired = await publish(client, headers, minor['version_id'])
    assert expired.status_code == 409 and expired.json()['error']['code'] == 'EFFECTIVE_DATE_PAST'
    async with factory() as db:
        rows = (await db.scalars(select(models.LegalVersion).where(models.LegalVersion.status == 'draft'))).all()
        assert len(rows) == 2 and all(row.published_at is None for row in rows)


async def test_stale_draft_cannot_publish_behind_later_version(client, legal_env):
    _, headers, _, _ = legal_env
    lower = (await draft(client, headers, '1.1', '2026-10-28')).json()
    higher = (await draft(client, headers, '1.2', '2026-10-29')).json()
    assert (await publish(client, headers, higher['version_id'])).status_code == 200
    rejected = await publish(client, headers, lower['version_id'])
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'SEMVER_NOT_GREATER'


async def test_major_requires_fifteen_complete_days(client, legal_env):
    _, headers, clock, _ = legal_env
    boundary = effective_at(date(2026, 11, 12))
    clock[0] = boundary - timedelta(days=15) + timedelta(seconds=1)
    rejected = await draft(client, headers, '2.0', '2026-11-12')
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'NOTICE_PERIOD'
    clock[0] = boundary - timedelta(days=15)
    created = await draft(client, headers, '2.0', '2026-11-12')
    assert created.status_code == 201
    assert (await publish(client, headers, created.json()['version_id'])).status_code == 200


@pytest.mark.parametrize('role', ['admin', 'analyst', 'support', 'editor', 'moderator', None])
async def test_admin_exclusivity_for_all_legal_operations(client, legal_env, role):
    factory, _, _, _ = legal_env
    async with factory() as db:
        actor = models.AdminUser(full_name='Rol de prueba', email=f'{uuid4()}@example.cl', role=role or 'admin', is_active=True)
        version = models.LegalVersion(doc_type='privacy', semver='1.0', content_md=TEXT, changelog='Cambio inicial',
                                      effective_date=earliest_major_date(NOW), status='draft')
        db.add_all([actor, version]); await db.commit()
        headers = {'Authorization': 'Bearer ' + create_access_token(actor.id, role)} if role else {}
        identity = str(version.id)
    expected = 200 if role == 'admin' else 403 if role else 401
    assert (await client.get(BASE + '/legal/documents', headers=headers)).status_code == expected
    created = await draft(client, headers, '1.1', '2026-11-30', doc='privacy')
    assert created.status_code == (201 if role == 'admin' else expected)
    assert (await publish(client, headers, identity)).status_code == expected


@pytest.mark.parametrize('change', [
    {'semver': '1.1.0'}, {'semver': '123456789.1'}, {'semver': 'a.1'}, {'content_md': ' ' * 101},
    {'changelog': 'corto'}, {'changelog': 'x' * 2001}, {'status': 'published'},
])
async def test_invalid_draft_has_no_side_effects(client, legal_env, change):
    factory, headers, _, _ = legal_env
    body = {'semver': '1.1', 'content_md': TEXT, 'changelog': 'Resumen de cambios', 'effective_date': '2026-10-29', **change}
    rejected = await client.post(BASE + '/legal/documents/terms/versions', headers=headers, json=body)
    assert rejected.status_code == 422
    async with factory() as db:
        assert len((await db.scalars(select(models.LegalVersion))).all()) == 1
