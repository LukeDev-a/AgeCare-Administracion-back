"""Solo DB temporal vacía agecare_audit_check_*; no usa datos habituales."""
import asyncio
import hashlib
import importlib.util
from datetime import timedelta
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from starlette.requests import Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app import database, models
from app.routers.auth import login
from app.schemas.auth import LoginIn
from app.errors import ApiError
from app.security import hash_password, now_utc
from scripts.run_api import provision_runtime


async def main():
    owner = database.get_engine()
    url = owner.url
    assert url.host == 'db' and url.username == 'agecare'
    assert url.database.startswith('agecare_audit_check_') and url.database != 'agecare_admin'
    role = 'agecare_api_' + hashlib.sha256(url.database.encode()).hexdigest()[:16]
    runtime = None
    try:
        async with owner.begin() as connection:
            assert not await connection.scalar(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"))
            await connection.run_sync(database.Base.metadata.create_all)
        factory = async_sessionmaker(owner, expire_on_commit=False)
        async with factory() as db:
            legacy = models.AuditLog(action='games.create', actor_name='Actor eliminado', actor_role='editor',
                                     created_at=now_utc()-timedelta(days=800), after={'title': 'Historia conservada'})
            admin = models.AdminUser(full_name='Admin temporal', email='audit@example.cl', role='admin', is_active=True,
                                     password_hash=hash_password('Prueba123!'))
            db.add_all([legacy, admin]); await db.commit()
            identity = legacy.id
        async with owner.begin() as connection:
            await connection.execute(text('ALTER TABLE audit_log DROP COLUMN event_metadata'))
            def migrate(sync):
                path = Path('alembic/versions/0011_audit_integrity.py')
                spec = importlib.util.spec_from_file_location('audit_migration', path)
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                module.op = Operations(MigrationContext.configure(sync))
                module.upgrade(); module.upgrade()
            await connection.run_sync(migrate)
            assert await connection.scalar(text('SELECT count(*) FROM audit_log')) == 1
        runtime_url = await provision_runtime(url.render_as_string(hide_password=False))
        runtime = create_async_engine(runtime_url, hide_parameters=True)
        database._session_factory = async_sessionmaker(runtime, expire_on_commit=False)
        for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'TRIGGER'):
            async with runtime.connect() as connection:
                permitted = await connection.scalar(text("SELECT has_table_privilege(current_user, 'public.audit_log', :p)"), {'p': privilege})
                assert permitted == (privilege in ('SELECT', 'INSERT')), privilege
        for statement in ("UPDATE audit_log SET actor_name='Alterado'", 'DELETE FROM audit_log',
                          'TRUNCATE audit_log', 'ALTER TABLE audit_log DISABLE TRIGGER ALL',
                          'DROP TABLE audit_log', 'SET ROLE agecare'):
            try:
                async with runtime.begin() as connection:
                    await connection.execute(text(statement))
            except Exception as exc:
                assert getattr(exc.orig, 'sqlstate', None) == '42501', type(exc).__name__
            else:
                raise AssertionError('Operación indebida permitida: ' + statement)
        # El trigger también defiende modificaciones accidentales del propietario.
        for statement in ('UPDATE audit_log SET actor_name=actor_name', 'DELETE FROM audit_log', 'TRUNCATE audit_log'):
            try:
                async with owner.begin() as connection:
                    await connection.execute(text(statement))
            except Exception as exc:
                assert getattr(exc.orig, 'sqlstate', None) == '42501'
            else:
                raise AssertionError('Defensa append-only no activa')
        request = Request({'type': 'http', 'method': 'POST', 'headers': []})
        async with database._session_factory() as db:
            response = await login(LoginIn(email='audit@example.cl', password='Prueba123!'), request, db)
            assert response.access_token
            await db.commit()
        async with database._session_factory() as db:
            request = Request({'type': 'http', 'method': 'POST', 'headers': []})
            try:
                await login(LoginIn(email='unknown@example.cl', password='Incorrecta123!'), request, db)
            except ApiError as exc:
                assert exc.status_code == 401
            else:
                raise AssertionError('Se aceptó un login incorrecto')
        async with database._session_factory() as db:
            assert len((await db.scalars(select(models.AuditLog).where(models.AuditLog.action.like('auth.%')))).all()) == 2
        async with database._session_factory() as db:
            legacy = await db.get(models.AuditLog, identity)
            assert legacy.actor_name == 'Actor eliminado' and legacy.after['title'] == 'Historia conservada'
        # También funciona tras una nueva preparación con rotación del login interno.
        await provision_runtime(url.render_as_string(hide_password=False))
        print('PostgreSQL OK: migración idempotente conserva legado; API SELECT/INSERT sin UPDATE/DELETE/TRUNCATE/DDL; login y auditoría transaccional funcionan; rol temporal eliminado al finalizar.')
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
