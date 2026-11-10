"""Migración y uso concurrente en PostgreSQL temporal, sin enviar correos."""
import asyncio
import importlib.util
import json
from datetime import timedelta
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, update
from starlette.requests import Request

from app import database, models
from app.account_security import decrypt
from app.config import get_settings
from app.errors import ApiError
from app.password_reset import request_reset, confirm_reset
from app.security import hash_password, now_utc, verify_password


async def main():
    engine = database.get_engine()
    assert engine.url.database == 'agecare_password_reset_check'
    assert engine.url.host == '127.0.0.1'
    settings = get_settings()
    settings.mail_provider = 'smtp'
    settings.smtp_host = 'localhost'
    settings.mail_from = 'tests@example.org'
    factory = database.get_session_factory()
    try:
        async with engine.begin() as connection:
            tables = [table for table in models.Base.metadata.sorted_tables if table.name != 'admin_password_resets']
            await connection.run_sync(lambda bind: models.Base.metadata.create_all(bind, tables=tables))
        async with factory() as db:
            user = models.AdminUser(full_name='Cuenta temporal', email='test@example.org', role='support',
                                    password_hash=hash_password('Antes123!'), is_active=True)
            db.add(user)
            await db.commit()
            user_id = user.id
        def migrate(connection):
            path = Path(__file__).resolve().parents[1] / 'alembic/versions/0014_password_reset.py'
            spec = importlib.util.spec_from_file_location('reset_migration', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.op = Operations(MigrationContext.configure(connection))
            module.upgrade()
            module.upgrade()
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
        request = Request({'type': 'http', 'method': 'POST', 'headers': [], 'client': ('127.0.0.1', 1)})
        async with factory() as db:
            assert verify_password('Antes123!', (await db.get(models.AdminUser, user_id)).password_hash)
            await request_reset(db, 'test@example.org', request)
            await db.commit()
            row = await db.scalar(select(models.AdminPasswordReset))
            token = json.loads(decrypt(row.payload_encrypted))['url'].split('#token=')[1]
        async def confirm(password):
            async with factory() as db:
                try:
                    await confirm_reset(db, token, password, request)
                    await db.commit()
                    return 200
                except ApiError as error:
                    await db.rollback()
                    return error.status_code
        assert sorted(await asyncio.gather(confirm('Nueva123!'), confirm('Otra123!'))) == [200, 422]
        async with factory() as db:
            user = await db.get(models.AdminUser, user_id)
            assert user.auth_version == 1
            assert verify_password('Nueva123!', user.password_hash) or verify_password('Otra123!', user.password_hash)
            await db.execute(update(models.AdminPasswordReset).values(created_at=now_utc() - timedelta(minutes=2)))
            await db.commit()
        async def issue():
            async with factory() as db:
                await request_reset(db, 'test@example.org', request)
                await db.commit()
        await asyncio.gather(issue(), issue())
        async with factory() as db:
            pending = (await db.scalars(select(models.AdminPasswordReset).where(
                models.AdminPasswordReset.used_at.is_(None), models.AdminPasswordReset.revoked_at.is_(None)))).all()
            assert len(pending) == 1
        print('PostgreSQL temporal OK: migración conserva cuenta, uso único y solicitudes concurrentes serializadas.')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
