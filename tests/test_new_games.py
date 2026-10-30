import importlib.util
from pathlib import Path
from uuid import uuid4
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app import models, database
from app.config import get_settings


def test_register_new_games_preserves_existing_values_and_is_idempotent():
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        models.GameApp.__table__.create(connection)
        connection.execute(models.GameApp.__table__.insert().values(slug='domino', title='Título personalizado',
            category='Personalizada', item_type='game', is_active=True, target_url='https://example.org/propio'))
        file = Path(__file__).resolve().parents[1] / 'alembic/versions/0005_new_games.py'
        spec = importlib.util.spec_from_file_location('new_games_migration', file)
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade(); migration.upgrade()
        rows = connection.execute(sa.select(models.GameApp.__table__)).mappings().all()
        assert len(rows) == 10
        old = next(row for row in rows if row['slug'] == 'domino')
        assert old['title'] == 'Título personalizado' and old['is_active']
        assert all(not row['is_active'] for row in rows if row['slug'] != 'domino')
        migration.downgrade()
        assert connection.execute(sa.select(sa.func.count()).select_from(models.GameApp.__table__)).scalar() == 10
    engine.dispose()


@pytest.mark.asyncio
async def test_catalog_resolves_relative_game_urls(client, admin_headers, monkeypatch):
    monkeypatch.setattr('app.routers.games_apps.ensure_resource', lambda slug: None)
    monkeypatch.setattr(get_settings(), 'game_public_base_url', '')
    slug = 'prueba-' + uuid4().hex
    response = await client.post('/api/v1/admin/games-apps/', headers=admin_headers, json={
        'title': 'Juego portable', 'slug': slug, 'category': 'Prueba',
        'target_url': f'/static/juegos/{slug}/index.html'})
    assert response.status_code == 201
    assert not set(('icon_url', 'banner_url', 'preview_image_url', 'sort_order', 'accessibility')).intersection(response.json())
    assert response.json()['target_url'] == f'http://test/static/juegos/{slug}/index.html'
    assert not response.json()['is_active']
    assert (await client.post(f'/api/v1/admin/games-apps/{response.json()["id"]}/toggle', headers=admin_headers)).status_code == 200
    monkeypatch.setattr(get_settings(), 'game_public_base_url', 'https://games.example.org/agecare')
    items = (await client.get('/api/v1/admin/games-apps/active')).json()
    item = next(row for row in items if row['slug'] == slug)
    assert item['target_url'] == f'https://games.example.org/agecare/static/juegos/{slug}/index.html'


def test_simplify_games_migration_preserves_game_and_other_fields():
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        models.GameApp.__table__.create(connection)
        table = models.GameApp.__table__
        connection.execute(table.insert().values(slug='conservar', title='Juego conservado',
            category='Prueba', target_url='/static/juegos/domino/index.html',
            featured=True, min_tier='dorado', updated_by_name='Responsable'))
        file = Path(__file__).resolve().parents[1] / 'alembic/versions/0006_simplify_games.py'
        spec = importlib.util.spec_from_file_location('simplify_games_migration', file)
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        migration.op = Operations(MigrationContext.configure(connection))
        # Simular estructura anterior y poblarla antes de migrar.
        migration.downgrade()
        connection.execute(sa.text("UPDATE games_apps SET icon_url='icon.png', banner_url='banner.png', "
            "preview_image_url='preview.png', sort_order=20, accessibility='{}'"))
        migration.upgrade()
        migration.upgrade()  # También soporta esquemas nuevos sin esas columnas.
        columns = {column['name'] for column in sa.inspect(connection).get_columns('games_apps')}
        assert not columns.intersection(migration.REMOVED)
        row = connection.execute(sa.select(table)).mappings().one()
        assert row['title'] == 'Juego conservado'
        assert row['featured'] and row['min_tier'] == 'dorado'
        assert row['updated_by_name'] == 'Responsable'
        assert row['target_url'] == '/static/juegos/domino/index.html'
        assert 'deleted_at' in columns and 'updated_by' in columns
    engine.dispose()
