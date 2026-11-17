"""Neon0017..0020: respaldo cifrado, migración acotada y permisos runtime. Sin --apply solo consulta."""
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
from scripts.migrate_neon_0016 import MigrationError, endpoint, manifest, profile_hashes, read_runtime, verify_tls

PHASE = 'configuración'
FILES = {'0018': '0018_scheduled_text_only.py', '0019': '0019_payment_storage.py', '0020': '0020_coherent_directory_samples.py'}
DIRECTORY = ('app_accounts', 'app_patients', 'app_memberships')
PAYMENTS = ('payment_subscriptions', 'payment_charges')


def load(revision):
    spec = importlib.util.spec_from_file_location('neon_'+revision, ROOT/'alembic/versions'/FILES[revision])
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def identity(key):
    return str(uuid5(NAMESPACE_URL, 'agecare:phase18:demo:'+key))


async def rows(conn, table):
    quoted = conn.dialect.identifier_preparer.quote_identifier(table)
    return (await conn.execute(text(f'SELECT to_jsonb(r) FROM public.{quoted} r ORDER BY id'))).scalars().all()


def verify_directory(before, after):
    if before['app_accounts'] != after['app_accounts']:
        raise MigrationError('Cambios no previstos en cuentas; se revierte.')
    accounts = {r['id']: r for r in before['app_accounts']}
    patients = {r['id']: r for r in before['app_patients']}
    actual_patients = {r['id']: r for r in after['app_patients']}
    for key, row in patients.items():
        if actual_patients.get(key) != row:
            raise MigrationError('Cambió una ficha existente; se revierte.')
    def account_matches(u, name, email):
        r = accounts.get(identity(f'user-{u}'), {})
        return r.get('full_name') == name and r.get('email') == email
    def patient_matches(p, name):
        return actual_patients.get(identity(f'patient-{p}'), {}).get('full_name') == name
    added = actual_patients.keys() - patients.keys()
    if added:
        if (added != {identity('patient-8')} or not patient_matches(8, 'Elvira Paredes')
            or not account_matches(11, 'Elena Morales', 'elena.morales@gmail.com')
            or any(r['full_name'] == 'Elvira Paredes' for r in patients.values())):
            raise MigrationError('Nueva ficha no prevista; se revierte.')
    expected = {r['id']: dict(r) for r in before['app_memberships']}
    carmen = expected.get(identity('link-3-7'))
    if (carmen and account_matches(7, 'Carmen Soto', 'carmen.soto@gmail.com') and patient_matches(3, 'Carmen Soto')
        and carmen['patient_id'] == identity('patient-3') and carmen['user_id'] == identity('user-7')
        and carmen['role'] == 'family' and carmen['is_owner']):
        carmen['role'] = 'elder'
    for p, pn, u, name, email, role, owner in load('0020').PAIRS:
        key = identity(f'link-{p}-{u}')
        if (not account_matches(u, name, email) or not patient_matches(p, pn) or key in expected
            or any(r['patient_id'] == identity(f'patient-{p}') and r['user_id'] == identity(f'user-{u}') for r in expected.values())):
            continue
        expected[key] = dict(id=key, patient_id=identity(f'patient-{p}'), user_id=identity(f'user-{u}'), role=role, is_owner=owner)
    if expected != {r['id']: r for r in after['app_memberships']}:
        raise MigrationError('Diferencia no prevista en vínculos; se revierte.')


async def run(apply=False):
    global PHASE
    profiles = profile_hashes()
    owner, runtime = owner_url(read_target()), read_runtime()
    if (not runtime.username or runtime.username == owner.username or not runtime.password
        or not (owner.host or '').endswith('.neon.tech') or not (runtime.host or '').endswith('.neon.tech')
        or (endpoint(runtime.host), runtime.database) != (endpoint(owner.host), owner.database)):
        raise MigrationError('Los perfiles no corresponden al mismo destino limitado.')
    if ScriptDirectory.from_config(Config(str(ROOT/'alembic.ini'))).get_heads() != ['0020']:
        raise MigrationError('Este procedimiento requiere head0020.')
    options = dict(hide_parameters=True, connect_args={**database_connect_args(owner), 'timeout': 20, 'command_timeout': 180})
    engine = create_async_engine(owner, **options)
    probe = create_async_engine(runtime, hide_parameters=True,
        connect_args={**database_connect_args(runtime), 'timeout': 20, 'command_timeout': 120})
    report = {}
    try:
        PHASE = 'verificación del destino'
        async with probe.connect() as conn:
            await verify_tls(conn)
            flags = (await conn.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user'))).one()
            if any(flags):
                raise MigrationError('El perfil de Render no es limitado.')
        async with engine.begin() as conn:
            await conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            await verify_tls(conn)
            if apply:
                await conn.execute(text("SET LOCAL lock_timeout='10s'"))
                await conn.execute(text("SET LOCAL statement_timeout='180s'"))
                await conn.execute(text('SELECT pg_advisory_xact_lock(7240062620)'))
                await conn.execute(text('LOCK TABLE public.alembic_version, public.content_items, public.app_accounts, public.app_patients, public.app_memberships IN SHARE ROW EXCLUSIVE MODE'))
            revisions = (await conn.execute(text('SELECT version_num FROM public.alembic_version'))).scalars().all()
            if len(revisions) != 1 or revisions[0] not in ('0017', '0018', '0019', '0020'):
                raise MigrationError('Revisión de origen inesperada; se detiene.')
            current = revisions[0]
            tables = (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars().all()
            counts = {name: await conn.scalar(text('SELECT count(*) FROM public.'+name)) for name in (*DIRECTORY, *PAYMENTS) if name in tables}
            print(json.dumps({'revision': current, 'pending': [r for r in FILES if r > current], 'rows': counts, 'tls_verified': True}), flush=True)
            if not apply:
                print('Solo consulta; ningún dato o permiso modificado.', flush=True)
                return
            PHASE = 'respaldo cifrado'
            for table in PAYMENTS:
                if table in tables:
                    await conn.execute(text('LOCK TABLE public.'+table+' IN SHARE ROW EXCLUSIVE MODE'))
            selected = [*DIRECTORY, 'content_items', *[t for t in PAYMENTS if t in tables]]
            before = {name: await rows(conn, name) for name in selected}
            unchanged = [t for t in tables if t not in (*selected, 'alembic_version')]
            fingerprints = await manifest(conn, unchanged)
            backup = ROOT/'backups'/('neon-schema-0020-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            backup.mkdir(parents=True, exist_ok=False)
            cipher = Fernet(read_local('ADMIN_ENCRYPTION_KEY').encode())
            payload = json.dumps({'revision': current, 'rows': before, 'other_tables': fingerprints}, ensure_ascii=False).encode()
            (backup/'before.enc').write_bytes(cipher.encrypt(payload))
            if cipher.decrypt((backup/'before.enc').read_bytes()) != payload:
                raise MigrationError('No se pudo verificar el respaldo cifrado.')
            PHASE = 'migración transaccional'
            for revision in FILES:
                if revision > current:
                    def upgrade(bind, revision=revision):
                        module = load(revision); module.op = Operations(MigrationContext.configure(bind)); module.upgrade()
                    await conn.run_sync(upgrade)
                    await conn.execute(text('UPDATE public.alembic_version SET version_num=:revision'), {'revision': revision})
            after = {name: await rows(conn, name) for name in (*DIRECTORY, 'content_items', *PAYMENTS)}
            verify_directory(before, after)
            expected_content = [dict(row, **({} if 'schedule_audio_exception' in row else {'schedule_audio_exception': None})) for row in before['content_items']]
            if after['content_items'] != expected_content:
                raise MigrationError('Cambió el contenido editorial; se revierte.')
            for table in PAYMENTS:
                if after[table] != before.get(table, []):
                    raise MigrationError('Cambió un pago previo; se revierte.')
            if await manifest(conn, unchanged) != fingerprints:
                raise MigrationError('Cambió otra tabla; se revierte.')
            role = conn.dialect.identifier_preparer.quote_identifier(runtime.username)
            for table in PAYMENTS:
                await conn.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO {role}'))
            for privilege in ('UPDATE', 'DELETE', 'TRUNCATE', 'TRIGGER'):
                if await conn.scalar(text('SELECT has_table_privilege(CAST(:role AS text),\'public.audit_log\',CAST(:p AS text))'), {'role': runtime.username, 'p': privilege}):
                    raise MigrationError('Auditoría perdió su protección; se revierte.')
            report = dict(before_revision=current, after_revision='0020', backup=str(backup.relative_to(ROOT)),
                preserved_other_tables=len(unchanged), rows={k: len(v) for k, v in after.items()}, transaction='verified_before_commit')
            (backup/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        PHASE = 'verificación de Render'
        await check_database(runtime.render_as_string(hide_password=False), check_accounts=False)
        async with probe.connect() as conn:
            await verify_tls(conn)
            for table in PAYMENTS:
                await conn.execute(text('SELECT 1 FROM public.'+table+' LIMIT 1'))
                for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
                    if not await conn.scalar(text('SELECT has_table_privilege(current_user,CAST(:t AS text),CAST(:p AS text))'), {'t': 'public.'+table, 'p': privilege}):
                        raise MigrationError('Faltan permisos runtime de pagos.')
        if profile_hashes() != profiles:
            raise MigrationError('Se modificó un perfil privado; revisar.')
        report.update(transaction='committed', runtime_verified=True, private_profiles_unchanged=True)
        (ROOT/report['backup']/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    finally:
        await engine.dispose(); await probe.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    try:
        asyncio.run(run(parser.parse_args().apply))
    except Exception as error:
        if isinstance(error, MigrationError):
            print(str(error), flush=True)
        raise SystemExit(f'Operación detenida en {PHASE} ({type(error).__name__}); detalles privados omitidos.') from None
