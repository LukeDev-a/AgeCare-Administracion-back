from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.account_security import requires_mfa
from app.database import Base
from app.models import AdminUser
from app.security import hash_password, verify_password
from scripts.bootstrap_dev_accounts import DEV_ACCOUNTS, bootstrap


@pytest_asyncio.fixture
async def isolated_session():
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_bootstrap_creates_accounts_with_password_hashes_and_mfa_enrollment(isolated_session):
    session = isolated_session
    settings = SimpleNamespace(bootstrap_dev_accounts=True, environment='dev')
    async with session.begin():
        await bootstrap(session, settings)
    users = (await session.scalars(select(AdminUser))).all()
    assert len(users) == 4
    for _, email, password, role in DEV_ACCOUNTS:
        user = next(user for user in users if user.email == email)
        assert user.role == role and user.is_active
        assert user.password_hash != password and verify_password(password, user.password_hash)
        assert not user.mfa_enabled and user.mfa_secret is None
        assert not user.recovery_hashes
        if role == 'admin':
            assert requires_mfa(user)  # Configurar MFA, sin acceso pleno previo.
    hashes = {user.email: user.password_hash for user in users}
    await bootstrap(session, settings)
    assert {user.email: user.password_hash for user in (await session.scalars(select(AdminUser))).all()} == hashes


@pytest.mark.asyncio
async def test_bootstrap_preserves_existing_user_and_does_not_fill_missing_accounts(isolated_session):
    session = isolated_session
    user = AdminUser(full_name='Cuenta real', email='admin@wellq.co.uk', role='support',
        password_hash=hash_password('Otra contraseña'), is_active=False, mfa_enabled=True,
        mfa_secret='conservar', mfa_required=True)
    session.add(user)
    await session.flush()
    await bootstrap(session, SimpleNamespace(bootstrap_dev_accounts=True, environment='dev'))
    users = (await session.scalars(select(AdminUser))).all()
    assert len(users) == 1
    assert user.role == 'support' and not user.is_active
    assert user.mfa_enabled and user.mfa_secret == 'conservar'
    assert verify_password('Otra contraseña', user.password_hash)


@pytest.mark.asyncio
async def test_bootstrap_disabled_or_non_dev_never_creates_accounts(isolated_session):
    session = isolated_session
    await bootstrap(session, SimpleNamespace(bootstrap_dev_accounts=False, environment='dev'))
    for environment in ('prod', 'production', 'staging'):
        with pytest.raises(RuntimeError, match='solo pueden crearse'):
            await bootstrap(session, SimpleNamespace(bootstrap_dev_accounts=True, environment=environment))
    assert (await session.scalars(select(AdminUser))).all() == []
