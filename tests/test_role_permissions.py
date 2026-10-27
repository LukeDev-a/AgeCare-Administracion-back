"""RF03: API real mediante ASGI, exclusivamente con la BD aislada de pytest."""
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app import database, models
from app.security import create_access_token, hash_password

BASE = '/api/v1/admin'
ROLES = ('admin', 'analyst', 'support', 'editor', 'moderator')
READ_ROLES = {
    '/metrics/commercial/summary?period=current_month': {'admin', 'analyst', 'support'},
    '/metrics/commercial/registrations?period=current_month': {'admin', 'analyst', 'support'},
    '/metrics/commercial/plans': {'admin', 'analyst', 'support'},
    '/metrics/commercial/funnel': {'admin', 'analyst', 'support'},
    '/ops/status': {'admin', 'analyst', 'support'},
    '/ops/latency': {'admin', 'analyst', 'support'},
    '/ops/critical-processes': {'admin', 'analyst', 'support'},
    '/support/tickets': {'admin', 'analyst', 'support'},
    '/games-apps/': set(ROLES),
    '/content/items': {'admin', 'editor'},
    '/marketplace/products': {'admin', 'editor', 'moderator'},
    '/moderation/queue': {'admin', 'moderator'},
    '/users': {'admin'}, '/settings': {'admin'},
    '/legal/documents': {'admin'}, '/audit-log': {'admin'},
}
pytestmark = pytest.mark.asyncio


async def actor(role):
    async with database._session_factory() as db:
        user = models.AdminUser(full_name='Prueba RF03', email=f'{uuid4()}@wellq.co.uk',
            role=role, password_hash=hash_password('Prueba123!'), is_active=True)
        db.add(user)
        await db.commit()
        return user.id, user.email, {'Authorization': 'Bearer ' + create_access_token(user.id, role)}


async def business_snapshot():
    # Comparar todas las columnas de negocio, no solo el estado HTTP.
    async with database._session_factory() as db:
        return {table.name: {str(tuple(row)): dict(row) for row in
            (await db.execute(select(table))).mappings().all()}
            for table in [model.__table__ for model in (models.GameApp, models.ContentItem,
                models.Incident, models.Ticket, models.Product, models.ModerationItem,
                models.SystemSetting, models.LegalVersion, models.AdminUser)]}


@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer token-invalido'}])
async def test_protected_reads_without_valid_session_return_401(client, headers):
    for path in READ_ROLES:
        response = await client.get(BASE + path, headers=headers)
        assert response.status_code == 401, (path, response.text)


@pytest.mark.parametrize('role', ROLES)
async def test_read_access_matrix_profile_and_logout_for_every_role(client, role):
    _, email, headers = await actor(role)
    for path, allowed in READ_ROLES.items():
        response = await client.get(BASE + path, headers=headers)
        assert response.status_code == (200 if role in allowed else 403), (role, path, response.text)
    profile = await client.get(BASE + '/auth/me', headers=headers)
    assert profile.status_code == 200 and profile.json()['role'] == role
    logged = await client.post(BASE + '/auth/login', json={'email': email, 'password': 'Prueba123!'})
    assert logged.status_code == 200, logged.text
    data = logged.json()
    own = {'Authorization': 'Bearer ' + data['access_token']}
    assert (await client.post(BASE + '/auth/logout', headers=own,
        json={'refresh_token': data['refresh_token']})).status_code == 204
    assert (await client.post(BASE + '/auth/refresh',
        json={'refresh_token': data['refresh_token']})).status_code == 401


@pytest.mark.parametrize('role', (*ROLES, None))
async def test_every_game_mutation_by_role_and_no_changes_on_rejection(client, role):
    headers = (await actor(role))[2] if role else {}
    async with database._session_factory() as db:
        target = models.GameApp(slug=uuid4().hex, title='Juego intacto', category='Prueba', is_active=True)
        db.add(target); await db.commit(); target_id = str(target.id)
    expected = 401 if role is None else 403
    allowed = role in ('admin', 'editor')
    calls = [
        ('POST', '/games-apps/', {'slug': uuid4().hex, 'title': 'Juego nuevo', 'category': 'Prueba'}, 201),
        ('PUT', f'/games-apps/{target_id}', {'title': 'Título modificado'}, 200),
        ('POST', f'/games-apps/{target_id}/toggle', None, 200),
        ('POST', f'/games-apps/{target_id}/toggle', None, 200),
        ('DELETE', f'/games-apps/{target_id}', None, 204),
    ]
    for method, path, body, success in calls:
        before = await business_snapshot()
        response = await client.request(method, BASE + path, headers=headers, **({'json': body} if body else {}))
        assert response.status_code == (success if allowed else expected), (role, method, path, response.text)
        if not allowed:
            assert await business_snapshot() == before


@pytest.mark.parametrize('role', (*ROLES, None))
async def test_write_separation_admin_exclusivity_and_rejections_preserve_data(client, role):
    headers = (await actor(role))[2] if role else {}
    async with database._session_factory() as db:
        content = models.ContentItem(type='news', title='Borrador RF03', body='Texto de prueba', tags=[])
        product = models.Product(name='Producto RF03', category='Prueba', vendor='Prueba', external_url='https://example.org')
        moderation = models.ModerationItem(type='review', content={'text': 'Prueba'}, author_name='Prueba')
        incident = models.Incident(title='Incidente RF03', severity='degraded', status='investigating',
            description='Descripción original', started_at=date.today())
        ticket = models.Ticket(number=uuid4().int % 1000000000, subject='Ticket RF03', description='Prueba',
            requester_name='Prueba', requester_email='test@wellq.co.uk', category='account_access',
            priority='medium', status='open', channel='console')
        setting = models.SystemSetting(key='rf03.' + uuid4().hex, value=1,
            value_schema={'type': 'integer'}, description='Prueba RF03')
        db.add_all([content, product, moderation, incident, ticket, setting]); await db.commit()
        ids = [str(item.id) for item in (content, product, moderation, incident, ticket)]
        key = setting.key
    content_id, product_id, moderation_id, incident_id, ticket_id = ids
    calls = [
        ('PATCH', f'/ops/incidents/{incident_id}', {'description': 'Actualizado'}, {'admin', 'support'}, 200),
        ('PATCH', f'/support/tickets/{ticket_id}', {'priority': 'high'}, {'admin', 'support'}, 200),
        ('PATCH', f'/content/items/{content_id}', {'title': 'Texto editado RF03'}, {'admin', 'editor'}, 200),
        ('DELETE', f'/content/items/{content_id}', None, {'admin'}, 204),
        ('PATCH', f'/marketplace/products/{product_id}', {'name': 'Nombre editado'}, {'admin', 'editor'}, 200),
        ('POST', f'/moderation/queue/{moderation_id}/approve', {}, {'admin', 'moderator'}, 200),
        ('PUT', f'/settings/{key}', {'value': 2, 'version': 1, 'change_note': 'Prueba RF03'}, {'admin'}, 200),
        ('POST', '/legal/documents/terms/versions', {'semver': f'99999.{uuid4().int}',
            'content_md': 'Texto legal de prueba. ' * 10, 'changelog': 'Prueba permisos RF03',
            'effective_date': (date.today() + timedelta(days=30)).isoformat()}, {'admin'}, 201),
        ('POST', '/users', {'full_name': 'Invitada RF03', 'email': f'{uuid4()}@wellq.co.uk',
            'role': 'support'}, {'admin'}, 201),
    ]
    for method, path, body, allowed, success in calls:
        before = await business_snapshot()
        response = await client.request(method, BASE + path, headers=headers, **({'json': body} if body is not None else {}))
        expected = success if role in allowed else (401 if role is None else 403)
        assert response.status_code == expected, (role, method, path, response.text)
        if role not in allowed:
            assert await business_snapshot() == before


@pytest.mark.parametrize('old_role,new_role', [('admin', 'analyst'), ('analyst', 'editor'),
    ('editor', 'moderator'), ('moderator', 'support'), ('support', 'analyst')])
async def test_role_change_revokes_all_sessions_and_new_login_obeys_new_role(client, admin_headers, old_role, new_role):
    user_id, email, _ = await actor(old_role)
    async def login():
        response = await client.post(BASE + '/auth/login', json={'email': email, 'password': 'Prueba123!'})
        assert response.status_code == 200, response.text
        return response.json()
    sessions = [await login(), await login(), await login()]
    changed = await client.patch(f'{BASE}/users/{user_id}', headers=admin_headers, json={'role': new_role})
    assert changed.status_code == 200, changed.text
    for session in sessions:
        stale = {'Authorization': 'Bearer ' + session['access_token']}
        assert (await client.get(BASE + '/auth/me', headers=stale)).status_code == 401
        assert (await client.get(BASE + '/games-apps/', headers=stale)).status_code == 401
        assert (await client.post(BASE + '/auth/refresh', json={'refresh_token': session['refresh_token']})).status_code == 401
    fresh = await login()
    headers = {'Authorization': 'Bearer ' + fresh['access_token']}
    profile = (await client.get(BASE + '/auth/me', headers=headers)).json()
    expected_modules = {path: new_role in allowed for path, allowed in READ_ROLES.items()}
    assert profile['role'] == new_role
    assert ('content' in profile['permissions']) == (new_role == 'editor')
    for path, permitted in expected_modules.items():
        assert (await client.get(BASE + path, headers=headers)).status_code == (200 if permitted else 403)
