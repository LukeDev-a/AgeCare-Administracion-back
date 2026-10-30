from uuid import uuid4

import pytest
from app import database, models

BASE = '/api/v1/admin/support'
pytestmark = pytest.mark.asyncio


async def new_ticket(client, headers, **extra):
    payload = dict(subject=f'Fase nueve {uuid4()}', description='Descripción de prueba',
                   user_email=f'{uuid4()}@example.com', category='other', confirm_unlinked=True)
    result = await client.post(BASE + '/tickets', headers=headers, json={**payload, **extra})
    assert result.status_code == 201, result.text
    return result.json()


@pytest.mark.parametrize('role,active,allowed', [
    ('admin', True, True), ('support', True, True), ('analyst', True, False),
    ('editor', True, False), ('moderator', True, False), ('support', False, False),
])
async def test_only_active_managers_can_be_assigned(client, admin_headers, role, active, allowed):
    async with database._session_factory() as db:
        agent = models.AdminUser(full_name='Agente fase nueve', email=f'{uuid4()}@example.com',
                                 role=role, is_active=active)
        db.add(agent)
        await db.commit()
        agent_id = str(agent.id)
    catalog = (await client.get(BASE + '/agents', headers=admin_headers)).json()
    assert any(row['id'] == agent_id for row in catalog) == allowed
    ticket = await new_ticket(client, admin_headers)
    result = await client.patch(BASE + f'/tickets/{ticket["id"]}', headers=admin_headers,
                               json={'assigned_to': agent_id, 'priority': 'critical'})
    assert result.status_code == (200 if allowed else 404)
    detail = (await client.get(BASE + f'/tickets/{ticket["id"]}', headers=admin_headers)).json()
    assert detail['priority'] == ('critical' if allowed else 'medium')
    assert (detail['assigned_to'] is not None) == allowed


async def test_combined_filters_and_priority_severity(client, admin_headers):
    marker = 'Filtro ' + str(uuid4())
    for priority in ['high', 'low', 'critical', 'medium']:
        await new_ticket(client, admin_headers, subject=marker, priority=priority)
    result = await client.get(BASE + '/tickets', headers=admin_headers,
                              params={'q': marker, 'category': 'other', 'status': 'open',
                                      'order': '-priority', 'page_size': 2})
    assert result.status_code == 200
    assert result.json()['total'] == 4
    assert [row['priority'] for row in result.json()['items']] == ['critical', 'high']
    result = await client.get(BASE + '/tickets', headers=admin_headers,
                              params={'q': marker, 'priority': 'low', 'category': 'other', 'status': 'open'})
    assert result.json()['total'] == 1
    assert result.json()['items'][0]['priority'] == 'low'
    assert (await client.get(BASE + '/tickets', headers=admin_headers,
                             params={'q': 'x' * 121})).status_code == 422


async def test_public_reply_note_and_paginated_history(client, admin_headers):
    ticket = await new_ticket(client, admin_headers)
    path = BASE + f'/tickets/{ticket["id"]}'
    assert ticket['status'] == 'open' and ticket['priority'] == 'medium' and ticket['channel'] == 'console'
    for internal in [True, False, True]:
        result = await client.post(path + '/replies', headers=admin_headers,
                                   json={'body': 'Nota' if internal else 'Respuesta', 'internal': internal})
        assert result.status_code == 201
        detail = (await client.get(path, headers=admin_headers)).json()
        if detail['replies_count'] == 1:
            assert detail['first_response_at'] is None
        else:
            assert detail['first_response_at'] is not None
    second = (await client.get(path + '/replies', headers=admin_headers,
                               params={'page': 2, 'page_size': 2})).json()
    assert second['total'] == 3 and len(second['items']) == 1 and second['page'] == 2
    first = (await client.get(path + '/replies', headers=admin_headers,
                              params={'page': 1, 'page_size': 2})).json()
    assert not set(row['id'] for row in first['items']) & set(row['id'] for row in second['items'])
    assert [row['created_at'] for row in first['items'] + second['items']] == sorted(row['created_at'] for row in first['items'] + second['items'])


async def test_patch_omission_null_and_rejected_transition(client, admin_headers):
    agent = (await client.get(BASE + '/agents', headers=admin_headers)).json()[0]
    ticket = await new_ticket(client, admin_headers)
    path = BASE + f'/tickets/{ticket["id"]}'
    assert (await client.patch(path, headers=admin_headers, json={'assigned_to': agent['id']})).status_code == 200
    result = await client.patch(path, headers=admin_headers, json={'category': 'billing_plans'})
    assert result.json()['assigned_to']['admin_id'] == agent['id']
    result = await client.patch(path, headers=admin_headers, json={'status': 'closed', 'priority': 'critical'})
    assert result.status_code == 409
    detail = (await client.get(path, headers=admin_headers)).json()
    assert detail['status'] == 'open' and detail['priority'] == 'medium'
    result = await client.patch(path, headers=admin_headers, json={'assigned_to': None})
    assert result.json()['assigned_to'] is None
