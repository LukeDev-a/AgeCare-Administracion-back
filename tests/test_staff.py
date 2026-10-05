from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app import database, models
from app.security import hash_password

BASE = '/api/v1/admin'
pytestmark = pytest.mark.asyncio


async def account(role='analyst', active=True):
    async with database._session_factory() as db:
        user = models.AdminUser(full_name='Cuenta de prueba', email=f'{uuid4()}@wellq.co.uk',
                                role=role, is_active=active, password_hash=hash_password('Prueba123!'))
        db.add(user); await db.commit()
        return {'id': str(user.id), 'email': user.email}


async def test_staff_permissions(client, admin_headers, analyst_headers):
    user = await account()
    for headers, expected in [({}, 401), (analyst_headers, 403)]:
        assert (await client.get(f'{BASE}/users', headers=headers)).status_code == expected
        assert (await client.post(f'{BASE}/users', headers=headers, json={'full_name': 'Nueva cuenta', 'email': f'{uuid4()}@wellq.co.uk', 'role': 'analyst'})).status_code == expected
        assert (await client.patch(f"{BASE}/users/{user['id']}", headers=headers, json={'full_name': 'Otro nombre'})).status_code == expected
        assert (await client.delete(f"{BASE}/users/{user['id']}", headers=headers)).status_code == expected


async def test_staff_edit_filter_and_audit(client, admin_headers):
    user = await account()
    email = f'{uuid4()}@wellq.co.uk'
    response = await client.patch(f"{BASE}/users/{user['id']}", headers=admin_headers,
                                  json={'full_name': 'Nombre editado', 'email': email, 'role': 'editor'})
    assert response.status_code == 200, response.text
    assert response.json()['email'] == email and response.json()['role'] == 'editor'
    filtered = (await client.get(f'{BASE}/users', headers=admin_headers, params={'q': email, 'role': 'editor', 'is_active': True})).json()
    assert filtered['total'] == 1 and filtered['items'][0]['id'] == user['id']
    logs = (await client.get(f'{BASE}/audit-log', headers=admin_headers, params={'entity_id': user['id']})).json()
    assert logs['total'] == 1 and logs['items'][0]['before']['email'] == user['email']
    assert logs['items'][0]['after']['email'] == email
    await client.patch(f"{BASE}/users/{user['id']}", headers=admin_headers, json={'full_name': 'Nombre editado'})
    assert (await client.get(f'{BASE}/audit-log', headers=admin_headers, params={'entity_id': user['id']})).json()['total'] == 1


async def test_delete_removes_login_tokens_and_keeps_history(client, admin_headers):
    user = await account()
    login = (await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': 'Prueba123!'})).json()
    await client.patch(f"{BASE}/users/{user['id']}", headers=admin_headers, json={'full_name': 'Para eliminar'})
    assert (await client.delete(f"{BASE}/users/{user['id']}", headers=admin_headers)).status_code == 204
    assert (await client.get(f'{BASE}/auth/me', headers={'Authorization': f"Bearer {login['access_token']}"})).status_code == 401
    assert (await client.post(f'{BASE}/auth/refresh', json={'refresh_token': login['refresh_token']})).status_code == 401
    assert (await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': 'Prueba123!'})).status_code == 401
    async with database._session_factory() as db:
        assert await db.scalar(select(models.AdminSession).where(models.AdminSession.admin_id == UUID(user['id']))) is None
    logs = (await client.get(f'{BASE}/audit-log', headers=admin_headers, params={'entity_id': user['id']})).json()
    assert {r['action'] for r in logs['items']} == {'staff.update', 'staff.delete'}
    deleted = next(r for r in logs['items'] if r['action'] == 'staff.delete')
    assert deleted['entity_name'] == 'Para eliminar' and deleted['action_label'] == 'Eliminó una cuenta de administración'
    assert (await client.delete(f"{BASE}/users/{user['id']}", headers=admin_headers)).status_code == 404


async def test_self_protection_and_validation(client, admin_headers):
    me = (await client.get(f'{BASE}/auth/me', headers=admin_headers)).json()
    url = f"{BASE}/users/{me['id']}"
    assert (await client.delete(url, headers=admin_headers)).status_code == 409
    assert (await client.patch(url, headers=admin_headers, json={'is_active': False})).status_code == 409
    assert (await client.patch(url, headers=admin_headers, json={'role': 'analyst'})).status_code == 409
    user = await account()
    other = await account()
    url = f"{BASE}/users/{user['id']}"
    assert (await client.patch(url, headers=admin_headers, json={'email': other['email']})).status_code == 409
    assert (await client.patch(url, headers=admin_headers, json={'email': 'staff@example.com'})).status_code == 422
    for payload in [{'email': None}, {'role': 'superadmin'}, {'is_active': None}, {'full_name': '  '}]:
        assert (await client.patch(url, headers=admin_headers, json=payload)).status_code == 422


async def test_disabled_account_refresh_rejected(client, admin_headers):
    user = await account()
    login = (await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': 'Prueba123!'})).json()
    assert (await client.patch(f"{BASE}/users/{user['id']}", headers=admin_headers, json={'is_active': False})).status_code == 200
    assert (await client.post(f'{BASE}/auth/refresh', json={'refresh_token': login['refresh_token']})).status_code == 401


async def test_create_ready_account_login_duplicate_and_audit(client, admin_headers):
    email = f'{uuid4()}@wellq.co.uk'
    payload = {'full_name': '  Nueva administradora  ', 'email': email, 'role': 'admin',
               'password': 'Nueva123!', 'require_mfa': False}
    response = await client.post(f'{BASE}/users', headers=admin_headers, json=payload)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created['is_active'] is True and created['invitation_expires_at'] is None
    assert 'password' not in response.text
    login = await client.post(f'{BASE}/auth/login', json={'email': email, 'password': payload['password']})
    assert login.status_code == 200 and login.json()['admin']['full_name'] == 'Nueva administradora'
    assert (await client.post(f'{BASE}/users', headers=admin_headers, json=payload)).status_code == 409
    assert (await client.post(f'{BASE}/users', headers=admin_headers, json={**payload, 'email': 'una@example.com'})).status_code == 422
    logs = (await client.get(f'{BASE}/audit-log', headers=admin_headers, params={'entity_id': created['id']})).json()
    assert logs['total'] == 1 and logs['items'][0]['entity_name'] == 'Nueva administradora'
    assert payload['password'] not in str(logs) and 'password_hash' not in str(logs)
    await client.delete(f"{BASE}/users/{created['id']}", headers=admin_headers)


async def test_invitation_compatibility_and_credentials_validation(client, admin_headers):
    payload = {'full_name': 'Pendiente', 'email': f'{uuid4()}@wellq.co.uk', 'role': 'admin'}
    response = await client.post(f'{BASE}/users', headers=admin_headers, json=payload)
    assert response.status_code == 201 and not response.json()['is_active']
    assert response.json()['invitation_expires_at']
    assert (await client.patch(f"{BASE}/users/{response.json()['id']}", headers=admin_headers, json={'is_active': True})).status_code == 409
    direct = await client.post(f'{BASE}/users', headers=admin_headers, json={**payload, 'email': f'{uuid4()}@wellq.co.uk', 'password': 'Nueva123!'})
    assert direct.status_code == 201
    login = await client.post(f'{BASE}/auth/login', json={'email': direct.json()['email'], 'password': 'Nueva123!'})
    assert login.status_code == 403 and login.json()['error']['code'] == 'MFA_ENROLLMENT_REQUIRED'
    for extra in [{'password': 'short', 'require_mfa': False}, {'full_name': '   '}, {'role': 'root'}]:
        assert (await client.post(f'{BASE}/users', headers=admin_headers, json={**payload, 'email': f'{uuid4()}@wellq.co.uk', **extra})).status_code == 422
