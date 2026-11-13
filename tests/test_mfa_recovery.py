import importlib.util
import json
from datetime import timedelta
from uuid import uuid4

import pyotp
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app import database, mfa_recovery, models
from app.account_security import decrypt, encrypt
from app.security import create_access_token, hash_password, hash_refresh, now_utc, verify_password

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/admin'


@pytest_asyncio.fixture
async def owner(client):
    async with database.get_session_factory()() as db:
        assert db.bind.url.drivername == 'sqlite+aiosqlite'
        await db.execute(delete(models.MfaRecoveryEmail))
        await db.execute(delete(models.AdminMfaRecovery))
        user = models.AdminUser(full_name='MFA perdido', email=f'{uuid4()}@wellq.co.uk', role='editor',
            password_hash=hash_password('Anterior123!'), is_active=True, mfa_enabled=True,
            mfa_secret=encrypt(pyotp.random_base32()), recovery_hashes=[hash_refresh('OLD-CODE')])
        db.add(user); await db.commit()
        return user


async def issue(client, owner):
    result = await client.post(f'{BASE}/auth/mfa-recovery/request', json={
        'email': owner.email, 'password': 'Anterior123!', 'reason': 'Perdí mi autenticador y todos los códigos'})
    assert result.status_code == 202, result.text
    async with database.get_session_factory()() as db:
        row = await db.scalar(select(models.AdminMfaRecovery).where(models.AdminMfaRecovery.admin_id == owner.id)
                              .order_by(models.AdminMfaRecovery.created_at.desc()))
        mail = await db.scalar(select(models.MfaRecoveryEmail).where(models.MfaRecoveryEmail.recovery_id == row.id,
                                                                    models.MfaRecoveryEmail.kind == 'verify'))
        token = json.loads(decrypt(mail.payload_encrypted))['url'].split('#token=')[1]
        assert row.token_hash == hash_refresh(token) and token not in mail.payload_encrypted
        return token, row.id


async def confirm(client, token):
    return await client.post(f'{BASE}/auth/mfa-recovery/confirm', json={'token': token})


def decision(note='Identidad verificada por llamada al número conocido', **extra):
    return {'decision': 'approve', 'identity_verified': True, 'note': note, 'password': 'Admin123!', **extra}


async def test_full_recovery_revokes_everything_and_requires_new_verified_mfa(client, owner, admin_headers, monkeypatch):
    old_access = create_access_token(owner.id, owner.role, True, owner.auth_version)
    refresh = 'old-refresh-' + uuid4().hex
    async with database.get_session_factory()() as db:
        db.add(models.AdminSession(admin_id=owner.id, refresh_hash=hash_refresh(refresh), auth_version=owner.auth_version,
            mfa_verified=True, expires_at=now_utc() + timedelta(hours=1)))
        db.add(models.MfaEnrollment(admin_id=owner.id, token_hash=hash_refresh('stale-enrollment'),
            secret_encrypted=encrypt(pyotp.random_base32()), expires_at=now_utc()+timedelta(minutes=10)))
        await db.commit()
    token, row_id = await issue(client, owner)
    sent = []
    monkeypatch.setattr(mfa_recovery, 'send_mail', lambda payload, kind, row: sent.append((payload, kind)))
    assert await mfa_recovery.deliver_pending()
    assert sent[0][1] == 'verify'
    assert (await client.get(f'{BASE}/mfa-recovery/requests', headers=admin_headers)).json()['total'] == 0
    assert (await confirm(client, token)).status_code == 200
    assert (await confirm(client, token)).status_code == 422
    listing = (await client.get(f'{BASE}/mfa-recovery/requests', headers=admin_headers)).json()
    assert listing['items'][0]['can_decide'] and listing['items'][0]['status'] == 'pending'
    assert token not in json.dumps(listing) and 'token_hash' not in json.dumps(listing)
    url = f'{BASE}/mfa-recovery/requests/{row_id}/decision'
    result = await client.post(url, headers=admin_headers, json=decision())
    assert result.status_code == 200, result.text
    assert (await client.post(url, headers=admin_headers, json=decision())).status_code == 409
    assert (await client.get(f'{BASE}/auth/me', headers={'Authorization': 'Bearer ' + old_access})).status_code == 401
    assert (await client.post(f'{BASE}/auth/refresh', json={'refresh_token': refresh})).status_code == 401
    async with database.get_session_factory()() as db:
        user = await db.get(models.AdminUser, owner.id)
        assert not user.mfa_enabled and user.mfa_required and user.mfa_secret is None
        assert user.recovery_hashes == [] and user.mfa_last_step is None
        assert user.auth_version == owner.auth_version + 1 and verify_password('Anterior123!', user.password_hash)
        enrollment = await db.scalar(select(models.MfaEnrollment).where(models.MfaEnrollment.admin_id == owner.id))
        assert enrollment.used_at and enrollment.secret_encrypted == ''
        log = await db.scalar(select(models.AuditLog).where(models.AuditLog.entity_id == owner.id,
                              models.AuditLog.action == 'staff.mfa_recovery_approve'))
        assert log.actor_id and log.created_at and log.event_metadata['reason'] == decision()['note']
    login = await client.post(f'{BASE}/auth/login', json={'email': owner.email, 'password': 'Anterior123!'})
    assert login.status_code == 403 and login.json()['error']['code'] == 'MFA_ENROLLMENT_REQUIRED'
    assert 'access_token' not in login.json()
    enrollment_token = login.json()['error']['enrollment_token']
    setup = await client.post(f'{BASE}/auth/mfa/enrollment/setup', json={'token': enrollment_token})
    otp = pyotp.TOTP(setup.json()['secret']).now()
    enabled = await client.post(f'{BASE}/auth/mfa/enrollment/confirm', json={'token': enrollment_token, 'otp_code': otp})
    assert enabled.status_code == 200 and len(enabled.json()['recovery_codes']) == 10
    login = await client.post(f'{BASE}/auth/login', json={'email': owner.email, 'password': 'Anterior123!',
        'recovery_code': enabled.json()['recovery_codes'][0]})
    assert login.status_code == 200 and login.json()['access_token']


async def test_bad_password_generic_response_limits_and_lockout(client, owner):
    body = {'email': owner.email, 'password': 'Incorrecta123!', 'reason': 'No tengo mis códigos'}
    unknown = await client.post(f'{BASE}/auth/mfa-recovery/request', json={**body, 'email': f'{uuid4()}@wellq.co.uk'})
    for _ in range(5):
        result = await client.post(f'{BASE}/auth/mfa-recovery/request', json=body)
        assert result.status_code == 202 and result.json() == unknown.json()
    async with database.get_session_factory()() as db:
        user = await db.get(models.AdminUser, owner.id)
        assert user.locked_until and user.mfa_enabled
        assert not (await db.scalars(select(models.AdminMfaRecovery).where(models.AdminMfaRecovery.admin_id == owner.id))).all()


async def test_cooldown_rotation_and_three_requests_per_hour(client, owner):
    tokens = []
    for _ in range(3):
        token, row_id = await issue(client, owner)
        tokens.append(token)
        # Una solicitud inmediata conserva el enlace anterior.
        await client.post(f'{BASE}/auth/mfa-recovery/request', json={
            'email': owner.email, 'password': 'Anterior123!', 'reason': 'Sigo sin acceso'})
        async with database.get_session_factory()() as db:
            row = await db.get(models.AdminMfaRecovery, row_id)
            assert row.status == 'awaiting_email'
            row.created_at = now_utc() - timedelta(minutes=2)
            await db.commit()
    await client.post(f'{BASE}/auth/mfa-recovery/request', json={'email': owner.email,
        'password': 'Anterior123!', 'reason': 'Sigo sin acceso'})
    async with database.get_session_factory()() as db:
        rows = (await db.scalars(select(models.AdminMfaRecovery).where(models.AdminMfaRecovery.admin_id == owner.id))).all()
        assert len(rows) == 3
    for token in tokens[:-1]:
        assert (await confirm(client, token)).status_code == 422
    assert (await confirm(client, tokens[-1])).status_code == 200


@pytest.mark.parametrize('change', ['expired', 'inactive', 'email', 'version'])
async def test_stale_confirmation_rejected(client, owner, change):
    token, row_id = await issue(client, owner)
    async with database.get_session_factory()() as db:
        user = await db.get(models.AdminUser, owner.id)
        row = await db.get(models.AdminMfaRecovery, row_id)
        if change == 'expired': row.expires_at = now_utc() - timedelta(seconds=1)
        if change == 'inactive': user.is_active = False
        if change == 'email': user.email = f'{uuid4()}@wellq.co.uk'
        if change == 'version': user.auth_version += 1
        await db.commit()
    assert (await confirm(client, token)).status_code == 422


async def test_identity_proof_rejection_and_permissions(client, owner, admin_headers, analyst_headers):
    token, row_id = await issue(client, owner)
    assert (await confirm(client, token)).status_code == 200
    url = f'{BASE}/mfa-recovery/requests/{row_id}/decision'
    assert (await client.get(f'{BASE}/mfa-recovery/requests')).status_code == 401
    assert (await client.get(f'{BASE}/mfa-recovery/requests', headers=analyst_headers)).status_code == 403
    assert (await client.post(url, headers=analyst_headers, json=decision())).status_code == 403
    assert (await client.post(url, headers=admin_headers, json=decision(identity_verified=False))).status_code == 422
    assert (await client.post(url, headers=admin_headers, json=decision(password='Incorrecta123!'))).status_code == 422
    result = await client.post(url, headers=admin_headers, json=decision(decision='reject', identity_verified=False))
    assert result.status_code == 200 and result.json()['status'] == 'rejected'
    async with database.get_session_factory()() as db:
        user = await db.get(models.AdminUser, owner.id)
        assert user.mfa_enabled and user.mfa_secret == owner.mfa_secret and user.recovery_hashes == owner.recovery_hashes
        assert user.auth_version == owner.auth_version


async def test_self_approval_blocked_and_admin_mfa_required(client, owner):
    async with database.get_session_factory()() as db:
        user = await db.get(models.AdminUser, owner.id); user.role = 'admin'; await db.commit()
    token, row_id = await issue(client, owner)
    await confirm(client, token)
    headers = {'Authorization': 'Bearer ' + create_access_token(owner.id, 'admin', True)}
    result = await client.post(f'{BASE}/mfa-recovery/requests/{row_id}/decision', headers=headers,
        json=decision(password='Anterior123!'))
    assert result.status_code == 409 and result.json()['error']['code'] == 'CANNOT_RECOVER_SELF'


async def test_admin_notice_revalidates_role_and_worker_retries(client, owner, monkeypatch):
    token, row_id = await issue(client, owner)
    await confirm(client, token)
    async with database.get_session_factory()() as db:
        mails = (await db.scalars(select(models.MfaRecoveryEmail).where(models.MfaRecoveryEmail.recovery_id == row_id))).all()
        for mail in mails:
            if mail.kind == 'verify': mail.status = 'cancelled'; mail.payload_encrypted = None
            else:
                recipient = await db.get(models.AdminUser, mail.recipient_id)
                assert recipient.role == 'admin' and recipient.id != owner.id
                # Cambiar el destino del aviso a una cuenta de prueba que perdió permisos.
                replacement = models.AdminUser(full_name='Antes admin', email=f'{uuid4()}@wellq.co.uk',
                    role='editor', is_active=True, password_hash=hash_password('Prueba123!'))
                db.add(replacement); await db.flush()
                mail.recipient_id = replacement.id
                mail.payload_encrypted = encrypt(json.dumps({'email': replacement.email}))
        await db.commit()
    monkeypatch.setattr(mfa_recovery, 'send_mail', lambda *args: pytest.fail('No enviar a un rol sin permiso'))
    while await mfa_recovery.deliver_pending():
        pass
    async with database.get_session_factory()() as db:
        assert not (await db.scalars(select(models.MfaRecoveryEmail).where(models.MfaRecoveryEmail.status == 'queued'))).all()


async def test_pending_expiration_and_actor_second_factor(client, owner):
    token, row_id = await issue(client, owner)
    await confirm(client, token)
    secret = pyotp.random_base32()
    async with database.get_session_factory()() as db:
        actor = models.AdminUser(full_name='Revisor MFA', email=f'{uuid4()}@wellq.co.uk', role='admin',
            password_hash=hash_password('Revisor123!'), is_active=True, mfa_enabled=True, mfa_secret=encrypt(secret))
        db.add(actor); await db.commit()
    headers = {'Authorization': 'Bearer ' + create_access_token(actor.id, 'admin', True)}
    url = f'{BASE}/mfa-recovery/requests/{row_id}/decision'
    assert (await client.post(url, headers=headers, json=decision(password='Revisor123!'))).status_code == 422
    async with database.get_session_factory()() as db:
        row = await db.get(models.AdminMfaRecovery, row_id)
        assert row.status == 'pending'
        row.expires_at = now_utc() - timedelta(seconds=1)
        await db.commit()
    assert (await client.post(url, headers=headers, json=decision(password='Revisor123!', otp_code=pyotp.TOTP(secret).now()))).status_code == 409
    listing = (await client.get(f'{BASE}/mfa-recovery/requests', headers=headers)).json()
    assert listing['items'][0]['status'] == 'expired' and not listing['items'][0]['can_decide']


async def test_mail_failure_retry_and_recipient_disable(client, owner, monkeypatch):
    _, row_id = await issue(client, owner)
    monkeypatch.setattr(mfa_recovery, 'send_mail', lambda *args: (_ for _ in ()).throw(RuntimeError('simulado')))
    assert await mfa_recovery.deliver_pending()
    async with database.get_session_factory()() as db:
        mail = await db.scalar(select(models.MfaRecoveryEmail).where(models.MfaRecoveryEmail.recovery_id == row_id))
        assert mail.attempts == 1 and mail.status == 'queued' and mail.payload_encrypted
        mail.next_attempt_at = now_utc()
        (await db.get(models.AdminUser, owner.id)).is_active = False
        await db.commit()
    assert await mfa_recovery.deliver_pending()
    async with database.get_session_factory()() as db:
        mail = await db.scalar(select(models.MfaRecoveryEmail).where(models.MfaRecoveryEmail.recovery_id == row_id))
        assert mail.status == 'cancelled' and mail.payload_encrypted is None


async def test_migration_preserves_existing_data_and_is_idempotent():
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    spec = importlib.util.spec_from_file_location('migration_mfa', 'alembic/versions/0015_mfa_recovery.py')
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE admin_users (id CHAR(32) PRIMARY KEY, name TEXT)'))
        conn.execute(sa.text("INSERT INTO admin_users VALUES ('existing', 'Conservar')"))
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade(); migration.upgrade()
        assert conn.scalar(sa.text('SELECT name FROM admin_users')) == 'Conservar'
        assert sa.inspect(conn).has_table('admin_mfa_recoveries') and sa.inspect(conn).has_table('mfa_recovery_emails')
    engine.dispose()
