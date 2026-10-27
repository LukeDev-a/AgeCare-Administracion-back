"""0007→0008 SOLO en una base temporal agecare_seed_check_ops_* vacía."""
import asyncio
import subprocess
from sqlalchemy import text
from app import database
from app.routers.ops import status, latency, critical_processes
from app.enums import ComponentKey

TABLES = ('ops_component_state', 'ops_latency_window', 'ops_critical_process_state')

def check_target():
    url = database.get_engine().url
    assert url.database.startswith('agecare_seed_check_ops_') and url.database != 'agecare_admin'
    assert url.host == 'db' and url.username == 'agecare'

async def prepare():
    check_target()
    async with database.get_engine().begin() as conn:
        for name in TABLES:
            await conn.execute(text(f'ALTER TABLE {name} DROP COLUMN IF EXISTS data_origin'))
        await conn.execute(text('ALTER TABLE ops_critical_process_state DROP COLUMN IF EXISTS execution_kind'))
        await conn.execute(text("INSERT INTO ops_component_state (key, status, uptime_30d, latency_p50_ms, latency_p95_ms, checked_at) VALUES ('push', 'outage', .98, NULL, 1900, '2026-10-01T12:00:00Z')"))
        await conn.execute(text("INSERT INTO ops_latency_window (id, \"window\", component_key, p50_ms, p95_ms, sample_count, computed_at) VALUES ('00000000-0000-0000-0000-000000000008', '1h', 'push', 100, 1900, 40, '2026-10-01T12:00:00Z')"))
        await conn.execute(text("INSERT INTO ops_critical_process_state (key, name, chain, p95_seconds, success_24h, status, computed_at) VALUES ('sos', 'SOS', 'App → push', 2.5, .99, 'operational', '2026-10-01T12:00:00Z')"))
        before = {name: dict((await conn.execute(text(f'SELECT * FROM {name}'))).mappings().one()) for name in TABLES}
    await database.get_engine().dispose()
    return before

async def verify(before):
    check_target()
    async with database.get_session_factory()() as db:
        for name in TABLES:
            after = dict((await db.execute(text(f'SELECT * FROM {name}'))).mappings().one())
            assert after.pop('data_origin') == 'unknown'
            if name == TABLES[2]:
                assert after.pop('execution_kind') == 'unknown'
            assert after == before[name]
        state = await status(db)
        assert state.overall == 'outage' and state.components[0].latency_p50_ms is None
        result = await latency(db, '1h', [ComponentKey.push])
        assert result.components[0].measurement_kind == 'delivery' and result.components[0].sample_count == 40
        result = await critical_processes(db)
        assert result.processes[0].execution_kind == 'unknown'
        assert result.processes[0].chain == 'App → push'
        await db.execute(text("UPDATE ops_critical_process_state SET execution_kind='synthetic' WHERE key='sos'"))
        result = await critical_processes(db)
        assert 'Comprobación sintética' in result.processes[0].chain
        await db.rollback()
    await database.get_engine().dispose()
    print('PostgreSQL OK: 0007→0008 conserva registros/fechas/null y marca procedencia desconocida; consultas y cadena sintética correctas.')

if __name__ == '__main__':
    check_target()
    subprocess.run(['alembic', 'upgrade', '0007'], check=True)
    before = asyncio.run(prepare())
    subprocess.run(['alembic', 'upgrade', 'head'], check=True)
    asyncio.run(verify(before))
