import asyncio
import importlib.util
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app import database, models
from app.errors import ApiError
from app.runtime_settings import SettingsCache, cache

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/admin'


def migration():
    spec = importlib.util.spec_from_file_location('runtime_migration', 'alembic/versions/0016_runtime_settings.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest_asyncio.fixture
async def runtime_rows(client):
    module = migration()
    keys = ('feature_flags', 'system_texts')
    originals = []
    async with database.get_session_factory()() as db:
        assert db.bind.url.drivername == 'sqlite+aiosqlite'
        for key in keys:
            existing = await db.get(models.SystemSetting, key)
            if existing:
                originals.append({column.name: getattr(existing, column.name) for column in existing.__table__.columns})
        await db.execute(delete(models.SystemSetting).where(models.SystemSetting.key.in_(keys)))
        db.add_all([
            models.SystemSetting(key='feature_flags', description='Funciones', value_schema=module.FEATURE_SCHEMA,
                value={'news_collection_enabled': True, 'news_adaptation_enabled': True}),
            models.SystemSetting(key='system_texts', description='Aviso', value_schema=module.NOTICE_SCHEMA,
                value={'notice_enabled': False, 'notice_title': '', 'notice_body': ''}),
        ])
        await db.commit()
    cache.entries.clear(); cache.locks.clear(); cache.generations.clear()
    yield
    async with database.get_session_factory()() as db:
        await db.execute(delete(models.SystemSetting).where(models.SystemSetting.key.in_(keys)))
        db.add_all([models.SystemSetting(**row) for row in originals]); await db.commit()
    cache.entries.clear(); cache.locks.clear(); cache.generations.clear()


async def change(client, headers, key, value):
    current = (await client.get(f'{BASE}/settings', params={'key': key}, headers=headers)).json()['settings'][0]
    return await client.put(f'{BASE}/settings/{key}', headers=headers,
        json={'version': current['version'], 'value': value, 'change_note': 'Ajuste operativo de prueba'})


async def test_notice_reaches_reader_after_commit_and_rejects_empty_active_text(client, admin_headers, analyst_headers, runtime_rows):
    assert (await client.get(f'{BASE}/runtime/notice')).status_code == 401
    assert (await client.get(f'{BASE}/runtime/notice', headers=analyst_headers)).json()['enabled'] is False
    value = {'notice_enabled': True, 'notice_title': 'Aviso de la consola', 'notice_body': 'Mañana revisaremos el catálogo.'}
    saved = await change(client, admin_headers, 'system_texts', value)
    assert saved.status_code == 200, saved.text
    notice = await client.get(f'{BASE}/runtime/notice', headers=analyst_headers)
    assert notice.headers['cache-control'] == 'no-store'
    assert notice.json()['title'] == value['notice_title'] and notice.json()['version'] == saved.json()['version']
    invalid = await change(client, admin_headers, 'system_texts', {**value, 'notice_body': '   '})
    assert invalid.status_code == 422 and invalid.json()['error']['code'] == 'INVALID_VALUE'
    assert (await client.get(f'{BASE}/runtime/notice', headers=analyst_headers)).json() == notice.json()
    assert (await client.put(f'{BASE}/settings/system_texts', headers=analyst_headers,
        json={'version': saved.json()['version'], 'value': value, 'change_note': 'Cambio no autorizado'})).status_code == 403


async def test_disabled_features_block_direct_api_and_reenable(client, admin_headers, runtime_rows):
    value = {'news_collection_enabled': False, 'news_adaptation_enabled': False}
    assert (await change(client, admin_headers, 'feature_flags', value)).status_code == 200
    runtime = (await client.get(f'{BASE}/content/runtime', headers=admin_headers)).json()
    assert runtime['collection_enabled'] is False and runtime['adaptation_enabled'] is False
    for path in ('/content/collect', '/content/candidates/00000000-0000-0000-0000-000000000001/adapt'):
        result = await client.post(BASE + path, headers=admin_headers)
        assert result.status_code == 409 and result.json()['error']['code'] == 'FEATURE_DISABLED'
    async with database.get_session_factory()() as db:
        await db.execute(delete(models.ContentJob).where(models.ContentJob.kind == 'collect'))
        await db.commit()
    assert (await change(client, admin_headers, 'feature_flags', {**value, 'news_collection_enabled': True})).status_code == 200
    assert (await client.post(f'{BASE}/content/collect', headers=admin_headers)).status_code == 202


async def test_cache_two_processes_fixed_ttl_immutable_values_and_no_stale_on_failure():
    now = [0]
    row = SimpleNamespace(value={'enabled': True}, version=1)
    class Db:
        calls = 0
        broken = False
        async def scalar(self, stmt):
            self.calls += 1
            if self.broken: raise RuntimeError('Sin conexión')
            return row
    db = Db()
    a, b = SettingsCache(lambda: now[0]), SettingsCache(lambda: now[0])
    result = await a.get(db, 'key'); await b.get(db, 'key')
    result['value']['enabled'] = False
    assert (await a.get(db, 'key'))['value']['enabled'] is True
    row.value = {'enabled': False}; row.version = 2
    now[0] = 59
    assert (await a.get(db, 'key'))['version'] == 1
    now[0] = 60
    assert (await a.get(db, 'key'))['version'] == (await b.get(db, 'key'))['version'] == 2
    assert db.calls == 4  # las lecturas intermedias no prolongan el TTL
    now[0] = 120; db.broken = True
    with pytest.raises(ApiError) as error:
        await a.get(db, 'key')
    assert error.value.status_code == 503
    db.broken = False
    assert (await a.get(db, 'key'))['version'] == 2


async def test_cache_single_load_and_never_rolls_back_version():
    clock = [0]
    class Db:
        calls = 0
        version = 2
        async def scalar(self, stmt):
            self.calls += 1; await asyncio.sleep(0)
            return SimpleNamespace(value={'x': 1}, version=self.version)
    db = Db(); instance = SettingsCache(lambda: clock[0])
    await asyncio.gather(*(instance.get(db, 'key') for _ in range(8)))
    assert db.calls == 1
    clock[0] = 60; db.version = 1
    with pytest.raises(ApiError): await instance.get(db, 'key')


async def test_disabled_collection_skips_scheduler_but_accepted_jobs_continue(client, admin_headers, runtime_rows, monkeypatch):
    from app import content_pipeline as pipeline
    assert (await change(client, admin_headers, 'feature_flags', {
        'news_collection_enabled': False, 'news_adaptation_enabled': False})).status_code == 200
    async with database.get_session_factory()() as db:
        await db.execute(delete(models.ContentJob))
        job = models.ContentJob(kind='collect')
        db.add(job); await db.commit(); job_id = job.id
    called = []
    async def collect(db, job): called.append(job.id)
    monkeypatch.setattr(pipeline, 'collect', collect)
    assert await pipeline.process_one()
    assert called == [job_id]
    await pipeline.schedule()
    async with database.get_session_factory()() as db:
        job = await db.get(models.ContentJob, job_id)
        assert job.status == 'done'
        assert not (await db.scalars(select(models.ContentJob).where(models.ContentJob.kind == 'collect',
            models.ContentJob.status == 'queued'))).all()


async def test_migration_preserves_existing_settings_and_bootstraps_once():
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    module = migration(); engine = sa.create_engine('sqlite://')
    with engine.begin() as conn:
        models.SystemSetting.__table__.create(conn)
        conn.execute(models.SystemSetting.__table__.insert().values(key='custom', value={'keep': 99}, value_schema={}, description='Conservar', version=4))
        module.op = Operations(MigrationContext.configure(conn)); module.upgrade()
        conn.execute(sa.text("UPDATE system_settings SET version=8 WHERE key='system_texts'"))
        module.upgrade()
        assert conn.scalar(sa.text("SELECT version FROM system_settings WHERE key='custom'")) == 4
        assert conn.scalar(sa.text("SELECT version FROM system_settings WHERE key='system_texts'")) == 8
        assert conn.scalar(sa.text('SELECT count(*) FROM system_settings')) == 3
    engine.dispose()
