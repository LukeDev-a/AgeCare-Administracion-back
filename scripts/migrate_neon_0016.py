"""Operación explícita 0014/0015 -> 0016: sin rotar credenciales, seed o envíos.

Sin --apply solo consulta. Destino y credencial limitada se leen privadamente
de los perfiles existentes. No crea roles ni modifica la configuración local.
"""
import argparse
import asyncio
import hashlib
import importlib.util
from datetime import datetime, timezone
from io import StringIO
import json
import ssl
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.database_urls import database_connect_args, normalize_database_url
from scripts.copy_to_neon import ROOT, read_target
from scripts.prepare_render import owner_url, read_local
from scripts.run_render import check_database

NEW_TABLES = ('admin_mfa_recoveries', 'mfa_recovery_emails')
PROFILES = ('.env', '.env.render', '.env.render-mail')
PHASE = 'comprobación de configuración'


class MigrationError(Exception):
    """Diagnósticos propios sin datos de conexión."""
    pass


def read_runtime():
    found = []
    with (ROOT / '.env.render').open(encoding='utf-8-sig') as stream:
        for line in stream:
            candidate = line.strip()
            if candidate.partition('=')[0].strip() == 'ADMIN_DATABASE_URL':
                found.append(dotenv_values(stream=StringIO(candidate), interpolate=False).get('ADMIN_DATABASE_URL'))
    if len(found) != 1 or not found[0]:
        raise MigrationError('Falta una única conexión limitada existente.')
    return make_url(normalize_database_url(found[0]))


def endpoint(host):
    name, rest = host.split('.', 1)
    return name.removesuffix('-pooler') + '.' + rest


def profile_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in PROFILES if (ROOT / name).exists()}


async def verify_tls(conn):
    # Neon termina TLS en su proxy; pg_stat_ssl describe otro tramo de conexión.
    # Comprobar el transporte de este cliente y su contexto de verificación.
    raw = await conn.get_raw_connection()
    transport = raw.driver_connection._transport
    tls = transport.get_extra_info('ssl_object')
    if (tls is None or tls.context.verify_mode != ssl.CERT_REQUIRED
            or not tls.context.check_hostname or not tls.getpeercert()):
        raise MigrationError('No se pudo verificar TLS del cliente y el certificado del destino.')


async def manifest(conn, tables):
    result = {}
    for name in tables:
        quoted = conn.dialect.identifier_preparer.quote_identifier(name)
        row = (await conn.execute(text(f'''SELECT count(*) AS rows,
            md5(coalesce(string_agg(md5(to_jsonb(r)::text), '' ORDER BY md5(to_jsonb(r)::text)), '')) AS fingerprint
            FROM public.{quoted} r'''))).mappings().one()
        result[name] = dict(row)
    return result


def apply_revision(bind, revision):
    filename = {'0015': '0015_mfa_recovery.py', '0016': '0016_runtime_settings.py'}[revision]
    spec = importlib.util.spec_from_file_location('neon_migration_' + revision, ROOT / 'alembic/versions' / filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.op = Operations(MigrationContext.configure(bind))
    module.upgrade()


async def run(*, apply=False):
    global PHASE
    before_profiles = profile_hashes()
    owner = owner_url(read_target())
    runtime = read_runtime()
    if (not runtime.username or runtime.username == owner.username or not runtime.password
            or not (runtime.host or '').endswith('.neon.tech')
            or (endpoint(runtime.host), runtime.database) != (endpoint(owner.host), owner.database)):
        raise MigrationError('Los perfiles no corresponden al mismo destino limitado esperado.')
    if set(ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_heads()) != {'0016'}:
        raise MigrationError('Este procedimiento solo admite head0016.')
    engine = create_async_engine(owner, hide_parameters=True,
        connect_args={**database_connect_args(owner), 'timeout': 20, 'command_timeout': 120})
    probe = create_async_engine(runtime, hide_parameters=True,
        connect_args={**database_connect_args(runtime), 'timeout': 20, 'command_timeout': 120})
    report = {}
    try:
        PHASE = 'verificación del destino y rol limitado'
        async with probe.connect() as conn:
            await verify_tls(conn)
            if await conn.scalar(text('SELECT current_user')) != runtime.username:
                raise MigrationError('El rol limitado no coincide con el perfil.')
            flags = (await conn.execute(text('SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls '
                                             'FROM pg_roles WHERE rolname=current_user'))).one()
            if any(flags):
                raise MigrationError('El perfil no corresponde a un rol limitado.')
        async with engine.begin() as conn:
            await verify_tls(conn)
            if apply:
                await conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
                await conn.execute(text("SET LOCAL lock_timeout='10s'"))
                await conn.execute(text("SET LOCAL statement_timeout='120s'"))
                await conn.execute(text('SELECT pg_advisory_xact_lock(7240062616)'))
                await conn.execute(text('LOCK TABLE public.system_settings IN SHARE ROW EXCLUSIVE MODE'))
            revisions = (await conn.execute(text('SELECT version_num FROM public.alembic_version'))).scalars().all()
            if len(revisions) != 1 or revisions[0] not in ('0014', '0015', '0016'):
                raise MigrationError('Revisión de origen inesperada; no se aplicarán otras migraciones.')
            report['before_revision'] = revisions[0]
            tables = (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars().all()
            settings_before = (await conn.execute(text('SELECT to_jsonb(s) AS data FROM public.system_settings s ORDER BY key'))).scalars().all()
            report['existing_settings'] = [row['key'] for row in settings_before]
            print('Versión Neon:', revisions[0], '| Destino y acceso limitado verificados mediante TLS.', flush=True)
            if not apply:
                print('Solo consulta: migraciones pendientes:', ', '.join(r for r in ('0015', '0016') if r > revisions[0]) or 'ninguna', flush=True)
                return
            PHASE = 'respaldo cifrado previo'
            cipher = Fernet(read_local('ADMIN_ENCRYPTION_KEY').encode())
            before = await manifest(conn, tables)
            backup = ROOT / 'backups' / ('neon-schema-0016-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            backup.mkdir(parents=True, exist_ok=False)
            encrypted = cipher.encrypt(json.dumps({'revision': revisions[0], 'system_settings': settings_before,
                'manifest': before}, ensure_ascii=False, default=str).encode())
            (backup / 'before.enc').write_bytes(encrypted)
            if json.loads(cipher.decrypt((backup / 'before.enc').read_bytes()))['system_settings'] != settings_before:
                raise MigrationError('No se verificó el respaldo de configuración.')
            PHASE = 'migraciones y permisos transaccionales'
            for revision in ('0015', '0016'):
                if revision > revisions[0]:
                    await conn.run_sync(lambda bind, revision=revision: apply_revision(bind, revision))
                    await conn.execute(text('UPDATE public.alembic_version SET version_num=:revision'), {'revision': revision})
            role = conn.dialect.identifier_preparer.quote_identifier(runtime.username)
            for name in NEW_TABLES:
                table = conn.dialect.identifier_preparer.quote_identifier(name)
                await conn.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO {role}'))
                for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
                    if not await conn.scalar(text('SELECT has_table_privilege(CAST(:role AS name),CAST(:table AS text),CAST(:privilege AS text))'),
                        {'role': runtime.username, 'table': 'public.' + name, 'privilege': privilege}):
                        raise MigrationError('No se verificaron los permisos nuevos.')
            after = await manifest(conn, [name for name in tables if name not in ('alembic_version', 'system_settings')])
            if after != {name: value for name, value in before.items() if name not in ('alembic_version', 'system_settings')}:
                raise MigrationError('Cambió una tabla anterior dentro de la operación; se revierte.')
            settings_after = (await conn.execute(text('SELECT to_jsonb(s) AS data FROM public.system_settings s ORDER BY key'))).scalars().all()
            after_by_key = {row['key']: row for row in settings_after}
            if any(after_by_key.get(row['key']) != row for row in settings_before):
                raise MigrationError('Se modificó una configuración anterior; se revierte.')
            if not {'system_texts', 'feature_flags'}.issubset(after_by_key):
                raise MigrationError('Faltan las claves operativas.')
            report.update({'after_revision': '0016', 'preserved_tables': len(after),
                'preserved_settings': len(settings_before), 'backup': str(backup.relative_to(ROOT)),
                'settings': sorted(after_by_key), 'new_table_rows': {name: await conn.scalar(text('SELECT count(*) FROM public.' + name)) for name in NEW_TABLES}})
        PHASE = 'comprobación final del rol de Render'
        await check_database(runtime.render_as_string(hide_password=False), check_accounts=False)
        async with probe.connect() as conn:
            for name in NEW_TABLES:
                await conn.execute(text('SELECT 1 FROM public.' + name + ' LIMIT 1'))
        if profile_hashes() != before_profiles:
            raise MigrationError('Cambió un perfil local durante la operación; revisar privadamente.')
        report['runtime_verified'] = True
        (ROOT / report['backup'] / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print('Neon en0016; tablas y configuración anteriores conservadas.', flush=True)
        print('DML de recuperación MFA verificado. Auditoría conserva solo SELECT/INSERT para Render.', flush=True)
        print('Perfiles y credenciales sin cambios. Respaldo cifrado y reporte guardados en backups/.', flush=True)
        print(json.dumps({key: report[key] for key in ('after_revision', 'preserved_tables', 'preserved_settings', 'new_table_rows', 'runtime_verified')}, ensure_ascii=False), flush=True)
    finally:
        await probe.dispose(); await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    try:
        asyncio.run(run(apply=parser.parse_args().apply))
    except Exception as error:
        if isinstance(error, MigrationError):
            print(str(error), flush=True)
        state = getattr(getattr(error, 'orig', None), 'sqlstate', None)
        suffix = f' SQLSTATE {state}.' if isinstance(state, str) and len(state) == 5 and state.isalnum() else ''
        raise SystemExit(f'Operación detenida en {PHASE} ({type(error).__name__}).{suffix} No se imprimen secretos ni SQL.') from None
