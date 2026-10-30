"""Fase18 SOLO en PostgreSQL temporal vacío agecare_directory_check_<12hex>."""
import asyncio
import hashlib
import importlib.util
import re
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app import database, models
from app.end_users_demo import demo_id, seed_demo_directory
from app.errors import ApiError
from app.routers.end_users import deactivate_user
from app.schemas.end_users import DeactivateIn
from app.security import now_utc
from scripts.run_api import provision_runtime


async def main():
    owner = database.get_engine()
    url = owner.url
    assert url.host == 'db' and url.username == 'agecare'
    assert re.fullmatch(r'agecare_directory_check_[0-9a-f]{12}', url.database)
    role = 'agecare_api_' + hashlib.sha256(url.database.encode()).hexdigest()[:16]
    runtime = None
    try:
        async with owner.begin() as connection:
            assert not await connection.scalar(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"))
            await connection.run_sync(database.Base.metadata.create_all)
            for name in ('demo_app_memberships', 'demo_app_accounts', 'demo_app_patients'):
                await connection.execute(text('DROP TABLE ' + name))
            def migrate(sync):
                for filename in ('0011_audit_integrity.py', '0012_demo_end_users.py'):
                    spec = importlib.util.spec_from_file_location('check_' + filename[:4], Path('alembic/versions') / filename)
                    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                    module.op = Operations(MigrationContext.configure(sync))
                    module.upgrade(); module.upgrade()
            await connection.run_sync(migrate)
        factory = async_sessionmaker(owner, expire_on_commit=False)
        async with factory() as db:
            admin = models.AdminUser(full_name='Personal conservado', email='staff@example.cl', role='admin', is_active=True)
            db.add(admin); await db.flush()
            session = models.AdminSession(admin_id=admin.id, refresh_hash='sesion-interna-de-prueba', expires_at=now_utc())
            old = models.AuditLog(action='staff.create', actor_name='Historia conservada')
            db.add_all([session, old]); await db.commit()
            admin_id, session_id, audit_id = admin.id, session.id, old.id
        async def seed_once():
            async with factory() as db:
                result = await seed_demo_directory(db); await db.commit()
                return result
        seeded = await asyncio.gather(seed_once(), seed_once())
        assert sorted(seeded) == [False, True], seeded
        async with factory() as db:
            for model, count in ((models.DemoEndUser, 32), (models.DemoPatient, 7), (models.DemoPatientMember, 14)):
                assert await db.scalar(select(func.count()).select_from(model)) == count
        runtime_url = await provision_runtime(url.render_as_string(hide_password=False))
        runtime = create_async_engine(runtime_url, hide_parameters=True)
        runtime_factory = async_sessionmaker(runtime, expire_on_commit=False)
        identity = demo_id('user-1')
        async def deactivate_once():
            async with runtime_factory() as db:
                admin = await db.get(models.AdminUser, admin_id)
                request = Request({'type': 'http', 'method': 'POST', 'headers': []})
                try:
                    result = await deactivate_user(identity, DeactivateIn(confirmation_user_id=identity, reason='Solicitud de demostración'), request, db, admin)
                    assert result.mobile_sessions_revoked is False and result.deactivation_effect == 'demo_only'
                    return 200
                except ApiError as exc:
                    await db.rollback()
                    assert exc.code == 'ACCOUNT_ALREADY_INACTIVE'
                    return exc.status_code
        assert sorted(await asyncio.gather(deactivate_once(), deactivate_once())) == [200, 409]
        assert await seed_once() is False
        async with factory() as db:
            assert (await db.get(models.AdminUser, admin_id)).full_name == 'Personal conservado'
            assert (await db.get(models.AdminSession, session_id)).revoked_at is None
            assert (await db.get(models.AuditLog, audit_id)).actor_name == 'Historia conservada'
            assert not (await db.get(models.DemoEndUser, identity)).is_active
            assert await db.scalar(select(func.count()).select_from(models.DemoPatientMember)) == 14
            assert await db.scalar(select(func.count()).select_from(models.AuditLog).where(models.AuditLog.action == 'end_users.demo_deactivate')) == 1
        print('PostgreSQL OK: migración idempotente, carga concurrente sin duplicados, desactivación demo concurrente 200/409 con un evento, datos/vínculos/sesiones internas conservados y rol limitado compatible.')
    finally:
        if runtime:
            await runtime.dispose()
        async with owner.begin() as connection:
            if await connection.scalar(text('SELECT 1 FROM pg_roles WHERE rolname=:role'), {'role': role}):
                await connection.execute(text(f'DROP OWNED BY "{role}"'))
                await connection.execute(text(f'DROP ROLE "{role}"'))
        await owner.dispose()


if __name__ == '__main__':
    asyncio.run(main())
