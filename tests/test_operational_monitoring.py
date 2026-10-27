"""RF05.01–03: consultas aisladas, sin recolectores ni base real."""
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.database import Base
from app.models import ComponentState, LatencyWindow, CriticalProcessState
from app.routers.ops import status, latency, critical_processes
from app.enums import ComponentKey
from app.errors import ApiError
from app.security import as_utc

AT = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)

@pytest_asyncio.fixture
async def db():
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()

pytestmark = pytest.mark.asyncio

@pytest.mark.parametrize('states,expected', [
    (['operational', 'degraded', 'outage'], 'outage'),
    (['outage', 'operational'], 'outage'), (['degraded', 'operational'], 'degraded'),
    (['operational', 'operational'], 'operational'),
])
async def test_worst_component_state_and_source_dates(db, states, expected):
    for index, state in enumerate(states):
        db.add(ComponentState(key=list(ComponentKey)[index], status=state, uptime_30d=.99,
            latency_p50_ms=None, latency_p95_ms=120, data_origin='demo', checked_at=AT+timedelta(minutes=index)))
    await db.flush()
    first = await status(db)
    assert first.overall == expected
    assert as_utc(first.checked_at) == AT+timedelta(minutes=len(states)-1)
    assert first.components[0].latency_p50_ms is None
    assert first.components[0].latency_p95_ms == 120
    assert first.components[0].data_origin == 'demo'
    second = await status(db)
    assert second.checked_at == first.checked_at  # consultar no rejuvenece el dato

async def test_empty_monitor_does_not_claim_health_or_fresh_measurement(db):
    state = await status(db)
    assert state.overall is None and state.checked_at is None and state.components == []
    result = await latency(db, '1h', None)
    assert result.components == [] and result.computed_at is None
    assert len(result.missing_components) == 7
    result = await critical_processes(db)
    assert result.processes == [] and result.computed_at is None

@pytest.mark.parametrize('window,multiplier', [('1h', 1), ('24h', 2), ('7d', 3)])
async def test_window_component_filters_values_and_async_meaning(db, window, multiplier):
    for name, factor in [('1h', 1), ('24h', 2), ('7d', 3)]:
        for key in ('push', 'ai_assistant', 'database'):
            db.add(LatencyWindow(window=name, component_key=key, p50_ms=11*factor, p95_ms=31*factor,
                sample_count=100*factor, computed_at=AT, data_origin='real'))
    await db.flush()
    result = await latency(db, window, [ComponentKey.push, ComponentKey.ai_assistant, ComponentKey.push])
    assert result.window == window and len(result.components) == 2
    assert result.missing_components == [] and as_utc(result.computed_at) == AT
    for row in result.components:
        assert (row.p50_ms, row.p95_ms, row.sample_count) == (11*multiplier, 31*multiplier, 100*multiplier)
        assert row.measurement_kind == ('delivery' if row.key == 'push' else 'generation')
        assert row.data_origin == 'real' and as_utc(row.computed_at) == AT

async def test_missing_selected_component_is_reported_without_zero_samples(db):
    db.add(LatencyWindow(window='1h', component_key='database', p50_ms=0, p95_ms=0,
        sample_count=10, computed_at=AT))
    await db.flush()
    result = await latency(db, '1h', [ComponentKey.database, ComponentKey.push])
    assert result.missing_components == ['push']
    assert result.components[0].p50_ms == 0  # cero real conservado
    assert result.components[0].data_origin == 'unknown'

async def test_invalid_window_has_stable_code(db):
    with pytest.raises(ApiError) as error:
        await latency(db, '5m', None)
    assert error.value.code == 'INVALID_WINDOW' and error.value.status_code == 422

@pytest.mark.parametrize('kind', ['real', 'synthetic', 'demo', 'unknown'])
async def test_synthetic_is_explicit_in_chain_without_inventing_execution(db, kind):
    db.add(CriticalProcessState(key='ai_query', name='Consulta IA', chain='App → IA → respuesta',
        p95_seconds=4.25, success_24h=.975, status='degraded', computed_at=AT,
        data_origin='demo' if kind == 'demo' else 'unknown', execution_kind=kind))
    await db.flush()
    result = await critical_processes(db)
    row = result.processes[0]
    assert row.execution_kind == kind and row.p95_seconds == 4.25 and row.success_24h == .975
    assert ('Comprobación sintética' in row.chain) == (kind == 'synthetic')
    assert as_utc(result.computed_at) == AT and as_utc(row.computed_at) == AT
