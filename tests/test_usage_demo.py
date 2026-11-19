"""Actividad/adopción coherentes; memoria, sin providers ni bases habituales."""
from datetime import datetime, date, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, func, create_engine, inspect
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app import models, usage_demo as usage
from app.analytics_models import UsageAccount, UsageSession, AnalyticsSource
from app.config import get_settings
from app.database import Base
from app.routers import metrics_roles, metrics_features


@pytest_asyncio.fixture
async def db(monkeypatch):
    monkeypatch.setattr(get_settings(),'environment','dev')
    monkeypatch.setattr(get_settings(),'usage_demo_refresh_enabled',True)
    monkeypatch.setattr(usage,'START',date(2026,8,1))
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as session:
        session.add_all([
            models.Feature(feature_key='chat',name='Chat',applicable_roles=list(usage.ROLES),expected_low=False,sort_order=1),
            models.Feature(feature_key='sos',name='SOS',applicable_roles=['elder'],expected_low=True,sort_order=2),
        ])
        await session.commit()
        yield session
    await engine.dispose()


def at(day):
    return usage.local_start(day)+timedelta(hours=12)


async def count(db,model):
    return await db.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_preparation_required_and_disabled_in_production(db,monkeypatch):
    assert (await usage.refresh_usage(db,at(date(2026,9,3))))['status']=='not_prepared'
    monkeypatch.setattr(get_settings(),'environment','prod')
    assert (await usage.refresh_usage(db,at(date(2026,9,3)),prepare=True))['status']=='disabled'
    assert await count(db,UsageAccount)==0


@pytest.mark.asyncio
async def test_daily_recovery_no_duplicates_or_future_and_common_denominator(db):
    now=at(date(2026,9,3))
    result=await usage.refresh_usage(db,now,prepare=True)
    await db.commit()
    assert result['through']=='2026-09-02'
    original=await count(db,UsageSession)
    assert (await usage.refresh_usage(db,now))['status']=='current'
    assert await count(db,UsageSession)==original
    result=await usage.refresh_usage(db,at(date(2026,9,6)))
    await db.commit()
    assert result['through']=='2026-09-05' and result['new_sessions']>0
    assert await db.scalar(select(func.max(UsageSession.started_at))) < datetime(2026,9,6,0,0)
    summary=await metrics_roles.roles_summary(db,30)
    adoption=await metrics_features.adoption(db,30)
    assert summary.data_through==adoption.data_through==date(2026,9,5)
    start=usage.local_start(date(2026,9,6))-timedelta(days=30)
    end=usage.local_start(date(2026,9,6))
    for row in summary.roles:
        expected=await db.scalar(select(func.count(func.distinct(UsageSession.account_id))).join(
            UsageAccount,UsageAccount.id==UsageSession.account_id).where(
                UsageAccount.profile==row.role.value, UsageSession.started_at>=start,UsageSession.started_at<end))
        assert row.active_users==expected
    for feature in adoption.features:
        for detail in feature.calculation_details:
            if detail.applicable:
                expected=next(r.active_users for r in summary.roles if r.role==detail.role)
                assert detail.active_users==expected and 0 <= detail.users <= expected
    weekly=await metrics_roles.weekly_active(db,8)
    assert len(weekly.week_details)==8
    assert max(w.end_date for w in weekly.week_details) >= date(2026,9,5)


@pytest.mark.asyncio
async def test_recovery_equals_processing_every_day(db):
    await usage.refresh_usage(db,at(date(2026,8,5)),prepare=True)
    await db.commit()
    for day in (6,7,8):
        await usage.refresh_usage(db,at(date(2026,8,day)))
        await db.commit()
    accounts=(await db.scalars(select(UsageAccount))).all()
    features=(await db.scalars(select(models.Feature))).all()
    expected=usage.session_rows(accounts,date(2026,8,1),date(2026,8,7),features)
    actual=(await db.scalars(select(UsageSession))).all()
    assert {r.id for r in actual}=={r['id'] for r in expected}


@pytest.mark.asyncio
async def test_freezes_after_december24_without_rejuvenating_dates(db,monkeypatch):
    monkeypatch.setattr(usage,'START',date(2026,12,15))
    await usage.refresh_usage(db,at(date(2026,12,25)),prepare=True)
    await db.commit()
    rows=await count(db,UsageSession)
    marker=await db.get(AnalyticsSource,(usage.MARKER,'demo'))
    stamp=marker.updated_at
    assert (await usage.refresh_usage(db,at(date(2027,1,4))))['status']=='frozen'
    assert marker.updated_at==stamp and await count(db,UsageSession)==rows
    assert usage.as_utc(marker.available_through)==usage.local_start(date(2026,12,25))


@pytest.mark.asyncio
async def test_failure_rolls_back_whole_cycle_and_preserves_unrelated_data(db,monkeypatch):
    db.add(models.ComponentState(key='push',status='operational',uptime_30d=.98))
    await db.commit()
    async def fail(*args):
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(usage,'aggregates',fail)
    with pytest.raises(RuntimeError):
        await usage.refresh_usage(db,at(date(2026,8,8)),prepare=True)
    await db.rollback()
    assert await count(db,UsageAccount)==0 and await count(db,UsageSession)==0
    assert await db.get(AnalyticsSource,(usage.MARKER,'demo')) is None
    assert (await db.get(models.ComponentState,'push')).uptime_30d==.98


def test_migration_adds_only_two_tables_and_downgrades():
    engine=create_engine('sqlite://')
    path=Path(__file__).parents[1]/'alembic/versions/0022_usage_observations.py'
    spec=importlib.util.spec_from_file_location('usage_revision',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
            assert set(inspect(conn).get_table_names())=={'analytics_usage_accounts','analytics_usage_sessions'}
            module.downgrade()
            assert not inspect(conn).get_table_names()
    engine.dispose()


def test_neon_runner_uses_additive_revision_and_preserves_existing_table():
    from scripts.migrate_neon_0022 import upgrade
    from sqlalchemy import text
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE existing_data (value TEXT NOT NULL)'))
        conn.execute(text("INSERT INTO existing_data VALUES ('preserved')"))
        upgrade(conn)
        assert set(inspect(conn).get_table_names()) == {
            'existing_data', 'analytics_usage_accounts', 'analytics_usage_sessions'}
        assert conn.scalar(text('SELECT value FROM existing_data')) == 'preserved'
        assert conn.scalar(text('SELECT count(*) FROM analytics_usage_accounts')) == 0
        assert conn.scalar(text('SELECT count(*) FROM analytics_usage_sessions')) == 0
    engine.dispose()
