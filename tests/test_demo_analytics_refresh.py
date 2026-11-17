from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app import models, demo_analytics as jobs
from app.database import Base
from app.analytics_models import AnalyticsSource, AnalyticsAccount, AnalyticsActivity, AnalyticsPayment
from app.commercial_analytics import cohort_funnel, freshness
from app.config import get_settings
from app.security import as_utc
from scripts.seed_commercial_demo import load_demo

OLD = datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 17, 18, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def fixture_factory(monkeypatch):
    monkeypatch.setattr(get_settings(), 'commercial_demo_refresh_enabled', True)
    monkeypatch.setattr(get_settings(), 'environment', 'dev')
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        async with db.begin(): await load_demo(db, OLD)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_processes_data_and_cohorts_preserving_history_then_skips_same_hour(fixture_factory):
    async with fixture_factory() as db:
        before = await cohort_funnel(db, '2026-11', now=NOW)
        await db.commit()
        historical = (await db.execute(select(models.MetricsPlanSnapshot.as_of, models.MetricsPlanSnapshot.plan_code,
            models.MetricsPlanSnapshot.price_clp, models.MetricsPlanSnapshot.mrr_clp))).all()
        accounts = await db.scalar(select(func.count()).select_from(AnalyticsAccount))
        await db.commit()
        async with db.begin(): result = await jobs.refresh_demo(db, NOW)
        assert result['status'] == 'updated'
        row = await db.get(models.MetricsDailyUsers, NOW.date())
        assert as_utc(row.computed_at) == NOW
        assert (await freshness(db, ['daily'], 'demo', row.computed_at, now=NOW)).status == 'fresh'
        after = await cohort_funnel(db, '2026-11', now=NOW)
        assert after.accounts > before.accounts and as_utc(after.cutoff_at) == NOW
        assert after.freshness.status == 'fresh'
        assert await db.scalar(select(func.count()).select_from(AnalyticsAccount)) == accounts
        assert await db.scalar(select(func.max(models.MetricsPlanSnapshot.as_of))) == NOW.date()
        for day, code, price, mrr in historical:
            stored = await db.scalar(select(models.MetricsPlanSnapshot).where(
                models.MetricsPlanSnapshot.as_of == day, models.MetricsPlanSnapshot.plan_code == code))
            assert (stored.price_clp, stored.mrr_clp) == (price, mrr)
        # Las filas futuras precargadas no se presentan como procesadas hoy.
        future = await db.get(models.MetricsDailyUsers, NOW.date() + timedelta(days=1))
        assert as_utc(future.computed_at) == OLD
        await db.commit()
    async with fixture_factory() as db:  # Simula reinicio del proceso en la misma hora.
        async with db.begin(): assert (await jobs.refresh_demo(db, NOW + timedelta(minutes=10)))['status'] == 'current'
        marker = await db.get(AnalyticsSource, (jobs.MARKER, 'demo'))
        assert marker.revision == 1
        await db.commit()
        async with db.begin():
            assert (await jobs.refresh_demo(db, NOW + timedelta(hours=1)))['status'] == 'updated'
        assert as_utc(await db.scalar(select(func.max(models.MetricsHourlyUsers.ts_hour)))) == NOW


@pytest.mark.asyncio
async def test_new_day_adds_plan_cut_with_new_price_and_keeps_previous_cut(fixture_factory):
    async with fixture_factory() as db:
        async with db.begin(): await jobs.refresh_demo(db, NOW)
        db.add(models.SystemSetting(key='plan_prices', description='Prueba', value_schema={},
            value={'gold': 2500, 'platinum': 10000, 'provider': 5000}, version=1))
        await db.commit()
        tomorrow = NOW + timedelta(days=1)
        async with db.begin(): assert (await jobs.refresh_demo(db, tomorrow))['status'] == 'updated'
        prices = dict((await db.execute(select(models.MetricsPlanSnapshot.as_of, models.MetricsPlanSnapshot.price_clp)
            .where(models.MetricsPlanSnapshot.plan_code == 'gold'))).all())
        assert prices[NOW.date()] == 1000 and prices[tomorrow.date()] == 2500
        marker = await db.get(AnalyticsSource, (jobs.MARKER, 'demo'))
        assert marker.revision == 2


@pytest.mark.asyncio
async def test_real_source_disables_refresh_without_touching_sources(fixture_factory):
    async with fixture_factory() as db:
        db.add(AnalyticsSource(name='accounts', data_origin='real', available_through=OLD, updated_at=OLD))
        await db.commit()
        async with db.begin(): assert (await jobs.refresh_demo(db, NOW))['status'] == 'foreign_source'
        assert as_utc((await db.get(AnalyticsSource, ('daily', 'demo'))).updated_at) == OLD
        assert await db.get(AnalyticsSource, (jobs.MARKER, 'demo')) is None


@pytest.mark.asyncio
async def test_edited_demo_values_are_not_replaced_or_marked_fresh(fixture_factory):
    async with fixture_factory() as db:
        row = await db.get(models.MetricsDailyUsers, NOW.date())
        row.downloads += 1
        saved = row.downloads
        await db.commit()
        with pytest.raises(ValueError, match='DEMO_EXISTING_VALUES_CHANGED'):
            async with db.begin(): await jobs.refresh_demo(db, NOW)
        row = await db.get(models.MetricsDailyUsers, NOW.date())
        assert row.downloads == saved and as_utc(row.computed_at) == OLD


@pytest.mark.asyncio
async def test_failure_rolls_back_generated_cuts_and_freshness(fixture_factory, monkeypatch):
    async def fail(*args, **kwargs): raise ValueError('test_failure')
    monkeypatch.setattr(jobs, 'cohort_funnel', fail)
    async with fixture_factory() as db:
        with pytest.raises(ValueError, match='test_failure'):
            async with db.begin(): await jobs.refresh_demo(db, NOW)
        assert as_utc((await db.get(AnalyticsSource, ('daily', 'demo'))).updated_at) == OLD
        assert await db.scalar(select(func.max(models.MetricsPlanSnapshot.as_of))) == OLD.date()
        assert await db.get(AnalyticsSource, (jobs.MARKER, 'demo')) is None


@pytest.mark.asyncio
async def test_disabled_or_expired_demo_never_extends_into_2027(fixture_factory, monkeypatch):
    async with fixture_factory() as db:
        monkeypatch.setattr(get_settings(), 'commercial_demo_refresh_enabled', False)
        assert (await jobs.refresh_demo(db, NOW))['status'] == 'disabled'
        monkeypatch.setattr(get_settings(), 'commercial_demo_refresh_enabled', True)
        assert (await jobs.refresh_demo(db, datetime(2027, 1, 2, tzinfo=timezone.utc)))['status'] == 'outside_demo_range'
        assert await db.get(AnalyticsSource, (jobs.MARKER, 'demo')) is None


@pytest.mark.asyncio
async def test_observed_mode_never_creates_future_observations(monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite://')
    try:
        async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as db:
            async with db.begin(): await load_demo(db, NOW, observed_only=True)
            assert await db.scalar(select(func.max(models.MetricsDailyUsers.day))) == NOW.date()
            for model, column in [(AnalyticsAccount, AnalyticsAccount.created_at), (AnalyticsActivity, AnalyticsActivity.occurred_at),
                (AnalyticsPayment, AnalyticsPayment.occurred_at)]:
                assert as_utc(await db.scalar(select(func.max(column)))) <= NOW
    finally:
        await engine.dispose()
