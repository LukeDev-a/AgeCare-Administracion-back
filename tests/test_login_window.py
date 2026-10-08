from datetime import timedelta
from uuid import uuid4

import pyotp
import pytest
from sqlalchemy import select

from app import database, models, login_attempts
from app.account_security import decrypt, encrypt, new_recovery_codes
from app.security import hash_password, now_utc

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/admin'
PASSWORD = 'Prueba123!'


async def account(mfa=False):
    async with database.get_session_factory()() as db:
        user = models.AdminUser(email=f'{uuid4()}@wellq.co.uk', full_name='Prueba bloqueo',
            role='analyst', password_hash=hash_password(PASSWORD), is_active=True,
            mfa_enabled=mfa, mfa_secret=encrypt(pyotp.random_base32()) if mfa else None)
        db.add(user)
        codes = new_recovery_codes(user) if mfa else []
        await db.commit()
        return user.email, codes


async def stored(email):
    async with database.get_session_factory()() as db:
        return await db.scalar(select(models.AdminUser).where(models.AdminUser.email == email))


async def test_window_is_rolling_and_block_expires(client, monkeypatch):
    email, _ = await account()
    clock = [now_utc()]
    monkeypatch.setattr(login_attempts, 'now_utc', lambda: clock[0])
    wrong = {'email': email, 'password': 'Incorrecta123!'}
    for _ in range(4):
        assert (await client.post(f'{BASE}/auth/login', json=wrong)).status_code == 401
    clock[0] += timedelta(minutes=10, seconds=1)
    assert (await client.post(f'{BASE}/auth/login', json=wrong)).status_code == 401
    assert (await stored(email)).failed_attempts == 1
    for _ in range(4):
        await client.post(f'{BASE}/auth/login', json=wrong)
    user = await stored(email)
    assert user.locked_until and user.failed_attempts == 0
    good = {'email': email, 'password': PASSWORD}
    assert (await client.post(f'{BASE}/auth/login', json=good)).status_code == 423
    clock[0] += timedelta(minutes=15)
    assert (await client.post(f'{BASE}/auth/login', json=good)).status_code == 200
    assert (await stored(email)).failed_attempt_times == []


async def test_mixed_failures_count_but_missing_factor_does_not(client):
    email, codes = await account(mfa=True)
    good = {'email': email, 'password': PASSWORD}
    missing = await client.post(f'{BASE}/auth/login', json=good)
    assert missing.json()['error']['code'] == 'OTP_REQUIRED'
    assert (await stored(email)).failed_attempts == 0
    assert (await client.post(f'{BASE}/auth/login', json={**good, 'password': 'Incorrecta123!'})).status_code == 401
    secret = (await stored(email)).mfa_secret
    wrong_otp = next(f'{n:06d}' for n in range(10)
                     if not pyotp.TOTP(decrypt(secret)).verify(f'{n:06d}', valid_window=1))
    for proof in [{'otp_code': wrong_otp}, {'recovery_code': 'FFFFFFFF-FFFFFFFF'},
                  {'otp_code': wrong_otp}, {'recovery_code': 'FFFFFFFF-FFFFFFFF'}]:
        assert (await client.post(f'{BASE}/auth/login', json={**good, **proof})).status_code == 401
    assert (await client.post(f'{BASE}/auth/login', json={**good, 'recovery_code': codes[0]})).status_code == 423


async def test_success_resets_previous_failures(client):
    email, codes = await account(mfa=True)
    good = {'email': email, 'password': PASSWORD}
    await client.post(f'{BASE}/auth/login', json={**good, 'password': 'Incorrecta123!'})
    assert (await client.post(f'{BASE}/auth/login', json={**good, 'recovery_code': codes[0]})).status_code == 200
    user = await stored(email)
    assert user.failed_attempts == 0 and user.failed_attempt_times == []
