from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base
from app import models
from app.analytics_models import AnalyticsAccount, AnalyticsActivity, AnalyticsPayment
from app.commercial_analytics import cohort_funnel
from scripts.seed_commercial_demo import load_demo, complete_legacy_year, START


@pytest.mark.asyncio
async def test_demo_is_repeatable_protects_existing_data_and_keeps_future_cohorts_out():
    engine = create_async_engine('sqlite+aiosqlite://')
    now = datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine)
        async with factory() as db:
            async with db.begin():
                counts = await load_demo(db, now)
            expected = {}
            for model in (models.MetricsDailyUsers, AnalyticsAccount, AnalyticsActivity, AnalyticsPayment):
                expected[model] = await db.scalar(sa.select(sa.func.count()).select_from(model))
            assert counts['cuentas'] > 15000
            await db.commit()
            async with db.begin():
                await load_demo(db, now)
            for model, count in expected.items():
                assert await db.scalar(sa.select(sa.func.count()).select_from(model)) == count
            assert await db.scalar(sa.select(sa.func.max(models.MetricsPlanSnapshot.as_of))) == now.date()
            result = await cohort_funnel(db, '2026-09', now=now)
            assert result.accounts > 3000 and not result.provisional
            assert all(option.month <= '2026-11' for option in result.cohorts)
            assert result.stages[0].users > result.stages[1].users > result.stages[2].users > 0
            await db.rollback()
            async with db.begin():
                row = await db.get(models.MetricsDailyUsers, now.date())
                row.data_origin = 'real'
            with pytest.raises(ValueError):
                async with db.begin():
                    await load_demo(db, now)
            assert (await db.get(models.MetricsDailyUsers, now.date())).data_origin == 'real'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('include_history', [False, True])
async def test_legacy_classification_preserves_values_and_timestamps(include_history):
    engine = create_async_engine('sqlite+aiosqlite://')
    stamp = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as db:
            start = date(2025, 6, 29) if include_history else date(2026, 1, 1)
            day = start
            while day < START:
                db.add(models.MetricsDailyUsers(day=day, data_origin='unknown',
                    signups=17, cancellations=2, downloads=40, computed_at=stamp))
                day += timedelta(days=1)
            await db.commit()
            assert await complete_legacy_year(db, include_history) == (START - start).days
            await db.flush()
            assert await complete_legacy_year(db, include_history) == 0
            row = await db.get(models.MetricsDailyUsers, date(2026, 1, 1))
            assert (row.signups, row.cancellations, row.downloads) == (17, 2, 40)
            assert row.computed_at.replace(tzinfo=timezone.utc) == stamp
            row.data_origin = 'real'
            await db.flush()
            with pytest.raises(ValueError):
                await complete_legacy_year(db, include_history)
    finally:
        await engine.dispose()
