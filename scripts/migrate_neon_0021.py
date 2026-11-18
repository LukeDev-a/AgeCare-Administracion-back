"""Migración aditiva 0020→0021. Sin --apply solo consulta; no seed ni rotación."""
import argparse
import asyncio
import importlib.util
import json
from datetime import datetime, timezone

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database_urls import database_connect_args
from scripts.copy_to_neon import ROOT, read_target
from scripts.prepare_render import owner_url, read_local
from scripts.migrate_neon_0016 import MigrationError, endpoint, manifest, profile_hashes, read_runtime, verify_tls
from scripts.run_render import check_database

PHASE = 'configuración'
TABLE = 'ops_observations'
PRIVILEGES = ('SELECT', 'INSERT', 'UPDATE', 'DELETE')


async def audit_protected(conn, role):
    for privilege in (*PRIVILEGES, 'TRUNCATE', 'TRIGGER'):
        allowed = await conn.scalar(text(
            "SELECT has_table_privilege(CAST(:role AS text),'public.audit_log',CAST(:p AS text))"),
            {'role': role, 'p': privilege})
        if allowed != (privilege in ('SELECT', 'INSERT')):
            raise MigrationError('Los permisos de auditoría no son los esperados.')
    if not await conn.scalar(text("""SELECT count(*) FROM pg_trigger WHERE
        tgrelid='public.audit_log'::regclass AND tgname='agecare_audit_immutable' AND tgenabled='O'""")):
        raise MigrationError('Falta la protección de auditoría.')


def upgrade(bind):
    path = ROOT / 'alembic/versions/0021_ops_observations.py'
    spec = importlib.util.spec_from_file_location('neon_revision_0021', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = Operations(MigrationContext.configure(bind))
    module.upgrade()


async def run(apply=False):
    global PHASE
    profiles = profile_hashes()
    owner, runtime = owner_url(read_target()), read_runtime()
    if (not runtime.username or runtime.username == owner.username or not runtime.password
        or not all((u.host or '').endswith('.neon.tech') for u in (owner, runtime))
        or (endpoint(owner.host), owner.database) != (endpoint(runtime.host), runtime.database)):
        raise MigrationError('Los perfiles no corresponden al mismo destino limitado.')
    if ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_heads() != ['0021']:
        raise MigrationError('Este procedimiento solo admite head0021.')
    options = dict(hide_parameters=True, connect_args={**database_connect_args(owner),
        'timeout': 20, 'command_timeout': 180})
    engine = create_async_engine(owner, **options)
    probe = create_async_engine(runtime, hide_parameters=True,
        connect_args={**database_connect_args(runtime), 'timeout': 20, 'command_timeout': 120})
    report, backup = {}, None
    try:
        PHASE = 'consulta previa'
        async with probe.connect() as conn:
            await verify_tls(conn)
            flags = (await conn.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls '
                'FROM pg_roles WHERE rolname=current_user'))).one()
            if any(flags):
                raise MigrationError('El perfil runtime no es limitado.')
            await audit_protected(conn, runtime.username)
        async with engine.begin() as conn:
            await conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            await verify_tls(conn)
            if apply:
                await conn.execute(text("SET LOCAL lock_timeout='10s'"))
                await conn.execute(text("SET LOCAL statement_timeout='180s'"))
                await conn.execute(text('SELECT pg_advisory_xact_lock(7240062621)'))
                await conn.execute(text('LOCK TABLE public.alembic_version IN SHARE ROW EXCLUSIVE MODE'))
            revisions = (await conn.execute(text('SELECT version_num FROM public.alembic_version'))).scalars().all()
            if len(revisions) != 1 or revisions[0] not in ('0020', '0021'):
                raise MigrationError('Revisión inesperada; se detiene sin migrar.')
            current = revisions[0]
            tables = (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars().all()
            if (TABLE in tables) != (current == '0021'):
                raise MigrationError('La tabla y la revisión no coinciden; revisar antes de continuar.')
            print(json.dumps({'revision': current, 'pending': ['0021'] if current == '0020' else [],
                'existing_tables': len(tables), 'tls_verified': True, 'audit_protected': True}), flush=True)
            if not apply:
                print('Solo consulta; datos y permisos intactos.', flush=True)
                return
            if current == '0020':
                PHASE = 'respaldo cifrado de metadatos y huellas'
                retained = [t for t in tables if t != 'alembic_version']
                before = await manifest(conn, retained)
                backup = ROOT / 'backups' / ('neon-schema-0021-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
                backup.mkdir(parents=True, exist_ok=False)
                cipher = Fernet(read_local('ADMIN_ENCRYPTION_KEY').encode())
                payload = json.dumps({'revision': current, 'manifest': before,
                    'scope': 'Metadata and fingerprints only; existing business tables are not altered.'}).encode()
                (backup / 'before.enc').write_bytes(cipher.encrypt(payload))
                if cipher.decrypt((backup / 'before.enc').read_bytes()) != payload:
                    raise MigrationError('No se pudo verificar el respaldo de metadatos.')
                PHASE = 'migración transaccional'
                await conn.run_sync(upgrade)
                await conn.execute(text("UPDATE public.alembic_version SET version_num='0021' WHERE version_num='0020'"))
                if await manifest(conn, retained) != before:
                    raise MigrationError('Cambió una tabla existente; se revierte.')
                if await conn.scalar(text('SELECT count(*) FROM public.ops_observations')) != 0:
                    raise MigrationError('La tabla nueva no está vacía; se revierte.')
                report.update(before_revision=current, after_revision='0021', preserved_tables=len(retained),
                    preserved_rows={k: v['rows'] for k, v in before.items()},
                    backup=str(backup.relative_to(ROOT)), backup_scope='revision_and_fingerprints')
            role = conn.dialect.identifier_preparer.quote_identifier(runtime.username)
            await conn.execute(text(f'GRANT SELECT,INSERT,UPDATE,DELETE ON public.ops_observations TO {role}'))
            await audit_protected(conn, runtime.username)
            indexes = await conn.run_sync(lambda bind: inspect(bind).get_indexes(TABLE))
            if not any(i['name'] == 'ix_ops_observations_component_time'
                and i['column_names'] == ['component_key', 'observed_at', 'id'] for i in indexes):
                raise MigrationError('Falta el índice compuesto; se revierte.')
            if profile_hashes() != profiles:
                raise MigrationError('Cambió un perfil privado; se detiene.')
        PHASE = 'verificación runtime posterior al commit'
        await check_database(runtime.render_as_string(hide_password=False), check_accounts=False)
        async with probe.connect() as conn:
            await verify_tls(conn)
            await conn.execute(text('SELECT 1 FROM public.ops_observations LIMIT 1'))
            for privilege in PRIVILEGES:
                if not await conn.scalar(text("SELECT has_table_privilege(current_user,'public.ops_observations',CAST(:p AS text))"), {'p': privilege}):
                    raise MigrationError('Falta un permiso runtime del monitor.')
        report.update(after_revision='0021', runtime_verified=True, audit_protected=True,
            private_profiles_unchanged=profile_hashes() == profiles, transaction='committed')
        if backup:
            (backup / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    finally:
        await engine.dispose()
        await probe.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    try:
        asyncio.run(run(parser.parse_args().apply))
    except Exception as error:
        if isinstance(error, MigrationError):
            print(str(error), flush=True)
        raise SystemExit(f'Operación detenida en {PHASE} ({type(error).__name__}); detalles privados omitidos.') from None
