from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import database, models
from app.config import get_settings
from scripts import seed as demo

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def isolated_demo(monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as connection:
        await connection.run_sync(database.Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, '_engine', engine)
    monkeypatch.setattr(database, '_session_factory', factory)
    monkeypatch.setattr(get_settings(), 'seed_demo_enabled', True)
    monkeypatch.setattr(get_settings(), 'environment', 'dev')
    yield factory
    await engine.dispose()


async def snapshot(factory):
    async with factory() as db:
        result = {}
        for table in database.Base.metadata.tables.values():
            rows = (await db.execute(select(table))).mappings().all()
            pk = tuple(column.name for column in table.primary_key.columns)
            result[table.name] = {tuple(row[key] for key in pk): dict(row) for row in rows}
        return result


async def test_empty_installation_gets_current_demo_data_and_thirty_games(isolated_demo):
    # 0004 registra control técnico aunque no haya contenido: no bloquear la demo.
    async with isolated_demo() as db:
        db.add(models.ContentControl(key='technical-test', data={'preservar': True}))
        await db.commit()
    await demo.seed(only_empty=True)
    tables = await snapshot(isolated_demo)
    assert len(tables['games_apps']) == 30
    assert len(tables['support_tickets']) == 251
    assert len(tables['metrics_daily_users']) == 426
    assert len(tables['content_items']) == 3
    assert all(row['status'] == 'draft' and not row['tts_ready'] and row['published_at'] is None
               for row in tables['content_items'].values())
    today = datetime.now(ZoneInfo(get_settings().business_timezone)).date()
    assert max(row['day'] for row in tables['metrics_daily_users'].values()) == today
    assert tables['admin_users'] == {}  # las cuentas pertenecen al bootstrap, no a esta carga
    assert next(iter(tables['content_control'].values()))['data'] == {'preservar': True}
    before = tables
    await demo.seed(only_empty=True)
    assert await snapshot(isolated_demo) == before


async def test_runtime_migration_keys_do_not_block_legacy_settings_seed(isolated_demo):
    async with isolated_demo() as db:
        db.add_all([models.SystemSetting(key=key, value={'keep': True}, value_schema={}, description='Conservar', version=7)
                    for key in ('system_texts', 'feature_flags')])
        await db.commit()
    await demo.seed(only_empty=True)
    async with isolated_demo() as db:
        rows = {row.key: row for row in (await db.scalars(select(models.SystemSetting))).all()}
        assert set(rows) == {'system_texts', 'feature_flags', 'plan_prices', 'churn_definition', 'ops_thresholds.api_core'}
        assert rows['system_texts'].version == 7 and rows['feature_flags'].value == {'keep': True}


async def test_accounts_mfa_sessions_and_edited_values_survive_restarts(isolated_demo):
    async with isolated_demo() as db:
        user = models.AdminUser(full_name='Cuenta personalizada', email=f'{uuid4()}@wellq.co.uk',
            password_hash='hash-que-no-debe-cambiar', role='admin', is_active=True,
            mfa_enabled=True, mfa_required=True, mfa_secret='secreto-de-prueba', auth_version=7,
            recovery_hashes=['hash-prueba'])
        db.add(user); await db.flush()
        db.add(models.AdminSession(admin_id=user.id, refresh_hash=uuid4().hex,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1), mfa_verified=True, auth_version=7))
        await db.commit()
    protected = await snapshot(isolated_demo)
    await demo.seed(only_empty=True)
    async with isolated_demo() as db:
        game = await db.scalar(select(models.GameApp).where(models.GameApp.slug == 'memorama'))
        game.title = 'Mi nombre personalizado'; game.is_active = False
        setting = await db.get(models.SystemSetting, 'plan_prices')
        setting.value = {'gold': 2222, 'platinum': 9999, 'provider': 7777}; setting.version = 9
        await db.commit()
    before = await snapshot(isolated_demo)
    for table in ('admin_users', 'admin_sessions'):
        assert before[table] == protected[table]
    await demo.seed(only_empty=True)
    assert await snapshot(isolated_demo) == before
    # Vaciar SOLO un módulo permite volver a cargarlo sin tocar los demás.
    async with isolated_demo() as db:
        await db.execute(delete(models.Product)); await db.commit()
    await demo.seed(only_empty=True)
    after = await snapshot(isolated_demo)
    assert len(after['marketplace_products']) == 2
    assert {key: value for key, value in after.items() if key != 'marketplace_products'} == {
        key: value for key, value in before.items() if key != 'marketplace_products'}


async def test_partial_modules_are_not_filled_or_overwritten(isolated_demo):
    async with isolated_demo() as db:
        ticket = models.Ticket(number=42, subject='Mi ticket', description='Conservar',
            requester_name='Prueba', requester_email='test@example.org', category='other',
            priority='medium', status='open')
        feature = models.Feature(feature_key='mi_funcion', name='Mi función', applicable_roles=['family'])
        db.add_all([ticket, feature]); await db.commit()
    before = await snapshot(isolated_demo)
    await demo.seed(only_empty=True)
    after = await snapshot(isolated_demo)
    assert after['support_tickets'] == before['support_tickets']
    assert after['features'] == before['features']
    assert after['feature_usage_window'] == {}  # grupo parcial se conserva completo
    assert len(after['metrics_daily_users']) == 426


async def test_migration_game_collection_does_not_block_originals_or_resurrect_individual_deletions(isolated_demo):
    import json
    from pathlib import Path
    games = json.loads((Path(demo.__file__).resolve().parents[1] / 'app/static/juegos/nuevos.json').read_text(encoding='utf-8'))
    async with isolated_demo() as db:
        for game in games:
            db.add(models.GameApp(**game, is_active=False))
        await db.commit()
    await demo.seed(only_empty=True)
    before = await snapshot(isolated_demo)
    assert len(before['games_apps']) == 30
    assert all(not row['is_active'] for row in before['games_apps'].values() if row['slug'] == 'domino')
    async with isolated_demo() as db:
        await db.execute(delete(models.GameApp).where(models.GameApp.slug.in_(['trivia', 'reloj'])))
        await db.commit()
    expected = await snapshot(isolated_demo)
    await demo.seed(only_empty=True)
    assert await snapshot(isolated_demo) == expected


async def test_disabled_and_non_dev_do_not_mutate_data(isolated_demo, monkeypatch):
    before = await snapshot(isolated_demo)
    monkeypatch.setattr(get_settings(), 'seed_demo_enabled', False)
    await demo.seed(only_empty=True)
    assert await snapshot(isolated_demo) == before
    monkeypatch.setattr(get_settings(), 'seed_demo_enabled', True)
    for environment in ('prod', 'staging'):
        monkeypatch.setattr(get_settings(), 'environment', environment)
        with pytest.raises(RuntimeError, match='solo se permite'):
            await demo.seed(only_empty=True)
    assert await snapshot(isolated_demo) == before


async def test_initial_load_failure_rolls_back_all_modules(isolated_demo, monkeypatch):
    before = await snapshot(isolated_demo)
    def fail(_):
        raise ValueError('Catálogo de prueba inválido')
    monkeypatch.setattr(demo, 'json', SimpleNamespace(loads=fail))
    with pytest.raises(ValueError, match='Catálogo de prueba'):
        await demo.seed(only_empty=True)
    assert await snapshot(isolated_demo) == before
