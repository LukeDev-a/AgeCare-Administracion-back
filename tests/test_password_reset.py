import json
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update

from app import database, models, password_reset
from app.account_security import decrypt, encrypt
from app.security import hash_password, hash_refresh, now_utc, verify_password

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/admin'


@pytest_asyncio.fixture
async def account(client):
    async with database.get_session_factory()() as db:
        assert db.bind.url.drivername == 'sqlite+aiosqlite'
        await db.execute(delete(models.AdminPasswordReset))
        user = models.AdminUser(full_name='Recuperación de prueba', email=f'{uuid4()}@wellq.co.uk',
            password_hash=hash_password('Anterior123!'), role='support', is_active=True, mfa_enabled=False)
        db.add(user)
        await db.commit()
        return user


async def issue(client, user):
    response = await client.post(f'{BASE}/auth/password-reset/request', json={'email': user.email})
    assert response.status_code == 202
    async with database.get_session_factory()() as db:
        row = await db.scalar(select(models.AdminPasswordReset).where(models.AdminPasswordReset.admin_id == user.id)
                              .order_by(models.AdminPasswordReset.created_at.desc()))
        token = json.loads(decrypt(row.payload_encrypted))['url'].split('#token=')[1]
        assert row.token_hash == hash_refresh(token) and token not in row.payload_encrypted
        return token, row.id


async def test_reset_revokes_access_refresh_and_preserves_mfa(client, account, monkeypatch):
    login = await client.post(f'{BASE}/auth/login', json={'email': account.email, 'password': 'Anterior123!'})
    session = login.json()
    async with database.get_session_factory()() as db:
        user = await db.get(models.AdminUser, account.id)
        user.mfa_enabled = True
        user.mfa_secret = encrypt('JBSWY3DPEHPK3PXP')
        user.recovery_hashes = ['previous-hash']
        await db.commit()
    token, row_id = await issue(client, account)
    sent = []
    monkeypatch.setattr(password_reset, 'send_reset', sent.append)
    assert await password_reset.deliver_pending()
    response = await client.post(f'{BASE}/auth/password-reset/confirm', json={'token': token, 'password': 'NuevaClave123!'})
    assert response.status_code == 200 and response.json() == {'changed': True}
    assert response.headers['cache-control'] == 'no-store'
    assert (await client.post(f'{BASE}/auth/password-reset/confirm', json={'token': token, 'password': 'OtraClave123!'})).status_code == 422
    assert (await client.get(f'{BASE}/auth/me', headers={'Authorization': 'Bearer ' + session['access_token']})).status_code == 401
    assert (await client.post(f'{BASE}/auth/refresh', json={'refresh_token': session['refresh_token']})).status_code == 401
    login = await client.post(f'{BASE}/auth/login', json={'email': account.email, 'password': 'NuevaClave123!'})
    assert login.json()['error']['code'] == 'OTP_REQUIRED'
    assert await password_reset.deliver_pending()
    assert sent[-1]['completed'] is True and 'url' not in sent[-1]
    async with database.get_session_factory()() as db:
        user = await db.get(models.AdminUser, account.id)
        row = await db.get(models.AdminPasswordReset, row_id)
        assert verify_password('NuevaClave123!', user.password_hash)
        assert user.mfa_enabled and user.recovery_hashes == ['previous-hash']
        assert row.used_at and row.status == 'sent' and row.payload_encrypted is None
        audit = await db.scalar(select(models.AuditLog).where(models.AuditLog.action == 'auth.password_reset', models.AuditLog.entity_id == user.id))
        assert audit is not None and 'NuevaClave123!' not in str(audit.after)


async def test_generic_response_for_unknown_inactive_pending_and_cooldown(client, account):
    first = await client.post(f'{BASE}/auth/password-reset/request', json={'email': account.email})
    again = await client.post(f'{BASE}/auth/password-reset/request', json={'email': account.email})
    unknown = await client.post(f'{BASE}/auth/password-reset/request', json={'email': f'{uuid4()}@wellq.co.uk'})
    async with database.get_session_factory()() as db:
        user = await db.get(models.AdminUser, account.id)
        user.is_active = False
        await db.commit()
    inactive = await client.post(f'{BASE}/auth/password-reset/request', json={'email': account.email})
    async with database.get_session_factory()() as db:
        user = await db.get(models.AdminUser, account.id)
        user.is_active = True
        user.password_hash = None
        await db.commit()
    pending = await client.post(f'{BASE}/auth/password-reset/request', json={'email': account.email})
    assert all(response.status_code == 202 and response.json() == first.json() for response in [again, unknown, inactive, pending])
    async with database.get_session_factory()() as db:
        assert len((await db.scalars(select(models.AdminPasswordReset).where(models.AdminPasswordReset.admin_id == account.id))).all()) == 1


@pytest.mark.parametrize('change', ['expired', 'disabled', 'email', 'version', 'revoked'])
async def test_invalid_reset_does_not_change_password(client, account, change):
    token, row_id = await issue(client, account)
    async with database.get_session_factory()() as db:
        row = await db.get(models.AdminPasswordReset, row_id)
        user = await db.get(models.AdminUser, account.id)
        if change == 'expired': row.expires_at = now_utc() - timedelta(seconds=1)
        if change == 'disabled': user.is_active = False
        if change == 'email': user.email = f'{uuid4()}@wellq.co.uk'
        if change == 'version': user.auth_version += 1
        if change == 'revoked': row.revoked_at = now_utc()
        await db.commit()
    result = await client.post(f'{BASE}/auth/password-reset/confirm', json={'token': token, 'password': 'NuevaClave123!'})
    assert result.status_code == 422
    async with database.get_session_factory()() as db:
        assert verify_password('Anterior123!', (await db.get(models.AdminUser, account.id)).password_hash)


async def test_request_rotation_limit_and_old_token(client, account):
    tokens = []
    for _ in range(3):
        token, row_id = await issue(client, account)
        tokens.append(token)
        async with database.get_session_factory()() as db:
            await db.execute(update(models.AdminPasswordReset).where(models.AdminPasswordReset.id == row_id)
                             .values(created_at=now_utc() - timedelta(minutes=2)))
            await db.commit()
    # Ordenar explícitamente la última fila para comprobar el límite horario.
    response = await client.post(f'{BASE}/auth/password-reset/request', json={'email': account.email})
    assert response.status_code == 202
    async with database.get_session_factory()() as db:
        rows = (await db.scalars(select(models.AdminPasswordReset).where(models.AdminPasswordReset.admin_id == account.id))).all()
        assert len(rows) == 3 and sum(row.revoked_at is None for row in rows) == 1
    for token in tokens[:2]:
        assert (await client.post(f'{BASE}/auth/password-reset/confirm', json={'token': token, 'password': 'NuevaClave123!'})).status_code == 422


async def test_delivery_failure_retries_and_cancel_disabled_account(client, account, monkeypatch):
    _, row_id = await issue(client, account)
    monkeypatch.setattr(password_reset, 'send_reset', lambda value: (_ for _ in ()).throw(RuntimeError('simulado')))
    assert await password_reset.deliver_pending()
    async with database.get_session_factory()() as db:
        row = await db.get(models.AdminPasswordReset, row_id)
        assert row.attempts == 1 and row.status == 'queued'
        row.next_attempt_at = now_utc()
        (await db.get(models.AdminUser, account.id)).is_active = False
        await db.commit()
    assert await password_reset.deliver_pending()
    async with database.get_session_factory()() as db:
        row = await db.get(models.AdminPasswordReset, row_id)
        assert row.status == 'cancelled' and row.payload_encrypted is None
