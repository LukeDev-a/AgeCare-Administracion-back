"""Reglas comerciales con reloj fijo y base aislada, sin servicios externos."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as Row
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.database import Base
from app.analytics_models import AnalyticsAccount, AnalyticsSource, AnalyticsCohortSnapshot
from app.commercial_analytics import VALID_ACTIONS, calculate, cohort_funnel, freshness, month_of
from app.periods import resolve, buckets_for
from app.enums import PeriodKey
from app.routers.metrics_commercial import commercial_summary, registrations
from app.models import MetricsDailyUsers, MetricsHourlyUsers

NOW = datetime(2026, 10, 26, 15, tzinfo=timezone.utc)
START = datetime(2026, 9, 30, 15, tzinfo=timezone.utc)

def account(start=START, profile='elder'):
    return Row(id=uuid4(), created_at=start, profile=profile, data_origin='real')

def sources(at=NOW):
    return [Row(name=name, available_through=at) for name in ('accounts', 'activity', 'payments')]

def activity(owner, when, action='message_sent', origin='real'):
    return Row(account_id=owner.id, occurred_at=when, action=action, data_origin=origin)

def payment(owner, when, amount=100, success=True, active=True):
    return Row(account_id=owner.id, occurred_at=when, amount_minor=amount,
               successful=success, subscription_active=active, data_origin='real')

@pytest.mark.parametrize('profile,action', [(profile, action) for profile, actions in VALID_ACTIONS.items() for action in actions])
def test_valid_mobile_actions(profile, action):
    owner = account(profile=profile)
    _, total, observed, stages = calculate([owner], [activity(owner, START+timedelta(days=1), action)], [], sources(), NOW)
    assert total == 1 and observed == 0  # septiembre se sigue también durante octubre
    assert [stage.users for stage in stages] == [1, 1, 0]
    assert stages[2].rate_vs_previous == 0  # cero medido, no ausencia

def test_distinct_accounts_not_number_of_events_and_strict_30_day_window():
    owner = account(NOW-timedelta(days=40))
    events = [activity(owner, owner.created_at+timedelta(days=1))]*5
    events += [activity(owner, owner.created_at+timedelta(days=30))]
    _, total, observed, stages = calculate([owner], events, [], sources(), NOW)
    assert (total, observed) == (1, 1)
    assert stages[1].users == 1
    assert calculate([owner], events[-1:], [], sources(), NOW)[3][1].users == 0

@pytest.mark.parametrize('offset,amount,success,active,expected', [
    (2, 100, True, True, 1), (0, 100, True, True, 0),
    (1, 100, True, True, 0), (2, 0, True, True, 0),
    (2, 100, False, True, 0), (2, 100, True, False, 0),
    (30, 100, True, True, 0),
])
def test_first_payment_rules(offset, amount, success, active, expected):
    owner = account(NOW-timedelta(days=40))
    event = activity(owner, owner.created_at+timedelta(days=1))
    charge = payment(owner, owner.created_at+timedelta(days=offset), amount, success, active)
    assert calculate([owner], [event], [charge], sources(), NOW)[3][2].users == expected

def test_later_payment_cannot_replace_first_charge_before_activity():
    owner = account()
    charges = [payment(owner, START), payment(owner, START+timedelta(days=3))]
    assert calculate([owner], [activity(owner, START+timedelta(days=1))], charges, sources(), NOW)[3][2].users == 0

def test_missing_source_and_zero_denominator_are_null():
    owner = account()
    stages = calculate([owner], [], [], sources()[:1], NOW)[3]
    assert [stage.users for stage in stages] == [1, None, None]
    assert stages[1].unavailable_reason == 'missing_source'
    empty = calculate([], [], [], sources(), NOW)[3]
    assert all(stage.rate_vs_first is None for stage in empty)
    assert empty[2].rate_vs_previous is None

def test_incompatible_origin_is_not_comparable_and_cutoff_excludes_future_events():
    owner = account()
    result = calculate([owner], [activity(owner, START, origin='demo')], [], sources(), NOW)
    assert result[3][1].users is None
    assert result[3][1].unavailable_reason == 'not_comparable'
    result = calculate([owner], [activity(owner, START+timedelta(days=2))], [], sources(START+timedelta(days=1)), NOW)
    assert result[0] == START+timedelta(days=1)
    assert result[3][1].users == 0

def test_business_month_and_twelve_calendar_buckets():
    assert month_of(datetime(2026, 10, 1, 1, tzinfo=timezone.utc)) == '2026-09'
    p = resolve(PeriodKey.last_12_months, date(2026, 10, 26))
    assert p.start == date(2025, 11, 1) and len(buckets_for(p)) == 12

@pytest_asyncio.fixture
async def db():
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()

@pytest.mark.asyncio
async def test_cohort_selection_daily_cache_and_real_precedence(db):
    for month in (8, 9, 10):
        db.add(AnalyticsAccount(external_id=f'real-{month}', profile='elder', data_origin='real',
            created_at=datetime(2026, month, 28 if month != 10 else 1, 12, tzinfo=timezone.utc)))
    db.add(AnalyticsAccount(external_id='demo', profile='elder', data_origin='demo', created_at=START))
    for name in ('accounts', 'activity', 'payments'):
        db.add(AnalyticsSource(name=name, data_origin='real', available_through=NOW, updated_at=NOW))
    await db.flush()
    first = await cohort_funnel(db, now=NOW)
    assert first.cohort_month == '2026-08' and not first.provisional
    assert first.data_origin == 'real' and first.accounts == 1
    explicit = await cohort_funnel(db, '2026-09', NOW)
    assert explicit.provisional and explicit.observed_accounts == 0
    cached = await cohort_funnel(db, now=NOW+timedelta(minutes=1))
    assert cached.computed_at == first.computed_at
    tomorrow = await cohort_funnel(db, now=NOW+timedelta(hours=25))
    assert tomorrow.computed_at > cached.computed_at
    assert tomorrow.freshness.status == 'stale'  # recalcular no rejuvenece la fuente
    assert await db.scalar(select(AnalyticsCohortSnapshot.month)) is not None
    src = await db.get(AnalyticsSource, ('accounts', 'real'))
    src.revision += 1
    await db.flush()
    refreshed = await cohort_funnel(db, now=NOW+timedelta(hours=25, minutes=1))
    assert refreshed.computed_at > tomorrow.computed_at

@pytest.mark.asyncio
@pytest.mark.parametrize('month', ['2026-11', '2026-13', '2026-1', 'texto'])
async def test_invalid_or_future_cohort(db, month):
    from app.errors import ApiError
    with pytest.raises(ApiError) as error:
        await cohort_funnel(db, month, NOW)
    assert error.value.status_code == 422
    assert error.value.code == 'INVALID_COHORT'

@pytest.mark.asyncio
async def test_freshness_source_and_calculation_separately(db):
    db.add(AnalyticsSource(name='daily', data_origin='real', updated_at=NOW,
        available_through=NOW-timedelta(hours=25)))
    await db.flush()
    state = await freshness(db, ['daily'], 'real', NOW, NOW)
    assert state.status == 'stale' and not state.calculation_stale
    assert (await freshness(db, ['plans'], 'real', NOW, NOW)).status == 'missing'
    src = await db.get(AnalyticsSource, ('daily', 'real'))
    src.available_through = NOW
    await db.flush()
    state = await freshness(db, ['daily'], 'real', NOW-timedelta(hours=25), NOW)
    assert state.calculation_stale and state.status == 'stale'

@pytest.mark.asyncio
async def test_empty_summary_is_not_zero_and_period_is_explicit(db):
    response = await commercial_summary(db, 'current_month')
    assert response.new_users is None and response.mrr_clp is None
    assert response.freshness.status == 'missing'
    assert response.period.start_date.day == 1

@pytest.mark.asyncio
async def test_hourly_boundaries_do_not_include_next_business_day(db, monkeypatch):
    monkeypatch.setattr('app.periods.business_today', lambda: date(2026, 10, 26))
    midnight = datetime(2026, 10, 26, 3, tzinfo=timezone.utc)  # Santiago UTC-3
    for offset, count in [(-1, 900), (0, 0), (23, 7), (24, 900)]:
        db.add(MetricsHourlyUsers(ts_hour=midnight+timedelta(hours=offset), bucket_minutes=60,
            signups=count, cancellations=0, data_origin='real', computed_at=NOW))
    await db.flush()
    response = await registrations(db, 'today')
    assert response.signups == [0, 7]
    assert response.buckets[-1].end == midnight+timedelta(days=1)

@pytest.mark.asyncio
async def test_missing_daily_bucket_remains_null(db, monkeypatch):
    monkeypatch.setattr('app.periods.business_today', lambda: date(2026, 10, 26))
    db.add(MetricsDailyUsers(day=date(2026, 10, 26), signups=0, cancellations=0, downloads=0,
        active_users_eod=0, paying_users_eod=0, mrr_clp_eod=0, data_origin='real', computed_at=NOW))
    await db.flush()
    response = await registrations(db, 'last_7_days')
    assert response.signups == [None]*6+[0]
    summary = await commercial_summary(db, 'last_7_days')
    assert summary.new_users is None and summary.paying_share is None

@pytest.mark.asyncio
async def test_old_snapshot_is_not_a_zero_percent_comparison(db, monkeypatch):
    monkeypatch.setattr('app.periods.business_today', lambda: date(2026, 10, 26))
    db.add(MetricsDailyUsers(day=date(2026, 8, 28), signups=3, cancellations=0, downloads=4,
        active_users_eod=10, paying_users_eod=5, mrr_clp_eod=1000, data_origin='demo', computed_at=NOW))
    await db.flush()
    summary = await commercial_summary(db, 'current_month')
    assert summary.as_of == date(2026, 8, 28)  # conservar el corte antiguo visible
    assert summary.new_users is None
    assert summary.deltas.mrr_pct is None and summary.deltas.active_users_pct is None

@pytest.mark.asyncio
async def test_plan_snapshot_keeps_zero_price_and_no_zero_denominator(db):
    from app.models import MetricsPlanSnapshot
    from app.routers.metrics_commercial import plans
    for day, price, users in [(date(2026, 9, 1), 500, 2), (date(2026, 10, 1), 0, 0)]:
        db.add(MetricsPlanSnapshot(as_of=day, plan_code='free', users=users, price_clp=price,
            mrr_clp=0, monthly_churn=0, data_origin='demo', computed_at=NOW))
    await db.flush()
    response = await plans(db)
    assert response.as_of == date(2026, 10, 1)
    assert response.plans[0].price_clp == 0 and response.plans[0].share is None
    assert response.totals.monthly_churn is None
