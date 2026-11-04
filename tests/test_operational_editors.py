from dotenv import dotenv_values
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import AdminUser, AuditLog
from app.database import Base
from app.security import verify_password
from scripts.create_editor_accounts import create_accounts, validate_accounts


@pytest.mark.asyncio
@pytest.mark.parametrize('role,require_mfa', [('editor', True), ('admin', True), ('admin', False)])
async def test_editor_creation_is_hashed_audited_and_requires_personal_mfa(tmp_path, role, require_mfa):
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        accounts = validate_accounts([('First', 'first@example.com'), ('Second', 'second@example.com')], {'example.com'}, role=role, require_mfa=require_mfa)
        result = await create_accounts(factory, accounts, tmp_path)
        async with factory() as session:
            users = (await session.scalars(select(AdminUser))).all()
            events = (await session.scalars(select(AuditLog))).all()
            assert len(users) == len(events) == 2
            passwords = []
            for email, path in result:
                initial = dotenv_values(path)['INITIAL_PASSWORD']
                user = next(u for u in users if u.email == email)
                assert user.role == role and user.mfa_required == require_mfa and user.is_active
                assert all(event.after['role'] == role for event in events)
                assert not user.mfa_enabled and user.mfa_secret is None
                assert verify_password(initial, user.password_hash)
                assert all(initial not in str(event.after) for event in events)
                passwords.append(initial)
            assert passwords[0] != passwords[1]
            assert all(event.actor_id is None and event.action == 'staff.create' for event in events)
        with pytest.raises(ValueError):
            await create_accounts(factory, accounts, tmp_path)
        assert len(list(tmp_path.iterdir())) == 2
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(AdminUser)) == 2
            assert await session.scalar(select(func.count()).select_from(AuditLog)) == 2
    finally:
        await engine.dispose()


def test_disallowed_domains_and_duplicate_emails_are_rejected():
    with pytest.raises(ValueError):
        validate_accounts([('First', 'first@example.com')], {'different.com'})
    with pytest.raises(ValueError):
        validate_accounts([('First', 'FIRST@example.com'), ('Other', 'first@example.com')], {'example.com'})
