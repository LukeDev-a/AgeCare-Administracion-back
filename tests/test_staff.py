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
    payload = {'full_name': '  Nueva administradora  ', 'email': email, 'role': 'analyst',
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


async def test_role_and_state_invalidate_all_previous_tokens(client, admin_headers):
    user = await account()
    url = f"{BASE}/users/{user['id']}"
    async def login():
        result = await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': 'Prueba123!'})
        assert result.status_code == 200
        return result.json()
    sessions = [await login(), await login()]
    assert (await client.patch(url, headers=admin_headers, json={'role': 'support'})).status_code == 200
    for session in sessions:
        assert (await client.get(f'{BASE}/auth/me', headers={'Authorization': f"Bearer {session['access_token']}"})).status_code == 401
        assert (await client.post(f'{BASE}/auth/refresh', json={'refresh_token': session['refresh_token']})).status_code == 401
    fresh = await login()
    assert fresh['admin']['role'] == 'support'
    assert (await client.patch(url, headers=admin_headers, json={'is_active': False})).status_code == 200
    assert (await client.get(f'{BASE}/auth/me', headers={'Authorization': f"Bearer {fresh['access_token']}"})).status_code == 401
    async with database._session_factory() as db:
        stored = await db.get(models.AdminUser, UUID(user['id']))
        assert stored is not None and not stored.is_active
        rows = (await db.scalars(select(models.AdminSession).where(models.AdminSession.admin_id == stored.id))).all()
        assert rows and all(row.revoked_at is not None for row in rows)
    assert (await client.patch(url, headers=admin_headers, json={'is_active': True})).status_code == 200
    assert (await client.get(f'{BASE}/auth/me', headers={'Authorization': f"Bearer {fresh['access_token']}"})).status_code == 401
    await login()


async def test_all_non_admin_roles_cannot_manage_staff(client, admin_headers):
    target = await account()
    for role in ['analyst', 'support', 'editor', 'moderator']:
        actor = await account(role)
        login = (await client.post(f'{BASE}/auth/login', json={'email': actor['email'], 'password': 'Prueba123!'})).json()
        headers = {'Authorization': f"Bearer {login['access_token']}"}
        assert (await client.get(f'{BASE}/users', headers=headers)).status_code == 403
        assert (await client.post(f'{BASE}/users', headers=headers, json={'full_name': 'Prohibida', 'email': f'{uuid4()}@wellq.co.uk', 'role': 'support'})).status_code == 403
        assert (await client.patch(f"{BASE}/users/{target['id']}", headers=headers, json={'is_active': False})).status_code == 403
        assert (await client.delete(f"{BASE}/users/{target['id']}", headers=headers)).status_code == 403
    async with database._session_factory() as db:
        assert (await db.get(models.AdminUser, UUID(target['id']))).is_active


async def test_pending_delete_removes_access_records(client, admin_headers):
    from app.account_security import decrypt
    from app.security import hash_refresh, now_utc
    from datetime import timedelta
    import json
    created = await client.post(f'{BASE}/users', headers=admin_headers, json={
        'full_name': 'Pendiente para borrar', 'email': f'{uuid4()}@wellq.co.uk', 'role': 'support'})
    assert created.status_code == 201
    user_id = UUID(created.json()['id'])
    async with database._session_factory() as db:
        invitation = await db.scalar(select(models.AdminInvitation).where(models.AdminInvitation.admin_id == user_id))
        invitation_id = invitation.id
        mail = await db.scalar(select(models.InvitationEmail).where(models.InvitationEmail.invitation_id == invitation_id))
        token = json.loads(decrypt(mail.payload_encrypted))['url'].split('#token=')[1]
        db.add(models.MfaEnrollment(admin_id=user_id, token_hash=hash_refresh(str(uuid4())),
            secret_encrypted='test-only', expires_at=now_utc() + timedelta(minutes=10)))
        await db.commit()
    assert (await client.delete(f'{BASE}/users/{user_id}', headers=admin_headers)).status_code == 204
    async with database._session_factory() as db:
        assert await db.get(models.AdminUser, user_id) is None
        for model in [models.AdminInvitation, models.MfaEnrollment, models.AdminSession]:
            assert await db.scalar(select(model).where(model.admin_id == user_id)) is None
        assert await db.scalar(select(models.InvitationEmail).where(models.InvitationEmail.invitation_id == invitation_id)) is None
    assert (await client.post(f'{BASE}/auth/invitations/inspect', json={'token': token})).status_code == 422


async def test_invited_admin_requires_mfa_despite_opt_out(client, admin_headers, monkeypatch):
    from app.config import get_settings
    from app.security import as_utc, now_utc
    monkeypatch.setattr(get_settings(), 'mfa_required_roles', '')
    monkeypatch.setattr(get_settings(), 'invitation_hours', 7)
    created = await client.post(f'{BASE}/users', headers=admin_headers, json={
        'full_name': 'Admin obligatorio', 'email': f'{uuid4()}@wellq.co.uk', 'role': 'admin', 'require_mfa': False})
    assert created.status_code == 201
    async with database._session_factory() as db:
        user = await db.get(models.AdminUser, UUID(created.json()['id']))
        assert user.mfa_required and not user.is_active
        assert 6.9 < (as_utc(user.invitation_expires_at) - now_utc()).total_seconds() / 3600 <= 7
    policy = (await client.get(f'{BASE}/users/policy', headers=admin_headers)).json()
    assert 'admin' in policy['mfa_required_roles']


async def test_pagination_and_combined_status_filters(client, admin_headers):
    prefix = f'Filtro-{uuid4()}'
    users = [await account('support', active) for active in [True, False, False]]
    for user in users:
        await client.patch(f"{BASE}/users/{user['id']}", headers=admin_headers, json={'full_name': prefix})
    params = {'q': prefix, 'role': 'support', 'account_status': 'inactive', 'page_size': 1}
    first = (await client.get(f'{BASE}/users', headers=admin_headers, params={**params, 'page': 1})).json()
    second = (await client.get(f'{BASE}/users', headers=admin_headers, params={**params, 'page': 2})).json()
    assert first['total'] == second['total'] == 2
    assert first['items'][0]['id'] != second['items'][0]['id']
    assert all(row['account_status'] == 'inactive' and row['role'] == 'support' for row in first['items'] + second['items'])
    empty = (await client.get(f'{BASE}/users', headers=admin_headers, params={**params, 'role': 'editor'})).json()
    assert empty['total'] == 0 and empty['items'] == []


async def test_promotion_requires_mfa_and_deleted_actor_history_survives(client, admin_headers):
    actor = await account()
    victim = await account()
    promoted = await client.patch(f"{BASE}/users/{actor['id']}", headers=admin_headers, json={'role': 'admin'})
    assert promoted.status_code == 200 and promoted.json()['mfa_required']
    login = await client.post(f'{BASE}/auth/login', json={'email': actor['email'], 'password': 'Prueba123!'})
    assert login.status_code == 403 and login.json()['error']['code'] == 'MFA_ENROLLMENT_REQUIRED'
    # Actor con MFA ya configurado, sin consumir TOTP real ni enviar correos.
    from app.security import create_access_token
    async with database._session_factory() as db:
        user = await db.get(models.AdminUser, UUID(actor['id']))
        user.mfa_enabled = True
        user.mfa_secret = 'test-only'
        version = user.auth_version
        await db.commit()
    headers = {'Authorization': f"Bearer {create_access_token(UUID(actor['id']), 'admin', True, version)}"}
    assert (await client.patch(f"{BASE}/users/{victim['id']}", headers=headers, json={'full_name': 'Editada por otro admin'})).status_code == 200
    assert (await client.delete(f"{BASE}/users/{actor['id']}", headers=admin_headers)).status_code == 204
    async with database._session_factory() as db:
        logs = (await db.scalars(select(models.AuditLog).where(models.AuditLog.actor_id == UUID(actor['id'])))).all()
        assert len(logs) == 1 and logs[0].actor_name == 'Cuenta de prueba'
        assert logs[0].after['full_name'] == 'Editada por otro admin'


async def test_delete_commits_before_success_response(client, admin_headers, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.main import app
    user = await account()
    committed = False
    original_commit = AsyncSession.commit
    async def commit(session):
        nonlocal committed
        await original_commit(session)
        committed = True
    monkeypatch.setattr(AsyncSession, 'commit', commit)
    async def observed_app(scope, receive, send):
        async def observed_send(message):
            if message['type'] == 'http.response.start' and message['status'] == 204:
                assert committed, 'DELETE debe confirmar transacción antes de enviar éxito'
            await send(message)
        await app(scope, receive, observed_send)
    async with AsyncClient(transport=ASGITransport(app=observed_app), base_url='http://test') as observed:
        assert (await observed.delete(f"{BASE}/users/{user['id']}", headers=admin_headers)).status_code == 204
        rows = (await observed.get(f'{BASE}/users', headers=admin_headers, params={'q': user['email']})).json()
        assert rows['total'] == 0 and rows['items'] == []


async def test_delete_unassigns_tickets_without_removing_history(client, admin_headers):
    user = await account('support')
    other = await account('support')
    async with database._session_factory() as db:
        number = (await db.scalar(select(models.Ticket.number).order_by(models.Ticket.number.desc()).limit(1))) or 0
        tickets = []
        for index, (assignee, status) in enumerate([(user, 'open'), (user, 'resolved'), (other, 'open')], 1):
            ticket = models.Ticket(number=number + index, subject='Ticket conservado', description='Detalle conservado',
                requester_name='Prueba', requester_email='test@wellq.co.uk', category='technical',
                priority='normal', status=status, assigned_to=UUID(assignee['id']))
            db.add(ticket); tickets.append(ticket)
        await db.flush()
        reply = models.TicketReply(ticket_id=tickets[0].id, author_type='admin', author_id=UUID(user['id']),
            author_name='Cuenta de prueba', body='Respuesta histórica', internal=False)
        db.add(reply); await db.commit()
        ids = [ticket.id for ticket in tickets]
        reply_id = reply.id
    assert (await client.delete(f"{BASE}/users/{user['id']}", headers=admin_headers)).status_code == 204
    async with database._session_factory() as db:
        assert await db.get(models.AdminUser, UUID(user['id'])) is None
        for ticket_id in ids[:2]:
            ticket = await db.get(models.Ticket, ticket_id)
            assert ticket.assigned_to is None and ticket.description == 'Detalle conservado'
        assert (await db.get(models.Ticket, ids[1])).status == 'resolved'
        assert (await db.get(models.Ticket, ids[2])).assigned_to == UUID(other['id'])
        stored_reply = await db.get(models.TicketReply, reply_id)
        assert stored_reply.body == 'Respuesta histórica' and stored_reply.author_name == 'Cuenta de prueba'
        log = await db.scalar(select(models.AuditLog).where(models.AuditLog.entity_id == UUID(user['id']), models.AuditLog.action == 'staff.delete'))
        assert log.after['unassigned_tickets'] == 2
