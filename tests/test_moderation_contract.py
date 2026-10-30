from datetime import timedelta
from uuid import UUID, uuid4
import pytest
from app import database, models
from app.security import create_access_token, now_utc

BASE = '/api/v1/admin/moderation/queue'
pytestmark = pytest.mark.asyncio


async def item(**values):
    async with database._session_factory() as db:
        row = models.ModerationItem(type='review', content={'text': 'Texto revisable'},
                                    author_name='Autor de prueba', status='pending')
        for key, value in values.items():
            setattr(row, key, value)
        db.add(row); await db.commit()
        return str(row.id)


async def test_real_notes_reasons_history_and_duplicate_decision(client, admin_headers):
    identity = await item()
    path = BASE + '/' + identity
    rejected = await client.post(path + '/reject', headers=admin_headers, json={'reason_code': 'other', 'note': '   '})
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'NOTE_REQUIRED'
    approved = await client.post(path + '/approve', headers=admin_headers, json={'note': '  Texto revisado  '})
    assert approved.status_code == 200, approved.text
    value = approved.json()
    assert value['decision_note'] == 'Texto revisado' and value['decided_by_name'] and value['decided_at']
    duplicate = await client.post(path + '/reject', headers=admin_headers, json={'reason_code': 'spam'})
    assert duplicate.status_code == 409 and duplicate.json()['error']['code'] == 'ALREADY_MODERATED'
    second = await item()
    result = await client.post(BASE + '/' + second + '/reject', headers=admin_headers,
                               json={'reason_code': 'offensive', 'note': 'Motivo registrado'})
    assert result.status_code == 200 and result.json()['reject_reason_code'] == 'offensive'
    history = (await client.get(BASE, headers=admin_headers, params={'status': 'rejected'})).json()['items']
    assert next(row for row in history if row['id'] == second)['decision_note'] == 'Motivo registrado'
    logs = (await client.get('/api/v1/admin/audit-log', headers=admin_headers, params={'entity_id': second})).json()['items']
    assert len(logs) == 1 and logs[0]['after']['reason'] == 'offensive'
    assert logs[0]['before']['status'] == 'pending' and logs[0]['after']['status'] == 'rejected'


@pytest.mark.parametrize('kind', ['photo', 'chat_message'])
async def test_protected_content_not_returned_or_decided_without_temporary_access(client, admin_headers, kind):
    identity = await item(type=kind, content={'text': 'Contenido privado de prueba', 'url': 'https://example.cl/privado'})
    page = await client.get(BASE, headers=admin_headers, params={'type': kind})
    row = next(row for row in page.json()['items'] if row['id'] == identity)
    assert row['content'] == {} and row['content_available'] is False
    for action, body in [('approve', {}), ('reject', {'reason_code': 'privacy'})]:
        result = await client.post(BASE + '/' + identity + '/' + action, headers=admin_headers, json=body)
        assert result.status_code == 409 and result.json()['error']['code'] == 'CONTENT_UNAVAILABLE'
    async with database._session_factory() as db:
        row = await db.get(models.ModerationItem, UUID(identity))
        assert row.status == 'pending'  # No se altera ni elimina el dato existente.


async def test_priority_pagination_default_and_note_limit(client, admin_headers):
    first = await item(type='caregiver_profile', is_safety=False, created_at=now_utc() - timedelta(days=3))
    safety = await item(type='caregiver_profile', is_safety=True, created_at=now_utc())
    params = {'type': 'caregiver_profile', 'page_size': 1}
    page = (await client.get(BASE, headers=admin_headers, params=params)).json()
    assert page['items'][0]['id'] == safety and page['items'][0]['is_safety']
    second = (await client.get(BASE, headers=admin_headers, params={**params, 'page': 2})).json()
    assert second['items'][0]['id'] == first
    too_long = await client.post(BASE + '/' + first + '/approve', headers=admin_headers, json={'note': 'x' * 1001})
    assert too_long.status_code == 422


@pytest.mark.parametrize('role', ['admin', 'moderator', 'editor', 'analyst', 'support', None])
@pytest.mark.parametrize('action', ['approve', 'reject'])
async def test_decision_permissions_and_rejection_without_mutation(client, role, action):
    identity = await item()
    async with database._session_factory() as db:
        actor = models.AdminUser(full_name='Revisor de prueba', email=f'{uuid4()}@example.cl', role=role or 'admin', is_active=True)
        db.add(actor); await db.commit(); actor_id = actor.id
    headers = {'Authorization': 'Bearer ' + create_access_token(actor_id, role)} if role else {}
    result = await client.post(BASE + '/' + identity + '/' + action, headers=headers,
                               json={} if action == 'approve' else {'reason_code': 'spam'})
    allowed = role in ('admin', 'moderator')
    assert result.status_code == (200 if allowed else 403 if role else 401), result.text
    async with database._session_factory() as db:
        row = await db.get(models.ModerationItem, UUID(identity))
        assert row.status == (('approved' if action == 'approve' else 'rejected') if allowed else 'pending')
