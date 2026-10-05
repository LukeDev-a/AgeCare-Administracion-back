import base64
import json
from datetime import timedelta
from uuid import UUID, uuid4

import pyotp
import pytest
from sqlalchemy import select, update

from app import database, models
from app.account_security import decrypt, requires_mfa
from app.config import get_settings
from app.invitation_mail import deliver_pending
from app.security import hash_password, now_utc

BASE = '/api/v1/admin'
PASSWORD = 'Invitada123!'
pytestmark = pytest.mark.asyncio


async def invite(client, headers, role='analyst', required=True):
    payload = {'full_name': 'Persona invitada', 'email': f'{uuid4()}@wellq.co.uk', 'role': role, 'require_mfa': required}
    result = await client.post(f'{BASE}/users', headers=headers, json=payload)
    assert result.status_code == 201, result.text
    user = result.json()
    async with database._session_factory() as db:
        invitation = await db.scalar(select(models.AdminInvitation).where(models.AdminInvitation.admin_id == UUID(user['id'])).order_by(models.AdminInvitation.created_at.desc()))
        mail = await db.scalar(select(models.InvitationEmail).where(models.InvitationEmail.invitation_id == invitation.id))
        token = json.loads(decrypt(mail.payload_encrypted))['url'].split('#token=')[1]
        assert token != invitation.token_hash and token not in mail.payload_encrypted
    assert token not in result.text
    return user, token


async def setup(client, token):
    result = await client.post(f'{BASE}/auth/invitations/setup', json={'token': token})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['qr_data_url'].startswith('data:image/svg+xml;base64,')
    assert b'<svg' in base64.b64decode(data['qr_data_url'].split(',')[1])
    assert result.headers['cache-control'] == 'no-store'
    return data['secret']


async def accept(client, token, secret=None, enabled=True):
    return await client.post(f'{BASE}/auth/invitations/accept', json={
        'token': token, 'password': PASSWORD, 'enable_mfa': enabled,
        **({'otp_code': pyotp.TOTP(secret).now()} if secret else {})})


async def test_full_invitation_mfa_login_refresh_and_recovery(client, admin_headers):
    user, token = await invite(client, admin_headers)
    assert (await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': PASSWORD})).status_code == 401
    info = await client.post(f'{BASE}/auth/invitations/inspect', json={'token': token})
    assert info.status_code == 200 and info.json()['mfa_required']
    secret = await setup(client, token)
    response = await accept(client, token, secret)
    assert response.status_code == 200, response.text
    codes = response.json()['recovery_codes']
    assert len(codes) == 10 and len(set(codes)) == 10
    assert (await accept(client, token, secret)).status_code == 422
    async with database._session_factory() as db:
        stored = await db.get(models.AdminUser, UUID(user['id']))
        assert stored.password_hash != PASSWORD and stored.mfa_secret != secret and stored.mfa_secret.startswith('enc:')
        assert all(code.replace('-', '') not in stored.recovery_hashes for code in codes)
    login_data = {'email': user['email'], 'password': PASSWORD}
    assert (await client.post(f'{BASE}/auth/login', json=login_data)).json()['error']['code'] == 'OTP_REQUIRED'
    assert (await client.post(f'{BASE}/auth/login', json={**login_data, 'otp_code': pyotp.TOTP(secret).now()})).status_code == 401
    login = await client.post(f'{BASE}/auth/login', json={**login_data, 'recovery_code': codes[0]})
    assert login.status_code == 200
    data = login.json()
    headers = {'Authorization': f"Bearer {data['access_token']}"}
    assert (await client.get(f'{BASE}/auth/me', headers=headers)).status_code == 200
    assert (await client.post(f'{BASE}/auth/refresh', json={'refresh_token': data['refresh_token']})).status_code == 200
    assert (await client.post(f'{BASE}/auth/login', json={**login_data, 'recovery_code': codes[0]})).status_code == 401
    logs = (await client.get(f'{BASE}/audit-log', headers=admin_headers, params={'entity_id': user['id']})).json()
    assert {r['action'] for r in logs['items']} == {'staff.create', 'staff.invitation_accept'}
    assert secret not in str(logs) and token not in str(logs) and PASSWORD not in str(logs) and codes[0] not in str(logs)


async def test_optional_mfa_and_role_policy_cannot_be_bypassed(client, admin_headers, monkeypatch):
    user, token = await invite(client, admin_headers, required=False)
    response = await accept(client, token, enabled=False)
    assert response.status_code == 200 and response.json()['recovery_codes'] == []
    assert (await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': PASSWORD})).status_code == 200
    monkeypatch.setattr(get_settings(), 'mfa_required_roles', 'admin')
    # Cabeceras emitidas antes de exigir MFA: se crea otro actor verificado para la prueba.
    async with database._session_factory() as db:
        actor = models.AdminUser(full_name='Admin con MFA', email=f'{uuid4()}@wellq.co.uk', role='admin', is_active=True,
                                 password_hash=hash_password(PASSWORD), mfa_enabled=True, mfa_secret=pyotp.random_base32())
        db.add(actor); await db.commit()
        actor_id = actor.id
    from app.security import create_access_token
    verified = {'Authorization': f'Bearer {create_access_token(actor_id, "admin", True)}'}
    admin_user, admin_token = await invite(client, verified, role='admin', required=False)
    rejected = await accept(client, admin_token, enabled=False)
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'OTP_INVALID'
    assert (await client.get(f'{BASE}/auth/me', headers=admin_headers)).status_code == 401


async def test_resend_cancel_expiration_and_pending_email(client, admin_headers):
    user, old = await invite(client, admin_headers)
    assert (await client.patch(f"{BASE}/users/{user['id']}", headers=admin_headers, json={'email': f'{uuid4()}@wellq.co.uk'})).status_code == 409
    assert (await client.post(f"{BASE}/users/{user['id']}/invitation/resend", headers=admin_headers)).status_code == 409
    async with database._session_factory() as db:
        await db.execute(update(models.AdminInvitation).where(models.AdminInvitation.admin_id == UUID(user['id'])).values(created_at=now_utc() - timedelta(minutes=2)))
        await db.commit()
    assert (await client.post(f"{BASE}/users/{user['id']}/invitation/resend", headers=admin_headers)).status_code == 200
    assert (await client.post(f'{BASE}/auth/invitations/inspect', json={'token': old})).status_code == 422
    async with database._session_factory() as db:
        latest = await db.scalar(select(models.AdminInvitation).where(models.AdminInvitation.admin_id == UUID(user['id']), models.AdminInvitation.revoked_at.is_(None)))
        mail = await db.scalar(select(models.InvitationEmail).where(models.InvitationEmail.invitation_id == latest.id))
        new_token = json.loads(decrypt(mail.payload_encrypted))['url'].split('#token=')[1]
    assert (await client.post(f"{BASE}/users/{user['id']}/invitation/cancel", headers=admin_headers)).status_code == 200
    assert (await accept(client, new_token, enabled=False)).status_code == 422
    listing = (await client.get(f'{BASE}/users', headers=admin_headers, params={'q': user['email'], 'account_status': 'cancelled'})).json()
    assert listing['total'] == 1 and listing['items'][0]['account_status'] == 'cancelled'
    another, expired = await invite(client, admin_headers)
    async with database._session_factory() as db:
        await db.execute(update(models.AdminInvitation).where(models.AdminInvitation.admin_id == UUID(another['id'])).values(expires_at=now_utc() - timedelta(hours=1)))
        stored = await db.get(models.AdminUser, UUID(another['id'])); stored.invitation_expires_at = now_utc() - timedelta(hours=1)
        await db.commit()
    assert (await client.post(f'{BASE}/auth/invitations/inspect', json={'token': expired})).status_code == 422
    assert (await client.get(f'{BASE}/users', headers=admin_headers, params={'q': another['email'], 'account_status': 'expired'})).json()['total'] == 1


async def test_otp_attempt_limit_permissions_and_no_mail_configuration(client, admin_headers, analyst_headers, monkeypatch):
    user, token = await invite(client, admin_headers)
    secret = await setup(client, token)
    invalid = '000000' if pyotp.TOTP(secret).now() != '000000' else '111111'
    for _ in range(10):
        response = await client.post(f'{BASE}/auth/invitations/accept', json={'token': token, 'password': PASSWORD, 'otp_code': invalid})
        assert response.status_code == 422
    assert (await accept(client, token, secret)).status_code == 422
    for endpoint in ['resend', 'cancel']:
        assert (await client.post(f"{BASE}/users/{user['id']}/invitation/{endpoint}", headers=analyst_headers)).status_code == 403
        assert (await client.post(f"{BASE}/users/{user['id']}/invitation/{endpoint}")).status_code == 401
    monkeypatch.setattr(get_settings(), 'smtp_host', '')
    email = f'{uuid4()}@wellq.co.uk'
    assert (await client.post(f'{BASE}/users', headers=admin_headers, json={'email': email, 'full_name': 'Sin correo', 'role': 'analyst'})).status_code == 503
    async with database._session_factory() as db:
        assert await db.scalar(select(models.AdminUser).where(models.AdminUser.email == email)) is None


async def test_existing_user_enrollment_invalidates_old_tokens(client, admin_headers):
    user, token = await invite(client, admin_headers, required=False)
    await accept(client, token, enabled=False)
    login = (await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': PASSWORD})).json()
    headers = {'Authorization': f"Bearer {login['access_token']}"}
    result = await client.post(f'{BASE}/auth/mfa/setup', headers=headers, json={'password': PASSWORD})
    enrollment = result.json()['enrollment_token']
    data = (await client.post(f'{BASE}/auth/mfa/enrollment/setup', json={'token': enrollment})).json()
    confirmed = await client.post(f'{BASE}/auth/mfa/enrollment/confirm', json={'token': enrollment, 'otp_code': pyotp.TOTP(data['secret']).now()})
    assert confirmed.status_code == 200
    assert (await client.get(f'{BASE}/auth/me', headers=headers)).status_code == 401
    assert (await client.post(f'{BASE}/auth/refresh', json={'refresh_token': login['refresh_token']})).status_code == 401
    assert (await client.post(f'{BASE}/auth/mfa/enrollment/confirm', json={'token': enrollment, 'otp_code': pyotp.TOTP(data['secret']).now()})).status_code == 422
    codes = confirmed.json()['recovery_codes']
    fresh = (await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': PASSWORD, 'recovery_code': codes[0]})).json()
    headers = {'Authorization': f"Bearer {fresh['access_token']}"}
    rejected = await client.post(f'{BASE}/auth/mfa/recovery-codes', headers=headers, json={'password': PASSWORD, 'otp_code': pyotp.TOTP(data['secret']).now()})
    assert rejected.status_code == 422
    assert rejected.json()['error']['code'] == 'INVALID_SECURITY_PROOF'
    assert (await client.get(f'{BASE}/auth/me', headers=headers)).status_code == 200
    async with database._session_factory() as db:
        account = await db.get(models.AdminUser, UUID(user['id']))
        assert len(account.recovery_hashes) == 9
    replaced = await client.post(f'{BASE}/auth/mfa/recovery-codes', headers=headers, json={'password': PASSWORD, 'recovery_code': codes[1]})
    assert replaced.status_code == 200
    assert len(replaced.json()['recovery_codes']) == 10
    assert (await client.get(f'{BASE}/auth/me', headers=headers)).status_code == 200
    assert (await client.post(f'{BASE}/auth/refresh', json={'refresh_token': fresh['refresh_token']})).status_code == 200
    assert (await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': PASSWORD, 'recovery_code': codes[2]})).status_code == 401
    disabled = await client.post(f'{BASE}/auth/mfa/disable', headers=headers, json={'password': PASSWORD, 'recovery_code': replaced.json()['recovery_codes'][0]})
    assert disabled.status_code == 200
    assert (await client.get(f'{BASE}/auth/me', headers=headers)).status_code == 401
    assert (await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': PASSWORD})).status_code == 200


async def test_required_existing_account_can_enroll_but_cannot_disable(client):
    async with database._session_factory() as db:
        user = models.AdminUser(full_name='Admin pendiente MFA', email=f'{uuid4()}@wellq.co.uk', role='admin', is_active=True,
                                password_hash=hash_password(PASSWORD), mfa_enabled=False, mfa_required=True)
        db.add(user); await db.commit(); email = user.email
    logged = await client.post(f'{BASE}/auth/login', json={'email': email, 'password': PASSWORD})
    assert logged.status_code == 403 and 'access_token' not in logged.json()
    token = logged.json()['error']['enrollment_token']
    secret = (await client.post(f'{BASE}/auth/mfa/enrollment/setup', json={'token': token})).json()['secret']
    response = await client.post(f'{BASE}/auth/mfa/enrollment/confirm', json={'token': token, 'otp_code': pyotp.TOTP(secret).now()})
    codes = response.json()['recovery_codes']
    authenticated = (await client.post(f'{BASE}/auth/login', json={'email': email, 'password': PASSWORD, 'recovery_code': codes[0]})).json()
    headers = {'Authorization': f"Bearer {authenticated['access_token']}"}
    assert (await client.post(f'{BASE}/auth/mfa/disable', headers=headers, json={'password': PASSWORD, 'recovery_code': codes[1]})).status_code == 409


async def test_mail_queue_survives_failure_and_removes_secrets(client, admin_headers, monkeypatch):
    from app import invitation_mail
    async with database._session_factory() as db:
        await db.execute(update(models.InvitationEmail).where(models.InvitationEmail.status == 'queued').values(status='cancelled', payload_encrypted=None)); await db.commit()
    user, token = await invite(client, admin_headers)
    calls = []
    def fail(payload):
        calls.append(payload); raise RuntimeError('SMTP no disponible')
    monkeypatch.setattr(invitation_mail, 'send_smtp', fail)
    assert await deliver_pending()
    async with database._session_factory() as db:
        invitation = await db.scalar(select(models.AdminInvitation).where(models.AdminInvitation.admin_id == UUID(user['id'])))
        mail = await db.scalar(select(models.InvitationEmail).where(models.InvitationEmail.invitation_id == invitation.id))
        assert mail.status == 'queued' and mail.attempts == 1 and mail.payload_encrypted
        mail.next_attempt_at = now_utc() - timedelta(seconds=1); await db.commit()
    monkeypatch.setattr(invitation_mail, 'send_smtp', lambda payload: calls.append(payload))
    assert await deliver_pending()
    assert calls[-1]['url'].endswith('#token=' + token)
    async with database._session_factory() as db:
        mail = await db.scalar(select(models.InvitationEmail).where(models.InvitationEmail.invitation_id == invitation.id))
        assert mail.status == 'sent' and mail.payload_encrypted is None
        assert (await db.get(models.AdminUser, UUID(user['id']))).invitation_delivery_status == 'sent'


async def test_mfa_management_failed_proofs_lock_account(client, admin_headers):
    user, token = await invite(client, admin_headers, required=False)
    await accept(client, token, enabled=False)
    login = (await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': PASSWORD})).json()
    headers = {'Authorization': f"Bearer {login['access_token']}"}
    for _ in range(5):
        assert (await client.post(f'{BASE}/auth/mfa/setup', headers=headers, json={'password': 'Incorrecta123!'})).status_code == 422
    response = await client.post(f'{BASE}/auth/mfa/setup', headers=headers, json={'password': PASSWORD})
    assert response.status_code == 423 and response.json()['error']['code'] == 'ACCOUNT_LOCKED'


async def test_old_invitation_cannot_reactivate_disabled_or_deleted_account(client, admin_headers):
    user, token = await invite(client, admin_headers, required=False)
    assert (await accept(client, token, enabled=False)).status_code == 200
    assert (await client.patch(f"{BASE}/users/{user['id']}", headers=admin_headers, json={'is_active': False})).status_code == 200
    assert (await accept(client, token, enabled=False)).status_code == 422
    assert (await client.post(f"{BASE}/users/{user['id']}/invitation/resend", headers=admin_headers)).status_code == 409
    assert (await client.delete(f"{BASE}/users/{user['id']}", headers=admin_headers)).status_code == 204
    assert (await accept(client, token, enabled=False)).status_code == 422


async def test_mfa_enrollment_attempt_limit_and_expiry(client, admin_headers):
    user, invitation = await invite(client, admin_headers, required=False)
    await accept(client, invitation, enabled=False)
    login = (await client.post(f'{BASE}/auth/login', json={'email': user['email'], 'password': PASSWORD})).json()
    headers = {'Authorization': f"Bearer {login['access_token']}"}
    token = (await client.post(f'{BASE}/auth/mfa/setup', headers=headers, json={'password': PASSWORD})).json()['enrollment_token']
    secret = (await client.post(f'{BASE}/auth/mfa/enrollment/setup', json={'token': token})).json()['secret']
    wrong = '000000' if pyotp.TOTP(secret).now() != '000000' else '111111'
    for _ in range(10):
        assert (await client.post(f'{BASE}/auth/mfa/enrollment/confirm', json={'token': token, 'otp_code': wrong})).status_code == 422
    assert (await client.post(f'{BASE}/auth/mfa/enrollment/confirm', json={'token': token, 'otp_code': pyotp.TOTP(secret).now()})).status_code == 422
    token = (await client.post(f'{BASE}/auth/mfa/setup', headers=headers, json={'password': PASSWORD})).json()['enrollment_token']
    async with database._session_factory() as db:
        await db.execute(update(models.MfaEnrollment).where(models.MfaEnrollment.admin_id == UUID(user['id'])).values(expires_at=now_utc() - timedelta(seconds=1)))
        await db.commit()
    assert (await client.post(f'{BASE}/auth/mfa/enrollment/setup', json={'token': token})).status_code == 422
