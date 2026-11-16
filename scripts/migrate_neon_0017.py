"""Migración explícita Neon0016→0017; sin --apply solo consulta."""
import argparse
import asyncio
import importlib.util
import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database_urls import database_connect_args
from scripts.copy_to_neon import ROOT, read_target
from scripts.prepare_render import owner_url, read_local
from scripts.run_render import check_database
from scripts.migrate_neon_0016 import (
    MigrationError, endpoint, manifest, profile_hashes, read_runtime, verify_tls,
)

PHASE = 'configuración'


def migration():
    spec = importlib.util.spec_from_file_location('neon_directory_0017',
        ROOT / 'alembic/versions/0017_app_directory_names.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def rows(conn, name):
    quoted = conn.dialect.identifier_preparer.quote_identifier(name)
    return (await conn.execute(text(f'SELECT to_jsonb(r) FROM public.{quoted} r ORDER BY id'))).scalars().all()


def expected_rows(before, module):
    expected = json.loads(json.dumps(before))
    for i, (name, email) in enumerate(module.ACCOUNTS, 1):
        identity = str(uuid5(NAMESPACE_URL, 'agecare:phase18:demo:user-' + str(i)))
        for row in expected['app_accounts']:
            if (row['id'] == identity and row['full_name'] == f'Persona de prueba {i:02}'
                    and row['email'] == f'persona{i:02}@example.test'):
                row.update(full_name=name, email=email)
    for i, name in enumerate(module.PATIENTS, 1):
        identity = str(uuid5(NAMESPACE_URL, 'agecare:phase18:demo:patient-' + str(i)))
        for row in expected['app_patients']:
            if row['id'] == identity and row['full_name'] == f'Paciente de prueba {i:02}':
                row['full_name'] = name
    return expected


async def run(apply=False):
    global PHASE
    profiles = profile_hashes()
    owner, runtime = owner_url(read_target()), read_runtime()
    if (not runtime.username or runtime.username == owner.username or not runtime.password
            or not (runtime.host or '').endswith('.neon.tech')
            or (endpoint(runtime.host), runtime.database) != (endpoint(owner.host), owner.database)):
        raise MigrationError('Los perfiles no coinciden con el mismo destino limitado.')
    if ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_heads() != ['0017']:
        raise MigrationError('Este procedimiento requiere head0017.')
    module = migration()
    engine = create_async_engine(owner, hide_parameters=True,
        connect_args={**database_connect_args(owner), 'timeout': 20, 'command_timeout': 120})
    probe = create_async_engine(runtime, hide_parameters=True,
        connect_args={**database_connect_args(runtime), 'timeout': 20, 'command_timeout': 120})
    report = {}
    try:
        PHASE = 'consulta del destino'
        async with engine.begin() as conn:
            await verify_tls(conn)
            await conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            revisions = (await conn.execute(text('SELECT version_num FROM public.alembic_version'))).scalars().all()
            if len(revisions) != 1 or revisions[0] not in ('0016', '0017'):
                raise MigrationError('Versión de origen inesperada; no se modifica.')
            current = revisions[0]
            tables = (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars().all()
            source = {new: old if current == '0016' else new for old, new in module.RENAMES}
            if any(name not in tables for name in source.values()):
                raise MigrationError('Faltan tablas del directorio esperado.')
            print('Neon:', current, '| TLS verificado | Directorio:',
                {new: await conn.scalar(text('SELECT count(*) FROM public.' + old)) for new, old in source.items()}, flush=True)
            if not apply:
                print('Solo consulta; pendiente0017.' if current == '0016' else 'Sin migraciones pendientes.', flush=True)
                return
            if current == '0016':
                PHASE = 'respaldo y bloqueo del directorio'
                await conn.execute(text("SET LOCAL lock_timeout='10s'"))
                await conn.execute(text("SET LOCAL statement_timeout='120s'"))
                await conn.execute(text('SELECT pg_advisory_xact_lock(7240062617)'))
                for name in sorted(source.values()):
                    await conn.execute(text('LOCK TABLE public.' + name + ' IN ACCESS EXCLUSIVE MODE'))
                before = {new: await rows(conn, old) for new, old in source.items()}
                unchanged = [name for name in tables if name not in (*source.values(), 'alembic_version')]
                fingerprints = await manifest(conn, unchanged)
                grants = (await conn.execute(text("SELECT oid, relname, relacl::text FROM pg_class WHERE oid IN (SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('demo_app_accounts','demo_app_patients','demo_app_memberships')) ORDER BY oid"))).mappings().all()
                backup = ROOT / 'backups' / ('neon-schema-0017-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
                backup.mkdir(parents=True, exist_ok=False)
                cipher = Fernet(read_local('ADMIN_ENCRYPTION_KEY').encode())
                payload = json.dumps({'revision': current, 'directory': before,
                    'manifest': fingerprints, 'grants': [dict(row) for row in grants]}, ensure_ascii=False).encode()
                (backup / 'before.enc').write_bytes(cipher.encrypt(payload))
                if cipher.decrypt((backup / 'before.enc').read_bytes()) != payload:
                    raise MigrationError('Respaldo cifrado no verificado.')
                PHASE = 'aplicación transaccional0017'
                def upgrade(bind):
                    module.op = Operations(MigrationContext.configure(bind))
                    module.upgrade()
                await conn.run_sync(upgrade)
                await conn.execute(text("UPDATE public.alembic_version SET version_num='0017'"))
                after = {name: await rows(conn, name) for name in source}
                if after != expected_rows(before, module):
                    raise MigrationError('Diferencia no prevista en directorio; se revierte.')
                if await manifest(conn, unchanged) != fingerprints:
                    raise MigrationError('Diferencia en otras tablas; se revierte.')
                for grant in grants:
                    actual = (await conn.execute(text('SELECT relacl::text FROM pg_class WHERE oid=:oid'), {'oid': grant['oid']})).scalar_one()
                    if actual != grant['relacl']:
                        raise MigrationError('Permisos alterados; se revierte.')
                orphans = await conn.scalar(text('SELECT count(*) FROM public.app_memberships m LEFT JOIN public.app_accounts a ON a.id=m.user_id LEFT JOIN public.app_patients p ON p.id=m.patient_id WHERE a.id IS NULL OR p.id IS NULL'))
                if orphans:
                    raise MigrationError('Vínculos huérfanos; se revierte.')
                report = {'after_revision': '0017', 'preserved_other_tables': len(unchanged),
                    'directory_rows': {name: len(data) for name, data in after.items()},
                    'changed_accounts': sum(a != b for a, b in zip(before['app_accounts'], after['app_accounts'])),
                    'changed_patients': sum(a != b for a, b in zip(before['app_patients'], after['app_patients'])),
                    'orphans': orphans, 'backup': str(backup.relative_to(ROOT))}
                (backup / 'report.json').write_text(json.dumps({**report, 'transaction': 'verified_before_commit'}, indent=2), encoding='utf-8')
        PHASE = 'comprobación del rol de Render después del commit'
        await check_database(runtime.render_as_string(hide_password=False), check_accounts=False)
        async with probe.connect() as conn:
            await verify_tls(conn)
            for name in source:
                await conn.execute(text('SELECT 1 FROM public.' + name + ' LIMIT 1'))
                for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
                    if not await conn.scalar(text('SELECT has_table_privilege(current_user, CAST(:table AS text), CAST(:privilege AS text))'), {'table': 'public.' + name, 'privilege': privilege}):
                        raise MigrationError('Falta un permiso de ejecución del directorio.')
        if profile_hashes() != profiles:
            raise MigrationError('Cambió un perfil privado; revisar.')
        report.update(runtime_verified=True, transaction='committed')
        if 'backup' in report:
            (ROOT / report['backup'] / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Neon0017 y acceso de Render verificados; auditoría protegida y perfiles sin cambios.', flush=True)
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
