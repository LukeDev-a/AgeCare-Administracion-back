"""Monitor real en SQLite aislado; sin seed, cuentas reales ni proveedores."""
import asyncio
from contextlib import suppress
from datetime import timedelta
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import models, ops_monitor as monitor
from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.routers import ops
from app.security import as_utc, create_access_token, now_utc


@pytest_asyncio.fixture
async def isolated(monkeypatch):
    monkeypatch.setattr(get_settings(), 'ops_monitor_enabled', True)
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(monitor, 'get_session_factory', lambda: factory)
    monitor.pending.clear()
    yield factory
    monitor.pending.clear()
    await engine.dispose()


def row(key='api_core', age=0, success=True, duration=10, at=None):
    return models.OpsObservation(component_key=key, observed_at=at or now_utc() - timedelta(seconds=age),
        duration_ms=duration, success=success, source='database_probe' if key == 'database' else 'http_requests')


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 401, 403, 422, 423, 429, 500, 503])
async def test_http_expected_errors_and_privacy(isolated, status):
    async def fake(scope, receive, send):
        await send({'type': 'http.response.start', 'status': status, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'private-response'})
    async def forbidden_receive():
        raise AssertionError('middleware must not inspect the body')
    async def send(message):
        pass
    scope = {'type': 'http', 'method': 'POST', 'path': '/api/v1/admin/auth/login',
             'query_string': b'token=private-query', 'headers': [(b'authorization', b'private-bearer')],
             'client': ('192.0.2.7', 4), 'private_user_id': 'private-user'}
    await monitor.OpsMonitorMiddleware(fake)(scope, forbidden_receive, send)
    assert len(monitor.pending) == 2
    assert {r.component_key for r in monitor.pending} == {'api_core', 'auth'}
    assert all(r.success == (status < 500) for r in monitor.pending)
    await monitor.persist_pending()
    async with isolated() as db:
        rows = (await db.scalars(select(models.OpsObservation))).all()
        assert len(rows) == 2
        saved = str([{k: v for k, v in vars(r).items() if k != '_sa_instance_state'} for r in rows])
        assert not any(secret in saved for secret in ('private-', '192.0.2.7', '/auth', 'POST'))
        assert all(r.failure_kind == ('http_5xx' if status >= 500 else None) for r in rows)


@pytest.mark.asyncio
async def test_transport_failure_and_non_console_exclusions(isolated):
    async def broken(scope, receive, send):
        raise OSError('private-user:private-token')
    middleware = monitor.OpsMonitorMiddleware(broken)
    with pytest.raises(OSError):
        await middleware({'type': 'http', 'method': 'GET', 'path': '/api/v1/admin/auth/me'}, None, None)
    assert all(r.failure_kind == 'transport' and not r.success for r in monitor.pending)
    assert 'private' not in str(list(monitor.pending))
    monitor.pending.clear()
    for path, method in [('/health', 'GET'), ('/static/x', 'GET'), ('/api/v1/admin/docs', 'GET'),
                         ('/api/v1/admin/openapi.json', 'GET'), ('/api/v1/admin/auth/me', 'OPTIONS')]:
        with pytest.raises(OSError):
            await middleware({'type': 'http', 'method': method, 'path': path}, None, None)
    assert not monitor.pending


@pytest.mark.asyncio
async def test_probe_real_select_one_and_timeout(isolated, monkeypatch):
    result = await monitor.probe_database()
    assert result.success and result.source == 'database_probe' and result.duration_ms >= 0
    class SlowSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def execute(self, statement):
            assert str(statement) == 'SELECT 1'
            await asyncio.sleep(1)
    monkeypatch.setattr(monitor, 'PROBE_TIMEOUT_SECONDS', .001)
    monkeypatch.setattr(monitor, 'get_session_factory', lambda: SlowSession)
    result = await monitor.probe_database()
    assert not result.success and result.failure_kind == 'probe_timeout'


@pytest.mark.asyncio
async def test_persistence_failure_keeps_pending_without_fresh_claim(isolated, monkeypatch):
    monitor.pending.append(monitor.Observation('api_core', now_utc(), 25, True, 'http_requests'))
    class BrokenSession:
        async def __aenter__(self):
            raise RuntimeError('private-db-url')
        async def __aexit__(self, *args):
            pass
    with monkeypatch.context() as patch:
        patch.setattr(monitor, 'get_session_factory', lambda: BrokenSession)
        with pytest.raises(RuntimeError):
            await monitor.persist_pending()
    assert len(monitor.pending) == 1
    async with isolated() as db:
        state = await ops.status(db)
        assert state.overall is None and state.checked_at is None
    await monitor.persist_pending()
    assert not monitor.pending
    async with isolated() as db:
        assert len((await db.scalars(select(models.OpsObservation))).all()) == 1


@pytest.mark.asyncio
async def test_percentiles_use_individual_successes_and_minimum_twenty(isolated):
    async with isolated() as db:
        db.add_all([row(duration=n) for n in range(1, 20)] + [row(success=False, duration=9999)])
        await db.commit()
        result = await ops.latency(db, '1h', [monitor.ComponentKey.api_core])
        assert result.components[0].sample_count == 20
        assert result.components[0].p50_ms is None and result.components[0].p95_ms is None
        db.add(row(duration=20))
        await db.commit()
        result = await ops.latency(db, '1h', [monitor.ComponentKey.api_core])
        assert (result.components[0].p50_ms, result.components[0].p95_ms) == (10, 19)
        assert result.components[0].observed_success_rate == 20 / 21
        assert result.components[0].successful_sample_count == 20
        assert result.components[0].coverage_ratio is None


@pytest.mark.asyncio
async def test_cancelled_response_never_counts_as_success(isolated):
    async def interrupted(scope, receive, send):
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        raise asyncio.CancelledError()
    async def send(message):
        pass
    with pytest.raises(asyncio.CancelledError):
        await monitor.OpsMonitorMiddleware(interrupted)(
            {'type': 'http', 'method': 'GET', 'path': '/api/v1/admin/auth/me'}, None, send)
    assert len(monitor.pending) == 2
    assert all(not r.success and r.failure_kind == 'cancelled' for r in monitor.pending)


@pytest.mark.asyncio
async def test_ambiguous_commit_retry_and_duplicate_buffer_are_idempotent(isolated):
    observation = monitor.Observation('api_core', now_utc(), 12, True, 'http_requests')
    monitor.pending.extend([observation, observation])
    await monitor.persist_pending()
    monitor.pending.append(observation)
    await monitor.persist_pending()
    assert not monitor.pending
    async with isolated() as db:
        assert len((await db.scalars(select(models.OpsObservation))).all()) == 1


@pytest.mark.asyncio
async def test_real_mode_preserves_other_services_without_affecting_real_summary(isolated):
    async with isolated() as db:
        db.add(models.ComponentState(key='push', status='outage', uptime_30d=0, data_origin='demo'))
        db.add(models.LatencyWindow(component_key='api_core', window='1h', p50_ms=9, p95_ms=10,
                                    sample_count=100, data_origin='demo'))
        db.add(models.LatencyWindow(component_key='push', window='1h', p50_ms=12, p95_ms=34,
                                    sample_count=50, data_origin='demo'))
        db.add(models.CriticalProcessState(key='demo', name='demo', chain='demo', p95_seconds=1,
            success_24h=1, status='operational', data_origin='demo', execution_kind='synthetic'))
        await db.commit()
        state = await ops.status(db)
        assert state.monitoring_enabled and state.overall is None and state.checked_at is None
        assert len(state.components) == len(monitor.ComponentKey)
        assert all(r.status is None and r.uptime_30d is None for r in state.components if r.key != 'push')
        push = next(r for r in state.components if r.key == 'push')
        assert push.freshness == 'stored' and push.status == 'outage' and push.uptime_30d == 0
        assert push.data_origin == 'demo'
        assert next(r for r in state.components if r.key == 'auth').freshness == 'no_data'
        latency = await ops.latency(db, '1h', [monitor.ComponentKey.api_core, monitor.ComponentKey.push])
        assert len(latency.components) == 2 and latency.components[0].p50_ms is None
        assert latency.components[0].sample_count == 0
        assert latency.components[1].p95_ms == 34 and latency.components[1].freshness == 'stored'
        critical = await ops.critical_processes(db)
        assert len(critical.processes) == 1 and critical.processes[0].data_origin == 'demo'


@pytest.mark.asyncio
async def test_stale_gaps_no_backfill_and_new_sample_does_not_refresh_others(isolated, monkeypatch):
    now = now_utc()
    monkeypatch.setattr(monitor, 'now_utc', lambda: now)
    async with isolated() as db:
        db.add_all([row('database', at=now - timedelta(hours=8)),
                    row('database', at=now - timedelta(seconds=60)), row('database', at=now),
                    row('api_core', age=600)])
        await db.commit()
        state = await ops.status(db)
        api = next(r for r in state.components if r.key == 'api_core')
        database = next(r for r in state.components if r.key == 'database')
        auth = next(r for r in state.components if r.key == 'auth')
        assert api.status is None and api.freshness == 'stale'
        assert as_utc(api.checked_at) < as_utc(database.checked_at)
        assert database.coverage_seconds == 60 and database.uptime_30d is None
        assert database.sample_count == 2
        assert auth.status is None and auth.freshness == 'no_data'
        assert state.overall == 'operational'
        assert len((await db.scalars(select(models.OpsObservation))).all()) == 4


def test_coverage_does_not_fill_gaps_or_after_last_probe():
    end = now_utc()
    rows = [row('database', at=end - timedelta(seconds=600)),
            row('database', at=end - timedelta(seconds=510)),
            row('database', at=end - timedelta(seconds=300)),
            row('database', at=end - timedelta(seconds=240), success=False)]
    seconds, ratio, rate = monitor.coverage(rows, end - timedelta(seconds=600), end)
    assert seconds == 120 and ratio == .2 and rate == .5


@pytest.mark.asyncio
async def test_retention_caps_and_buffer_are_bounded(isolated, monkeypatch):
    monkeypatch.setattr(monitor, 'MAX_ROWS_PER_COMPONENT', 2)
    async with isolated() as db:
        db.add_all([row(age=40 * 86400), row(age=4), row(age=3), row(age=2), row('database')])
        await db.commit()
    await monitor.persist_pending()
    async with isolated() as db:
        rows = (await db.scalars(select(models.OpsObservation))).all()
        assert len(rows) == 3 and sum(r.component_key == 'database' for r in rows) == 1
    for _ in range(monitor.BUFFER_LIMIT + 20):
        monitor.pending.append(monitor.Observation('api_core', now_utc(), 1, True, 'http_requests'))
    assert len(monitor.pending) == monitor.BUFFER_LIMIT


@pytest.mark.asyncio
async def test_worker_disabled_and_cancellation_cleanup(isolated, monkeypatch):
    calls = []
    ready = asyncio.Event()
    async def tick():
        calls.append(True)
        ready.set()
    monkeypatch.setattr(monitor, 'monitor_tick', tick)
    monkeypatch.setattr(get_settings(), 'ops_monitor_enabled', False)
    await monitor.ops_monitor_worker()
    assert not calls
    monkeypatch.setattr(get_settings(), 'ops_monitor_enabled', True)
    task = asyncio.create_task(monitor.ops_monitor_worker())
    await asyncio.wait_for(ready.wait(), 1)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    assert task.done() and calls == [True]


@pytest.mark.asyncio
async def test_ops_reads_remain_permission_protected(isolated):
    async def override_db():
        async with isolated() as session:
            yield session
    app.dependency_overrides[get_db] = override_db
    async with isolated() as db:
        admin = models.AdminUser(full_name='Prueba', email='ops@example.invalid', role='admin')
        editor = models.AdminUser(full_name='Prueba', email='editor@example.invalid', role='editor')
        db.add_all([admin, editor])
        await db.commit()
        admin_token = create_access_token(admin.id, admin.role)
        editor_token = create_access_token(editor.id, editor.role)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            for path in ('status', 'latency', 'critical-processes'):
                assert (await client.get('/api/v1/admin/ops/' + path)).status_code == 401
                assert (await client.get('/api/v1/admin/ops/' + path,
                    headers={'Authorization': 'Bearer ' + editor_token})).status_code == 403
                assert (await client.get('/api/v1/admin/ops/' + path,
                    headers={'Authorization': 'Bearer ' + admin_token})).status_code == 200
    finally:
        app.dependency_overrides.pop(get_db)


def migration():
    path = Path(__file__).parents[1] / 'alembic/versions/0021_ops_observations.py'
    spec = importlib.util.spec_from_file_location('migration_0021', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_sqlite_preserves_existing_rows_and_model_contract():
    module = migration()
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE prior_data (value TEXT)'))
        connection.execute(text("INSERT INTO prior_data VALUES ('preserved')"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()
            columns = {r['name'] for r in inspect(connection).get_columns('ops_observations')}
            assert columns == set(models.OpsObservation.__table__.columns.keys())
            assert connection.scalar(text('SELECT value FROM prior_data')) == 'preserved'
            assert connection.scalar(text('SELECT count(*) FROM ops_observations')) == 0
            module.downgrade()
            assert connection.scalar(text('SELECT value FROM prior_data')) == 'preserved'
    engine.dispose()


def test_migration_compiles_postgres_uuid_and_constraints():
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': output})
    with Operations.context(context):
        migration().upgrade()
    ddl = output.getvalue()
    assert 'id UUID NOT NULL' in ddl and 'TIMESTAMP WITH TIME ZONE' in ddl
    assert 'ck_ops_observation_component' in ddl and 'CREATE INDEX' in ddl
    assert 'INSERT' not in ddl and 'UPDATE' not in ddl
