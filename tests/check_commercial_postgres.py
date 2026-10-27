"""Verificación explícita SOLO en base temporal agecare_seed_check_*.

Simula columnas de 0006, migra, carga demo vacía y consulta cachés concurrentes.
Ejecutar con la configuración temporal suministrada desde el entorno.
"""
import asyncio
import subprocess
from sqlalchemy import text
from app import database
from app.analytics_models import (AnalyticsCohortSnapshot, AnalyticsPayment,
    AnalyticsActivity, AnalyticsAccount, AnalyticsSource)
from app.commercial_analytics import cohort_funnel
from tests.check_demo_seed_postgres import main as check_seed


def check_target():
    url = database.get_engine().url
    assert url.database.startswith('agecare_seed_check_') and url.database != 'agecare_admin'
    assert url.host == 'db' and url.username == 'agecare'


async def prepare_legacy():
    check_target()
    engine = database.get_engine()
    async with engine.begin() as conn:
        for model in (AnalyticsCohortSnapshot, AnalyticsPayment, AnalyticsActivity, AnalyticsAccount, AnalyticsSource):
            await conn.run_sync(lambda bind, table=model.__table__: table.drop(bind, checkfirst=True))
        for name in ('metrics_daily_users', 'metrics_hourly_users', 'metrics_plan_snapshot'):
            await conn.execute(text(f'ALTER TABLE {name} DROP COLUMN IF EXISTS data_origin'))
        await conn.execute(text('ALTER TABLE metrics_hourly_users DROP COLUMN IF EXISTS bucket_minutes'))
        await conn.execute(text("INSERT INTO metrics_hourly_users (id, ts_hour, signups, cancellations, computed_at) VALUES ('00000000-0000-0000-0000-000000000007', '2020-01-01T00:00:00Z', 1, 0, now())"))
    await engine.dispose()


async def verify():
    check_target()
    async with database.get_engine().begin() as conn:
        row = (await conn.execute(text('SELECT data_origin, bucket_minutes FROM metrics_hourly_users'))).one()
        assert tuple(row) == ('unknown', 180), row
        await conn.execute(text("DELETE FROM metrics_hourly_users WHERE ts_hour = '2020-01-01T00:00:00Z'"))
    await check_seed()
    async def request():
        async with database.get_session_factory()() as db:
            result = await cohort_funnel(db)
            await db.commit()
            return result
    first, second = await asyncio.gather(request(), request())
    assert first.computed_at == second.computed_at
    assert first.data_origin == 'demo' and not first.provisional
    assert [stage.users for stage in first.stages] == [6, 4, 2]
    print('Migración 0006→0007, preservación de intervalo legado, seed seguro y caché concurrente: correctos.')
    await database.get_engine().dispose()


if __name__ == '__main__':
    check_target()
    subprocess.run(['alembic', 'upgrade', '0006'], check=True)
    asyncio.run(prepare_legacy())
    subprocess.run(['alembic', 'upgrade', 'head'], check=True)
    asyncio.run(verify())
