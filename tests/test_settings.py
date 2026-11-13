from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app import database, models
from app.security import create_access_token, hash_password

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/admin'


async def make_setting():
    async with database.get_session_factory()() as db:
        row = models.SystemSetting(key=f'test_setting_{uuid4().hex}', description='Parámetro de prueba',
            value={'limit': 10, 'enabled': True}, value_schema={'type': 'object',
                'properties': {'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100},
                               'enabled': {'type': 'boolean'}},
                'required': ['limit', 'enabled'], 'additionalProperties': False})
        db.add(row); await db.commit()
        return row.key


async def audit_count():
    async with database.get_session_factory()() as db:
        return await db.scalar(select(func.count()).select_from(models.AuditLog))


async def test_read_update_version_responsible_and_audit(client, admin_headers):
    key = await make_setting()
    result = await client.get(f'{BASE}/settings', headers=admin_headers, params={'key': key})
    row = result.json()['settings'][0]
    assert row['version'] == 1 and row['updated_by'] is None
    assert any(s['key'] == key for s in (await client.get(f'{BASE}/settings', headers=admin_headers)).json()['settings'])
    count = await audit_count()
    payload = {'value': {'limit': 20, 'enabled': False}, 'version': 1, 'change_note': '  Ajuste operativo  '}
    saved = await client.put(f'{BASE}/settings/{key}', headers=admin_headers, json=payload)
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data['value'] == payload['value'] and data['version'] == 2
    assert data['updated_at'] and data['updated_by']['name']
    assert await audit_count() == count + 1
    async with database.get_session_factory()() as db:
        log = await db.scalar(select(models.AuditLog).where(models.AuditLog.action == 'settings.update',
            models.AuditLog.after['key'].as_string() == key).order_by(models.AuditLog.created_at.desc()))
        assert log.after['note'] == 'Ajuste operativo'
        assert log.after['key'] == key and log.after['name'] == 'Parámetro de prueba'
    conflict = await client.put(f'{BASE}/settings/{key}', headers=admin_headers, json=payload)
    assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'VERSION_CONFLICT'
    assert await audit_count() == count + 1
    assert (await client.get(f'{BASE}/settings', headers=admin_headers, params={'key': key})).json()['settings'][0] == data


async def test_invalid_values_and_notes_do_not_change_setting(client, admin_headers):
    key = await make_setting()
    original = (await client.get(f'{BASE}/settings', headers=admin_headers, params={'key': key})).json()
    count = await audit_count()
    for value in [{'limit': 0, 'enabled': True}, {'limit': 2.5, 'enabled': True},
                  {'limit': 10}, {'limit': 10, 'enabled': 'yes'}, {'limit': 10, 'enabled': True, 'extra': 2}]:
        response = await client.put(f'{BASE}/settings/{key}', headers=admin_headers,
            json={'value': value, 'version': 1, 'change_note': 'Prueba inválida'})
        assert response.status_code == 422 and response.json()['error']['code'] == 'INVALID_VALUE'
    for note in ['', '     ', 'abcd', 'x' * 501]:
        assert (await client.put(f'{BASE}/settings/{key}', headers=admin_headers,
            json={'value': {'limit': 20, 'enabled': True}, 'version': 1, 'change_note': note})).status_code == 422
    assert (await client.get(f'{BASE}/settings', headers=admin_headers, params={'key': key})).json() == original
    assert await audit_count() == count


@pytest.mark.parametrize('role', ['analyst', 'support', 'editor', 'moderator'])
async def test_other_roles_cannot_read_or_modify(client, role):
    key = await make_setting()
    async with database.get_session_factory()() as db:
        user = models.AdminUser(full_name='Sin permiso', email=f'{uuid4()}@wellq.co.uk', role=role,
            is_active=True, password_hash=hash_password('Prueba123!'))
        db.add(user); await db.commit()
        headers = {'Authorization': f'Bearer {create_access_token(user.id, role)}'}
    assert (await client.get(f'{BASE}/settings', headers=headers)).status_code == 403
    assert (await client.put(f'{BASE}/settings/{key}', headers=headers,
        json={'value': {'limit': 20, 'enabled': False}, 'version': 1, 'change_note': 'Cambio denegado'})).status_code == 403
    async with database.get_session_factory()() as db:
        row = await db.get(models.SystemSetting, key)
        assert row.version == 1 and row.value['limit'] == 10


async def test_unknown_key_and_missing_auth(client, admin_headers):
    key = f'unknown_{uuid4().hex}'
    for response in [await client.get(f'{BASE}/settings', headers=admin_headers, params={'key': key}),
                     await client.put(f'{BASE}/settings/{key}', headers=admin_headers,
                         json={'value': 1, 'version': 1, 'change_note': 'Clave inexistente'})]:
        assert response.status_code == 404 and response.json()['error']['code'] == 'UNKNOWN_SETTING'
    assert (await client.get(f'{BASE}/settings')).status_code == 401


async def test_plan_prices_update_preserves_historical_metrics(client, admin_headers):
    before = (await client.get(f'{BASE}/metrics/commercial/plans', headers=admin_headers)).json()
    assert before['plans']
    assert all(row['billing_unit'] == 'account' and row['billing_period'] == 'month'
               for row in before['plans'])
    setting = (await client.get(f'{BASE}/settings', headers=admin_headers,
                               params={'key': 'plan_prices'})).json()['settings'][0]
    prices = {**setting['value'], 'gold': setting['value']['gold'] + 100}
    count = await audit_count()
    payload = {'value': prices, 'version': setting['version'], 'change_note': 'Ajuste de tarifa mensual por cuenta'}
    saved = await client.put(f'{BASE}/settings/plan_prices', headers=admin_headers, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()['value'] == prices
    assert saved.json()['version'] == setting['version'] + 1
    assert await audit_count() == count + 1
    after = (await client.get(f'{BASE}/metrics/commercial/plans', headers=admin_headers)).json()
    assert after == before  # tarifa vigente y registro histórico son fuentes distintas
    invalid = await client.put(f'{BASE}/settings/plan_prices', headers=admin_headers,
        json={**payload, 'version': saved.json()['version'], 'value': {**prices, 'gold': -1}})
    assert invalid.status_code == 422 and invalid.json()['error']['code'] == 'INVALID_VALUE'
    current = (await client.get(f'{BASE}/settings', headers=admin_headers,
                               params={'key': 'plan_prices'})).json()['settings'][0]
    assert current == saved.json()
