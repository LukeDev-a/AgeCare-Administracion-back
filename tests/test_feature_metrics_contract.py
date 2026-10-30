"""RF08: contrato y exclusión de valores no calculables en todas las consultas."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app import database, models
from app.routers.metrics_features import adoption, top, alerts

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/admin/metrics/features'

@pytest.mark.parametrize('days', [7, 30, 90])
async def test_existing_feature_queries_and_calculation_dates(client, analyst_headers, days):
    matrix = (await client.get(BASE+'/adoption', params={'days': days}, headers=analyst_headers)).json()
    assert matrix['days'] == days and matrix['computed_at']
    assert matrix['roles'] == ['family', 'caregiver', 'elder', 'doctor']
    assert all(len(row['adoption']) == len(matrix['roles']) for row in matrix['features'])
    for row in matrix['features']:
        assert [detail['role'] for detail in row['calculation_details']] == matrix['roles']
        for value, detail in zip(row['adoption'], row['calculation_details']):
            assert (value is not None) == (detail['status'] == 'calculated')
    for limit in (1, 5):
        response = await client.get(BASE+'/top', params={'days': days, 'limit': limit}, headers=analyst_headers)
        assert response.status_code == 200
        data = response.json()
        assert data['computed_at']
        assert data['calculable_only'] is True
        for role in data['top_by_role']:
            values = [feature['adoption'] for feature in role['features']]
            assert len(values) <= limit and values == sorted(values, reverse=True)
    for threshold in (.01, .15, .5):
        response = await client.get(BASE+'/alerts', params={'days': days, 'threshold': threshold}, headers=analyst_headers)
        assert response.status_code == 200
        data = response.json()
        assert data['threshold'] == threshold and data['computed_at']
        assert data['calculable_only'] is True
        for alert in data['alerts']:
            assert len(alert['roles']) == len(alert['adoption'])
            assert all(value < threshold for value in alert['adoption'])
            assert isinstance(alert['expected_low'], bool)

async def test_invalid_windows_limits_and_thresholds_are_rejected(client, analyst_headers):
    for route in ('adoption', 'top', 'alerts'):
        for days in (6, 14, 91):
            response = await client.get(BASE+'/'+route, params={'days': days}, headers=analyst_headers)
            assert response.status_code == 422 and response.json()['error']['code'] == 'INVALID_RANGE'
    for limit in (0, 6):
        assert (await client.get(BASE+'/top', params={'limit': limit}, headers=analyst_headers)).status_code == 422
    for value in (0, .009, .501, 1):
        response = await client.get(BASE+'/alerts', params={'threshold': value}, headers=analyst_headers)
        assert response.status_code == 422 and response.json()['error']['code'] == 'INVALID_THRESHOLD'

async def test_same_window_denominator_and_strict_alert_threshold():
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    async with async_sessionmaker(engine)() as db:
        db.add(models.Feature(feature_key='test_feature', name='Prueba', applicable_roles=['elder'], expected_low=True, note='Contexto'))
        db.add(models.RoleActivityWindow(days_window=30, role='elder', active_users=20, growth_8w=0,
            sessions_per_week=1, avg_session_seconds=60, retention_30d=.5))
        db.add(models.RoleActivityWindow(days_window=7, role='elder', active_users=10, growth_8w=0,
            sessions_per_week=1, avg_session_seconds=60, retention_30d=.5))
        await db.flush()
        db.add(models.FeatureUsageWindow(days_window=30, feature_key='test_feature', role='elder', users=6))
        await db.flush()
        matrix = await adoption(db, 30)
        assert matrix.features[0].adoption == [None, None, .3, None]
        assert (await alerts(db, 30, .3)).alerts == []
        alert = (await alerts(db, 30, .31)).alerts[0]
        assert alert.expected_low and alert.note == 'Contexto' and alert.adoption == [.3]
    await engine.dispose()

async def test_missing_denominator_is_not_a_zero_ranking_or_alert():
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    async with async_sessionmaker(engine)() as db:
        db.add(models.Feature(feature_key='test_feature', name='Prueba', applicable_roles=['elder'], expected_low=False))
        await db.flush()
        matrix = await adoption(db, 30)
        assert matrix.features[0].adoption == [None, None, None, None]
        details = matrix.features[0].calculation_details
        assert details[0].status == 'not_applicable' and not details[0].applicable
        assert details[2].status == 'not_calculable' and details[2].reason == 'missing_active_users'
        ranking = await top(db, 30, 1)
        assert ranking.top_by_role[2].features == []
        assert (await alerts(db, 30, .15)).alerts == []
    await engine.dispose()

@pytest_asyncio.fixture
async def feature_db():
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    async with async_sessionmaker(engine)() as db:
        yield db
    await engine.dispose()

@pytest.mark.parametrize('applicable,active,users,status,reason,value', [
    (False, 100, 0, 'not_applicable', 'not_applicable', None),
    (True, None, None, 'not_calculable', 'missing_active_users', None),
    (True, None, 0, 'not_calculable', 'missing_active_users', None),
    (True, 0, 0, 'not_calculable', 'no_active_users', None),
    (True, 100, None, 'not_calculable', 'missing_usage', None),
    (True, -1, 0, 'not_calculable', 'invalid_data', None),
    (True, 100, -1, 'not_calculable', 'invalid_data', None),
    (True, 100, 101, 'not_calculable', 'invalid_data', None),
    (True, 100, 0, 'calculated', None, 0),
    (True, 100, 25, 'calculated', None, .25),
    (True, 1000000, 1, 'calculated', None, .000001),
])
async def test_cell_states_are_shared_by_matrix_ranking_and_alerts(feature_db, applicable, active, users, status, reason, value):
    db = feature_db
    db.add(models.Feature(feature_key='state', name='Estado', applicable_roles=['elder'] if applicable else [], expected_low=True))
    if active is not None:
        db.add(models.RoleActivityWindow(days_window=30, role='elder', active_users=active, growth_8w=0,
            sessions_per_week=0, avg_session_seconds=0, retention_30d=0))
    await db.flush()
    if users is not None:
        db.add(models.FeatureUsageWindow(days_window=30, feature_key='state', role='elder', users=users))
    await db.flush()
    matrix = await adoption(db, 30)
    detail = matrix.features[0].calculation_details[2]
    assert matrix.features[0].adoption[2] == value
    assert (detail.status, detail.reason, detail.applicable) == (status, reason, applicable)
    ranked = (await top(db, 30, 1)).top_by_role[2].features
    assert [row.adoption for row in ranked] == ([value] if status == 'calculated' else [])
    reported = (await alerts(db, 30, .15)).alerts
    assert [row.adoption for row in reported] == ([[value]] if value is not None and value < .15 else [])

async def test_ranking_filters_before_limit_and_preserves_valid_zero_alert(feature_db):
    db = feature_db
    for order, key in enumerate(('missing', 'zero', 'high')):
        db.add(models.Feature(feature_key=key, name=key, applicable_roles=['elder'], sort_order=order))
    db.add(models.RoleActivityWindow(days_window=30, role='elder', active_users=100, growth_8w=0,
        sessions_per_week=0, avg_session_seconds=0, retention_30d=0))
    await db.flush()
    db.add_all([models.FeatureUsageWindow(days_window=30, feature_key=key, role='elder', users=count)
                for key, count in [('zero', 0), ('high', 80)]])
    await db.flush()
    assert [row.feature_key for row in (await top(db, 30, 5)).top_by_role[2].features] == ['high', 'zero']
    assert [row.feature_key for row in (await top(db, 30, 1)).top_by_role[2].features] == ['high']
    assert [row.feature_key for row in (await alerts(db, 30, .15)).alerts] == ['zero']
