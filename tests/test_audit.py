from uuid import uuid4

import pytest
from sqlalchemy import func, select
from fastapi import Request

from app import database, models
from app.audit import _mask, audit

BASE = '/api/v1/admin'
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def hosted_resources(monkeypatch):
    # Esta suite aísla auditoría; los archivos reales se validan en test_game_availability.
    monkeypatch.setattr('app.routers.games_apps.ensure_resource', lambda slug: None)


async def count_logs():
    async with database._session_factory() as db:
        return await db.scalar(select(func.count()).select_from(models.AuditLog))


async def create_game(client, headers, title='Juego de prueba'):
    slug = f'test-{uuid4()}'
    response = await client.post(f'{BASE}/games-apps/', headers=headers,
                                 json={'title': title, 'slug': slug, 'category': 'Memoria',
                                       'target_url': f'/static/juegos/{slug}/index.html'})
    assert response.status_code == 201, response.text
    return response.json()


async def test_reads_failed_requests_and_interactions_do_not_write(client, admin_headers, analyst_headers):
    before = await count_logs()
    for path in ['/auth/me', '/games-apps/', '/audit-log', '/audit-log/export']:
        assert (await client.get(BASE + path, headers=admin_headers)).status_code == 200
    assert (await client.get(f'{BASE}/settings', headers=analyst_headers)).status_code == 403
    assert (await client.get(f'{BASE}/users', headers=admin_headers, params={'page_size': 1000})).status_code == 422
    assert (await client.post(f'{BASE}/audit-events', headers=admin_headers, json={'events': []})).status_code == 404
    assert (await client.post(f'{BASE}/games-apps/', headers=analyst_headers,
                              json={'title': 'Denegado', 'slug': str(uuid4()), 'category': 'Memoria'})).status_code == 403
    assert await count_logs() == before


async def test_game_changes_and_noop_save(client, admin_headers):
    game = await create_game(client, admin_headers)
    game_id = game['id']
    url = f'{BASE}/games-apps/{game_id}'
    assert (await client.put(url, headers=admin_headers, json={'title': game['title']})).status_code == 200
    rows = (await client.get(f'{BASE}/audit-log', headers=admin_headers, params={'entity_id': game_id})).json()
    assert rows['total'] == 1
    assert (await client.put(url, headers=admin_headers, json={'title': 'Título editado'})).status_code == 200
    for _ in range(2):
        assert (await client.post(url + '/toggle', headers=admin_headers)).status_code == 200
    assert (await client.delete(url, headers=admin_headers)).status_code == 204
    rows = (await client.get(f'{BASE}/audit-log', headers=admin_headers, params={'entity_id': game_id})).json()['items']
    assert len(rows) == 5
    assert {r['action'] for r in rows} == {'games.create', 'games.update', 'games.activate', 'games.deactivate', 'games.delete'}
    assert all(r['actor']['role'] == 'admin' and r['module_label'] == 'Juegos y aplicaciones' and r['metadata'] == {} for r in rows)
    edited = next(r for r in rows if r['action'] == 'games.update')
    assert edited['before']['title'] == game['title']
    assert edited['after']['title'] == edited['entity_name'] == 'Título editado'
    assert next(r for r in rows if r['action'] == 'games.activate')['action_label'] == 'Activó un juego o aplicación'
    before = await count_logs()
    assert (await client.delete(url, headers=admin_headers)).status_code == 404
    assert await count_logs() == before


async def test_old_noise_hidden_and_legacy_business_labels(client, admin_headers):
    marker = f'historial-{uuid4()}'
    async with database._session_factory() as db:
        for action in ['ui.click', 'http.request', 'auth.login', 'games.toggle']:
            db.add(models.AuditLog(action=action, actor_name=marker, entity_type='game_app',
                    after={'title': marker, 'is_active': False, '__audit': {'path': '/api/v1/admin/games-apps/', 'source': 'server'}}))
        await db.commit()
    rows = (await client.get(f'{BASE}/audit-log', headers=admin_headers, params={'q': marker})).json()
    assert rows['total'] == 2  # login ahora es auditable; clics/HTTP siguen excluidos.
    entry = next(row for row in rows['items'] if row['action'] == 'games.toggle')
    assert entry['action_label'] == 'Desactivó un juego o aplicación'
    assert entry['metadata'] == {} and '__audit' not in entry['after']
    assert (await client.get(f'{BASE}/audit-log', headers=admin_headers, params={'q': marker, 'action': 'ui.click'})).json()['total'] == 0
    csv = (await client.get(f'{BASE}/audit-log/export', headers=admin_headers, params={'q': marker})).text
    assert 'Desactivó un juego o aplicación' in csv
    assert '/api/' not in csv and 'ui.click' not in csv and 'games.toggle' not in csv


async def test_pagination_filter_export_and_masking(client, admin_headers):
    marker = f'Filtro-{uuid4()}'
    for i in range(3): await create_game(client, admin_headers, f'{marker}-{i}')
    params = {'q': marker, 'action': 'games.create', 'page_size': 2}
    first = (await client.get(f'{BASE}/audit-log', headers=admin_headers, params=params)).json()
    second = (await client.get(f'{BASE}/audit-log', headers=admin_headers, params={**params, 'page': 2})).json()
    assert first['total'] == 3 and len(first['items']) == 2 and len(second['items']) == 1
    assert {r['id'] for r in first['items']}.isdisjoint(r['id'] for r in second['items'])
    exported = await client.get(f'{BASE}/audit-log/export', headers=admin_headers, params={'q': marker})
    assert exported.status_code == 200 and exported.text.count(marker) == 3
    assert 'Creó un juego o aplicación' in exported.text and '/api/' not in exported.text
    assert _mask({'nested': [{'refresh_token': 'secret', 'PASSWORD': 'secret', 'name': 'visible'}]}) == {'nested': [{'refresh_token': '***', 'PASSWORD': '***', 'name': 'visible'}]}
    await create_game(client, admin_headers, '=IMPORTXML(1)')
    csv = (await client.get(f'{BASE}/audit-log/export', headers=admin_headers, params={'q': 'IMPORTXML'})).text
    assert "'=IMPORTXML(1)" in csv


async def test_permissions_and_dates(client, admin_headers, analyst_headers):
    for path in ['/audit-log', '/audit-log/export']:
        assert (await client.get(BASE + path)).status_code == 401
        assert (await client.get(BASE + path, headers=analyst_headers)).status_code == 403
        for start, end in [('2026-10-02T00:00:00Z', '2026-10-01T00:00:00Z'), ('2026-01-01T00:00:00Z', '2026-04-02T00:00:00Z')]:
            assert (await client.get(BASE + path, headers=admin_headers, params={'date_from': start, 'date_to': end})).status_code == 422


async def test_session_rotation_still_revokes_reuse_without_business_logs(client, admin_headers):
    before = await count_logs()
    logged = (await client.post(f'{BASE}/auth/login', json={'email': 'admin@wellq.co.uk', 'password': 'Admin123!'})).json()
    rotated = (await client.post(f'{BASE}/auth/refresh', json={'refresh_token': logged['refresh_token']})).json()
    assert (await client.post(f'{BASE}/auth/refresh', json={'refresh_token': logged['refresh_token']})).status_code == 401
    assert (await client.post(f'{BASE}/auth/refresh', json={'refresh_token': rotated['refresh_token']})).status_code == 401
    assert await count_logs() == before + 1  # Solo el login, nunca la rotación.


async def test_audit_rollback_is_atomic(client):
    marker = f'rollback-{uuid4()}'
    request = Request({'type': 'http', 'method': 'POST', 'headers': []})
    async with database._session_factory() as db:
        db.add(models.GameApp(title=marker, slug=marker, category='Memoria'))
        await audit(db, request, 'games.create', after={'title': marker})
        await db.flush()
        await db.rollback()
    async with database._session_factory() as db:
        assert await db.scalar(select(models.GameApp).where(models.GameApp.slug == marker)) is None
        assert await db.scalar(select(models.AuditLog).where(models.AuditLog.after['title'].as_string() == marker)) is None
