"""Arranque cloud: credencial estable limitada, esquema al día y sin seed/DDL."""
import asyncio
import os
import sys
from urllib.parse import urlsplit

from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.database_urls import database_connect_args, normalize_database_url


def validate_settings(settings):
    url = make_url(normalize_database_url(settings.database_url))
    if (url.drivername != 'postgresql+asyncpg' or not (url.host or '').endswith('.neon.tech')
            or url.query.get('ssl') != 'verify-full' or not url.password):
        raise ValueError('Render requiere la conexión Neon limitada con TLS verificado.')
    if len(settings.jwt_secret) < 32 or settings.jwt_secret in ('solo-para-desarrollo', 'cambia-esto-en-produccion'):
        raise ValueError('Falta una clave JWT propia y aleatoria para Render.')
    Fernet(settings.encryption_key.encode())  # Validar, nunca generar ni sustituir MFA.
    if settings.bootstrap_dev_accounts or settings.seed_demo_enabled:
        raise ValueError('El arranque Render no debe habilitar bootstrap ni seed.')
    if getattr(settings, 'render_allow_dev_credentials', False) and settings.environment != 'dev':
        raise ValueError('El arranque con credenciales de demostración solo se admite en entorno dev.')
    public = urlsplit(settings.game_public_base_url)
    if public.scheme != 'https' or not public.hostname or public.username or public.password or public.query or public.fragment or public.path not in ('', '/'):
        raise ValueError('Falta la raíz pública HTTPS de los juegos.')
    origins = [origin.strip() for origin in settings.allows_origins.split(',') if origin.strip()]
    if not origins or any('*' in origin or origin == 'null' or urlsplit(origin).scheme not in ('http', 'https')
                          or not urlsplit(origin).hostname or urlsplit(origin).username or urlsplit(origin).password
                          or urlsplit(origin).path or urlsplit(origin).query or urlsplit(origin).fragment
                          for origin in origins):
        raise ValueError('CORS debe indicar los orígenes concretos de las consolas.')


async def check_database(database_url, *, check_accounts=True):
    url = normalize_database_url(database_url)
    engine = create_async_engine(url, hide_parameters=True, connect_args=database_connect_args(url))
    try:
        async with engine.connect() as connection:
            flags = (await connection.execute(text('''SELECT rolsuper, rolcreatedb, rolcreaterole,
                rolreplication, rolbypassrls FROM pg_roles WHERE rolname=current_user'''))).one()
            if any(flags):
                raise ValueError('La API necesita un rol de ejecución limitado, no el propietario.')
            for sql in (
                "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)",
                "SELECT count(*) FROM pg_class WHERE relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)",
                "SELECT count(*) FROM pg_namespace WHERE nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)",
                "SELECT count(*) FROM pg_database WHERE datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)",
            ):
                if await connection.scalar(text(sql)):
                    raise ValueError('La API no debe tener membresías elevadas ni ser propietaria de objetos.')
            if await connection.scalar(text("SELECT has_schema_privilege(current_user,'public','CREATE')")):
                raise ValueError('El rol de ejecución no debe tener DDL.')
            for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'TRIGGER'):
                permitted = await connection.scalar(text("SELECT has_table_privilege(current_user,'public.audit_log',:p)"), {'p': privilege})
                if permitted != (privilege in ('SELECT', 'INSERT')):
                    raise ValueError('Los permisos de auditoría no son los esperados.')
            if not await connection.scalar(text("""SELECT count(*) FROM pg_trigger WHERE
                tgrelid='public.audit_log'::regclass AND tgname='agecare_audit_immutable' AND tgenabled='O'""")):
                raise ValueError('Falta la protección PostgreSQL de auditoría.')
            expected = set(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())
            actual = set((await connection.execute(text('SELECT version_num FROM alembic_version'))).scalars())
            if actual != expected:
                raise ValueError('El esquema requiere migración por separado antes de arrancar Render.')
            if check_accounts:
                count = await development_password_count(connection)
                if count:
                    raise ValueError(f'Hay {count} cuentas activas con contraseñas públicas de desarrollo. Cambiarlas antes de publicar.')
    finally:
        await engine.dispose()


async def development_password_count(connection):
    from app.security import verify_password
    from scripts.bootstrap_dev_accounts import DEV_ACCOUNTS
    passwords = {row[2] for row in DEV_ACCOUNTS}
    hashes = (await connection.execute(text('SELECT password_hash FROM admin_users WHERE is_active AND password_hash IS NOT NULL'))).scalars().all()
    return sum(any(verify_password(password, hashed) for password in passwords) for hashed in hashes)


def main():
    try:
        if not os.environ.get('ADMIN_GAME_PUBLIC_BASE_URL') and os.environ.get('RENDER_EXTERNAL_URL'):
            os.environ['ADMIN_GAME_PUBLIC_BASE_URL'] = os.environ['RENDER_EXTERNAL_URL']
        settings = get_settings()
        validate_settings(settings)
        port = int(os.environ.get('PORT', '8000'))
        if not 1 <= port <= 65535:
            raise ValueError('Puerto no válido.')
        asyncio.run(check_database(settings.database_url,
                                  check_accounts=not settings.render_allow_dev_credentials))
    except ValueError as exc:
        # No imprimir ValidationError de terceros: puede incluir entradas privadas.
        if type(exc) is ValueError and str(exc).startswith(('Render requiere', 'Falta una clave', 'El arranque', 'Falta la raíz', 'CORS debe', 'La API ', 'El rol ', 'Los permisos', 'Falta la protección', 'El esquema', 'Hay ', 'Puerto no válido')):
            raise SystemExit(str(exc)) from None
        raise SystemExit('Configuración Render inválida; revisar variables privadas, clave MFA y conexión sin publicar sus valores.') from None
    except Exception:
        raise SystemExit('No se pudo verificar el arranque Render. Revisar TLS, conexión, rol limitado y migraciones; no se imprime información privada.') from None
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', str(port)])


if __name__ == '__main__':
    main()
