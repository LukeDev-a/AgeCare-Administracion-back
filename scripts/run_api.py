"""Arranque tras migraciones/seed: Uvicorn usa un login PostgreSQL sin DDL.

La credencial aleatoria vive en el entorno del proceso, nunca se imprime/guarda.
El propietario solo se usa para preparar permisos. Diseñado para una API Compose.
"""
import asyncio
import hashlib
import os
import re
import secrets
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.database_urls import database_connect_args


async def provision_runtime(database_url: str, *, stable_password: str | None = None) -> str:
    url = make_url(database_url)
    if url.get_backend_name() != 'postgresql':
        raise RuntimeError('El arranque protegido requiere PostgreSQL.')
    role = 'agecare_api_' + hashlib.sha256(url.database.encode()).hexdigest()[:16]
    if stable_password is not None and not re.fullmatch(r'[0-9a-f]{64}', stable_password):
        raise ValueError('La contraseña estable debe tener el formato generado por el preparador.')
    password = stable_password if stable_password is not None else secrets.token_hex(32)
    engine = create_async_engine(url, hide_parameters=True, connect_args=database_connect_args(url))
    try:
        async with engine.begin() as connection:
            await connection.execute(text('SELECT pg_advisory_xact_lock(724017, 1)'))
            existing = (await connection.execute(text('''SELECT rolsuper, rolcreatedb, rolcreaterole,
                rolreplication, rolbypassrls FROM pg_roles WHERE rolname = :role'''), {'role': role})).first()
            if existing and any(existing):
                raise RuntimeError('El rol reservado de API tiene privilegios incompatibles.')
            if await connection.scalar(text('''SELECT count(*) FROM pg_auth_members m
                JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = :role'''), {'role': role}):
                raise RuntimeError('El rol reservado no debe pertenecer a otros roles.')
            if await connection.scalar(text('''SELECT count(*) FROM pg_class c
                JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = :role'''), {'role': role}):
                raise RuntimeError('El rol de API no debe ser propietario de tablas.')
            if await connection.scalar(text('''SELECT count(*) FROM pg_database d
                JOIN pg_roles r ON r.oid = d.datdba WHERE r.rolname = :role'''), {'role': role}):
                raise RuntimeError('El rol de API no debe ser propietario de bases.')
            if await connection.scalar(text('''SELECT count(*) FROM pg_namespace n
                JOIN pg_roles r ON r.oid = n.nspowner WHERE r.rolname = :role'''), {'role': role}):
                raise RuntimeError('El rol de API no debe ser propietario de esquemas.')
            if existing and stable_password is not None:
                # No reemplazar una credencial desconocida o ya desplegada.
                # El archivo privado debe poder autenticar el login existente.
                probe_url = url.set(username=role, password=password)
                probe = create_async_engine(probe_url, hide_parameters=True,
                                            connect_args=database_connect_args(probe_url))
                try:
                    async with probe.connect() as login:
                        await login.execute(text('SELECT 1'))
                finally:
                    await probe.dispose()
            # Solo identificadores hash y contraseña hexadecimal generados internamente.
            verb = 'ALTER' if existing else 'CREATE'
            # Los atributos privilegiados ya se comprueban arriba. Sus valores
            # predeterminados son falsos; no pedir ALTER de atributos reservados
            # a superusuario en proveedores administrados como Neon.
            password_clause = '' if existing and stable_password is not None else f" PASSWORD '{password}'"
            await connection.execute(text(f'''{verb} ROLE "{role}" LOGIN NOINHERIT
                NOCREATEDB NOCREATEROLE{password_clause}'''))
            await connection.execute(text('REVOKE CREATE ON SCHEMA public FROM PUBLIC'))
            await connection.execute(text('REVOKE ALL ON TABLE public.audit_log FROM PUBLIC'))
            quoted_db = connection.dialect.identifier_preparer.quote_identifier(url.database)
            await connection.execute(text(f'GRANT CONNECT ON DATABASE {quoted_db} TO "{role}"'))
            await connection.execute(text(f'REVOKE ALL ON SCHEMA public FROM "{role}"'))
            await connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
            tables = (await connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))).scalars().all()
            for name in tables:
                quoted = connection.dialect.identifier_preparer.quote_identifier(name)
                await connection.execute(text(f'REVOKE ALL ON TABLE public.{quoted} FROM "{role}"'))
                privileges = 'SELECT, INSERT' if name == 'audit_log' else 'SELECT' if name == 'alembic_version' else 'SELECT, INSERT, UPDATE, DELETE'
                await connection.execute(text(f'GRANT {privileges} ON TABLE public.{quoted} TO "{role}"'))
            await connection.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"'))
            protected = await connection.scalar(text("""SELECT count(*) FROM pg_trigger
                WHERE tgrelid = 'public.audit_log'::regclass AND tgname = 'agecare_audit_immutable' AND tgenabled = 'O'"""))
            if protected != 1:
                raise RuntimeError('Falta migración 0011 de protección de auditoría.')
            for privilege in ('UPDATE', 'DELETE', 'TRUNCATE', 'TRIGGER'):
                if await connection.scalar(text("SELECT has_table_privilege(:role, 'public.audit_log', :privilege)"), {'role': role, 'privilege': privilege}):
                    raise RuntimeError('La cuenta de API conserva permisos indebidos en auditoría.')
    finally:
        await engine.dispose()
    return url.set(username=role, password=password).render_as_string(hide_password=False)


def main():
    # No pasar URL ni excepción con parámetros a logs del arranque.
    try:
        runtime_url = asyncio.run(provision_runtime(get_settings().database_url))
    except Exception:
        raise SystemExit('No se pudo preparar la cuenta limitada de API. Revisa migraciones y permisos CREATEROLE del propietario; consulta docs/auditoria-administrativa.md.') from None
    os.environ['ADMIN_DATABASE_URL'] = runtime_url
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'])


if __name__ == '__main__':
    main()
