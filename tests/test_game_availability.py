from pathlib import Path
from uuid import uuid4
import importlib.util

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app import database, models, game_resources
from app.main import app

BASE = '/api/v1/admin/games-apps'


@pytest.fixture
def hosted_game(tmp_path, monkeypatch):
    root = tmp_path / 'juegos'
    slug = 'test-' + uuid4().hex
    folder = root / slug
    folder.mkdir(parents=True)
    (folder / 'index.html').write_text('<html><head></head><body>Juego de prueba</body></html>', encoding='utf-8')
    (folder / 'script.js').write_text('console.log("juego");', encoding='utf-8')
    monkeypatch.setattr(game_resources, 'GAME_ROOT', root)
    static = next(route.app for route in app.routes if route.name == 'static')
    monkeypatch.setattr(static, 'all_directories', [str(tmp_path)])
    return {'title': 'Juego de prueba', 'slug': slug, 'category': 'Memoria',
            'target_url': f'/static/juegos/{slug}/index.html'}


@pytest.mark.asyncio
async def test_game_lifecycle_blocks_direct_access_and_preserves_audit(client, admin_headers, hosted_game):
    created = await client.post(BASE + '/', headers=admin_headers, json=hosted_game)
    assert created.status_code == 201, created.text
    game = created.json()
    assert not game['is_active'] and game['created_by'] and game['created_by_name']
    direct = hosted_game['target_url']
    assert (await client.get(direct)).status_code == 403
    assert (await client.head(direct)).status_code == 403
    assert not any(row['id'] == game['id'] for row in (await client.get(BASE + '/active')).json())
    toggle = BASE + f'/{game["id"]}/toggle'
    assert (await client.post(toggle, headers=admin_headers)).json()['is_active']
    opened = await client.get(direct)
    assert opened.status_code == 200 and 'disponibilidad.js' in opened.text
    assert opened.headers['cache-control'] == 'no-store'
    assert (await client.head(direct)).status_code == 200
    assert not (await client.post(toggle, headers=admin_headers)).json()['is_active']
    assert (await client.get(direct)).status_code == 403
    assert (await client.get(direct.replace('index.html', 'script.js'))).status_code == 403
    assert (await client.post(toggle, headers=admin_headers)).status_code == 200
    assert (await client.delete(BASE + f'/{game["id"]}', headers=admin_headers)).status_code == 204
    assert (await client.get(direct)).status_code == 403
    audit = (await client.get('/api/v1/admin/audit-log', headers=admin_headers, params={'entity_id': game['id']})).json()['items']
    assert {row['action'] for row in audit} == {'games.create', 'games.activate', 'games.deactivate', 'games.delete'}


@pytest.mark.asyncio
async def test_sandbox_can_check_public_game_status_without_opening_admin_cors(client, admin_headers, hosted_game):
    game = (await client.post(BASE + '/', headers=admin_headers, json=hosted_game)).json()
    direct = hosted_game['target_url']
    origin = {'Origin': 'null'}
    async def check(expected):
        response = await client.head(direct, headers=origin)
        assert response.status_code == expected
        assert response.headers['access-control-allow-origin'] == '*'
        assert response.headers['cache-control'] == 'no-store'
        assert response.content == b''
    await check(403)
    await client.post(BASE + f'/{game["id"]}/toggle', headers=admin_headers)
    await check(200)
    # El GET del juego y los endpoints administrativos no ganan permisos CORS.
    assert 'access-control-allow-origin' not in (await client.get(direct, headers=origin)).headers
    for path in ('/api/v1/admin/auth/me', '/api/v1/admin/users', '/api/v1/admin/audit-log'):
        response = await client.get(path, headers={**admin_headers, **origin})
        assert response.status_code == 200
        assert 'access-control-allow-origin' not in response.headers
    assert (await client.get('/api/v1/admin/users', headers=origin)).status_code == 401
    await client.post(BASE + f'/{game["id"]}/toggle', headers=admin_headers)
    await check(403)
    await client.delete(BASE + f'/{game["id"]}', headers=admin_headers)
    await check(403)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [
    {'is_active': True}, {'title': ' '}, {'category': ''}, {'title': None},
    {'target_url': 'http://example.org/juego'}, {'target_url': 'javascript:alert(1)'},
    {'target_url': '/static/juegos/otro/index.html'}, {'description': 'x' * 4001},
])
async def test_invalid_edits_preserve_prior_game(client, admin_headers, hosted_game, change):
    created = (await client.post(BASE + '/', headers=admin_headers, json=hosted_game)).json()
    rejected = await client.put(BASE + f'/{created["id"]}', headers=admin_headers, json=change)
    assert rejected.status_code == 422, rejected.text
    current = next(row for row in (await client.get(BASE + '/', headers=admin_headers)).json() if row['id'] == created['id'])
    assert current == created


@pytest.mark.asyncio
async def test_missing_resources_and_explicit_initial_activation_rejected(client, admin_headers, hosted_game):
    assert (await client.post(BASE + '/', headers=admin_headers, json={**hosted_game, 'is_active': True})).status_code == 422
    entry = game_resources.GAME_ROOT / hosted_game['slug'] / 'index.html'
    entry.unlink()
    assert (await client.post(BASE + '/', headers=admin_headers, json=hosted_game)).status_code == 422
    entry.write_text('<html><head></head></html>', encoding='utf-8')
    created = (await client.post(BASE + '/', headers=admin_headers, json=hosted_game)).json()
    entry.unlink()
    assert (await client.post(BASE + f'/{created["id"]}/toggle', headers=admin_headers)).status_code == 422
    assert (await client.get(hosted_game['target_url'])).status_code == 403


def test_creator_migration_preserves_legacy_data():
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE games_apps (id TEXT PRIMARY KEY, title TEXT)'))
        connection.execute(sa.text("INSERT INTO games_apps VALUES ('legacy', 'Juego conservado')"))
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/0010_game_creator.py'
        spec = importlib.util.spec_from_file_location('game_creator_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade(); migration.upgrade()
        row = connection.execute(sa.text('SELECT * FROM games_apps')).mappings().one()
        assert row['title'] == 'Juego conservado' and row['created_by'] is None and row['created_by_name'] is None
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('same_path', [False, True])
async def test_external_game_activates_without_local_files_and_keeps_external_address(client, admin_headers, same_path):
    slug = 'external-' + uuid4().hex
    url = f'https://juegos.example.cl/static/juegos/{slug}/index.html' if same_path else 'https://juegos.example.cl/jugar?modo=tranquilo'
    result = await client.post(BASE + '/', headers=admin_headers, json={
        'title': 'Juego externo', 'slug': slug, 'category': 'Memoria', 'target_url': url})
    assert result.status_code == 201, result.text
    game = result.json()
    assert game['target_url'] == url and game['resource_kind'] == 'external' and not game['is_active']
    path = BASE + f'/{game["id"]}'
    assert (await client.post(path + '/toggle', headers=admin_headers)).status_code == 200
    active = (await client.get(BASE + '/active')).json()
    assert next(row for row in active if row['id'] == game['id'])['target_url'] == url
    assert (await client.post(path + '/toggle', headers=admin_headers)).status_code == 200
    assert not any(row['id'] == game['id'] for row in (await client.get(BASE + '/active')).json())


@pytest.mark.asyncio
async def test_changing_local_game_to_external_blocks_old_local_files(client, admin_headers, hosted_game):
    game = (await client.post(BASE + '/', headers=admin_headers, json=hosted_game)).json()
    path = BASE + f'/{game["id"]}'
    await client.post(path + '/toggle', headers=admin_headers)
    assert (await client.get(hosted_game['target_url'])).status_code == 200
    edited = await client.put(path, headers=admin_headers, json={'target_url': 'https://juegos.example.cl/jugar'})
    assert edited.status_code == 200 and edited.json()['resource_kind'] == 'external'
    assert edited.json()['is_active']
    assert (await client.get(hosted_game['target_url'])).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['javascript:alert(1)', 'data:text/html,prueba', '//juegos.example.cl/jugar',
                                'http://juegos.example.cl/jugar', 'https://usuario:clave@example.cl/jugar',
                                'https://example.cl:incorrecto/jugar', 'https://example.cl/mi juego'])
async def test_unsafe_external_addresses_rejected(client, admin_headers, url):
    result = await client.post(BASE + '/', headers=admin_headers, json={
        'title': 'Juego externo', 'slug': uuid4().hex, 'category': 'Memoria', 'target_url': url})
    assert result.status_code == 422, result.text
