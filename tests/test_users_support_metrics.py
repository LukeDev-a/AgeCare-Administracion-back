"""RF07: verificar el contrato recibido, sin ampliar su implementación."""
import pytest
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app import database, models
from app.routers.support import support_summary

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/admin'

@pytest.mark.parametrize('days', [7, 30, 90])
async def test_roles_available_windows_and_temporal_fields(client, analyst_headers, days):
    result = await client.get(BASE+'/metrics/roles/summary', params={'days': days}, headers=analyst_headers)
    assert result.status_code == 200
    data = result.json()
    assert data['days'] == days and data['computed_at']
    assert [row['role'] for row in data['roles']] == ['family', 'caregiver', 'elder', 'doctor']
    assert all({'active_users', 'growth_8w', 'sessions_per_week', 'avg_session_seconds', 'retention_30d'} <= row.keys() for row in data['roles'])

async def test_intermediate_window_preserves_existing_normalization(client, analyst_headers):
    result = await client.get(BASE+'/metrics/roles/summary', params={'days': 14}, headers=analyst_headers)
    assert result.status_code == 200 and result.json()['days'] == 7
    for days in (6, 91):
        assert (await client.get(BASE+'/metrics/roles/summary', params={'days': days}, headers=analyst_headers)).status_code == 422

@pytest.mark.parametrize('weeks', [2, 8, 26])
async def test_weekly_contract_order_and_alignment(client, analyst_headers, weeks):
    result = await client.get(BASE+'/metrics/roles/weekly-active', params={'weeks': weeks}, headers=analyst_headers)
    assert result.status_code == 200
    data = result.json()
    async with database.get_session_factory()() as db:
        dates = (await db.scalars(select(models.RoleWeeklyActive.week_start).distinct()
            .order_by(models.RoleWeeklyActive.week_start.desc()).limit(weeks))).all()
    assert data['weeks'] == [f'S{day.isocalendar()[1]}' for day in sorted(dates)]
    assert len(data['weeks']) <= weeks and data['computed_at']
    assert all(len(row['values']) == len(data['weeks']) for row in data['series'])
    assert len(data['week_details']) == len(data['weeks'])
    for detail, start in zip(data['week_details'], sorted(dates)):
        assert detail['start_date'] == start.isoformat()
        assert detail['end_date'] == (start+timedelta(days=6)).isoformat()
        assert isinstance(detail['is_current_week'], bool)

async def test_existing_parameter_limits_and_categories_contract(client, analyst_headers):
    for weeks in (1, 27):
        result = await client.get(BASE+'/metrics/roles/weekly-active', params={'weeks': weeks}, headers=analyst_headers)
        assert result.status_code == 422 and result.json()['error']['code'] == 'INVALID_RANGE'
    for days in (1, 30, 365):
        result = await client.get(BASE+'/support/tickets/by-category', params={'days': days}, headers=analyst_headers)
        assert result.status_code == 200
        data = result.json()
        assert data['days'] == days and 'computed_at' not in data
        counts = [row['count'] for row in data['categories']]
        assert counts == sorted(counts, reverse=True) and sum(counts) == data['total']
        if data['total']:
            assert abs(sum(row['share'] for row in data['categories'])-1) < .001
    for days in (0, 366):
        assert (await client.get(BASE+'/support/tickets/by-category', params={'days': days}, headers=analyst_headers)).status_code == 422

async def test_empty_support_keeps_csat_null_and_documents_response_zero():
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    async with async_sessionmaker(engine)() as db:
        result = await support_summary(db)
        assert result.csat_avg is None and result.csat_count == 0
        assert result.open == result.in_progress == result.waiting_user == result.resolved_30d == 0
        assert result.first_response_hours_avg == 0.0  # contrato vigente; no distingue ausencia
        assert result.deltas.open_wow == 6  # aproximación existente, no mostrarla como histórico
    await engine.dispose()

async def test_week_ranges_cross_month_year_and_use_santiago_calendar(monkeypatch):
    from app.routers.metrics_roles import weekly_active
    from app.config import get_settings
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            # UTC ya es lunes 4, pero Santiago sigue en domingo 3.
            return datetime(2027, 1, 4, 2, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr('app.periods.datetime', FixedDateTime)
    monkeypatch.setattr(get_settings(), 'business_timezone', 'America/Santiago')
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    async with async_sessionmaker(engine)() as db:
        starts = [date(2026, 10, 26), date(2026, 12, 28), date(2027, 1, 4)]
        for index, start in enumerate(starts):
            db.add(models.RoleWeeklyActive(week_start=start, role='family', active_users=index+1,
                computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        await db.flush()
        result = await weekly_active(db, 8)
        assert result.weeks == ['S44', 'S53', 'S1']  # etiquetas previas intactas
        assert result.series[0].values == [1, 2, 3]
        assert [row.start_date for row in result.week_details] == starts
        assert [row.end_date for row in result.week_details] == [date(2026, 11, 1), date(2027, 1, 3), date(2027, 1, 10)]
        assert [row.is_current_week for row in result.week_details] == [False, True, False]
    await engine.dispose()

async def test_empty_week_ranges_are_empty_and_aligned():
    from app.routers.metrics_roles import weekly_active
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    async with async_sessionmaker(engine)() as db:
        result = await weekly_active(db, 8)
        assert result.weeks == result.week_details == []
        assert all(row.values == [] for row in result.series)
    await engine.dispose()
