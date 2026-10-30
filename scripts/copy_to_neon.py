"""Copia explícita de Compose local a un Neon vacío; no carga seed ni borra datos.

--check solo consulta. --copy respalda, restaura en una transacción y compara
filas/huellas. La API local debe estar apagada. La URL se lee privadamente de
NEON_MIGRATION_DATABASE_URL; nunca se imprime ni se pasa como argumento.
"""
import argparse
from contextlib import suppress
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import uuid

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ['docker', 'compose']
REQUIRED_TABLES = {'admin_users', 'games_apps', 'audit_log', 'alembic_version'}


class CopyError(Exception):
    """Solo mensajes seguros, sin excepciones originales ni salida SQL."""


def target_environment(value):
    try:
        url = urlsplit(value)
        host = url.hostname or ''
        if (url.scheme not in ('postgres', 'postgresql')
                or not host.endswith('.neon.tech') or '-pooler' in host.split('.')[0]
                or not url.username or not url.password or not url.path.strip('/')
                or url.fragment or (url.port not in (None, 5432))):
            raise ValueError()
        return {
            'PGHOST': host, 'PGPORT': '5432',
            'PGUSER': unquote(url.username), 'PGPASSWORD': unquote(url.password),
            'PGDATABASE': unquote(url.path[1:]),
            'PGSSLMODE': 'verify-full', 'PGSSLROOTCERT': 'system',
            'PGCHANNELBINDING': 'require', 'PGCONNECT_TIMEOUT': '15',
            'PGOPTIONS': '-c timezone=UTC -c statement_timeout=120000',
            'PGAPPNAME': 'agecare-explicit-copy',
        }
    except (ValueError, TypeError):
        raise CopyError('Revisa la conexión directa PostgreSQL de Neon guardada en la variable de transferencia.') from None


def read_target():
    # Solo interpretar la línea de esta variable, no cargar secretos de la API.
    values = []
    with (ROOT / '.env').open(encoding='utf-8-sig') as stream:
        for line in stream:
            candidate = line.strip().removeprefix('export ').lstrip()
            if candidate.partition('=')[0].strip() == 'NEON_MIGRATION_DATABASE_URL':
                values.append(dotenv_values(stream=StringIO(candidate), interpolate=False)
                              .get('NEON_MIGRATION_DATABASE_URL'))
    if len(values) != 1 or not values[0]:
        raise CopyError('Falta una única NEON_MIGRATION_DATABASE_URL válida en el .env del backend.')
    return target_environment(values[0])


def run(arguments, *, target=None, stdin=None, stdout=subprocess.PIPE, label='operación', timeout=180):
    environment = os.environ.copy()
    command = COMPOSE + ['exec', '-T']
    if target:
        environment.update(target)
        # Docker toma los valores del entorno: la contraseña no va en argv.
        for name in target:
            command += ['-e', name]
    command += ['db'] + arguments
    try:
        result = subprocess.run(command, cwd=ROOT, env=environment, stdin=stdin,
                                stdout=stdout, stderr=subprocess.PIPE, timeout=timeout,
                                check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise CopyError(f'No se completó {label}; revisa Docker y la conectividad. No se muestra salida privada.') from None
    if result.returncode:
        error = result.stderr.decode('utf-8', errors='replace').lower()
        detail = (' Revisa la contraseña guardada.' if 'password authentication failed' in error else
                  ' Revisa DNS/conexión a internet.' if 'could not translate host' in error else
                  ' Revisa el certificado TLS y los certificados del contenedor.' if 'certificate' in error else '')
        raise CopyError(f'Falló {label}.{detail} La salida SQL privada no se imprime.')
    return result.stdout


def query(sql, target=None):
    arguments = ['psql', '-X', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1']
    if not target:
        arguments += ['-h', '/var/run/postgresql', '-U', 'agecare', '-d', 'agecare_admin']
    raw = run(arguments + ['-c', "SET TIME ZONE 'UTC'; " + sql], target=target,
              label='consulta Neon' if target else 'consulta local')
    try:
        return json.loads(raw.decode('utf-8').strip())
    except (ValueError, UnicodeError):
        raise CopyError('La consulta no devolvió el resumen esperado; se detiene la copia.') from None


def require_api_stopped():
    try:
        status = subprocess.run(COMPOSE + ['ps', '--status', 'running', '--format', 'json', 'api'],
                                cwd=ROOT, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise CopyError('No se pudo comprobar si la API local está apagada.') from None
    if status.returncode or status.stdout.strip() not in (b'', b'[]'):
        raise CopyError('La API local debe permanecer apagada durante la copia; no se detendrá automáticamente.')


TABLES_SQL = """SELECT coalesce(json_agg(json_build_object('schema', schemaname,
    'name', tablename) ORDER BY schemaname, tablename), '[]'::json)
    FROM pg_tables WHERE schemaname NOT LIKE 'pg_%'
    AND schemaname <> 'information_schema'"""

EMPTY_SQL = """SELECT json_build_object(
    'relations', (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
        AND c.relkind IN ('r','p','v','m','S','f')),
    'functions', (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND NOT EXISTS (SELECT 1 FROM pg_depend d
            WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')),
    'types', (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname='public' AND t.typtype IN ('e','d'))
)"""


def require_empty(target):
    if any(query(EMPTY_SQL, target).values()):
        raise CopyError('Neon contiene objetos o datos. No se sobrescribirá ni limpiará: revisar el destino.')


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def manifest(tables, target=None):
    selects = []
    for table in tables:
        name = table['schema'] + '.' + table['name']
        relation = quote_identifier(table['schema']) + '.' + quote_identifier(table['name'])
        literal = "'" + name.replace("'", "''") + "'"
        selects.append(f"SELECT {literal} AS name, count(*) AS rows, "
                       "md5(coalesce(string_agg(md5(to_jsonb(r)::text), '' "
                       f"ORDER BY md5(to_jsonb(r)::text)), '')) AS fingerprint FROM {relation} r")
    sql = 'SELECT json_agg(s ORDER BY name) FROM (' + ' UNION ALL '.join(selects) + ') s'
    return query(sql, target)


def ensure_same(expected, actual):
    if actual != expected:
        raise CopyError('La comparación de tablas, cantidades o huellas no coincide. Conservar respaldo y revisar; no borrar ni reintentar sobre Neon ocupado.')


def restore(backup, target):
    with backup.open('rb') as stream:
        toc = run(['pg_restore', '--list'], stdin=stream, label='validación del archivo de respaldo')
    # public ya existe en una base vacía de Neon: conservarlo, sin DROP/--clean.
    lines = toc.decode('utf-8').splitlines()
    existing_public = re.compile(r'^\d+; \d+ \d+ (?:SCHEMA - public|COMMENT - SCHEMA public)(?: |$)')
    selected = '\n'.join(line for line in lines if not existing_public.match(line)) + '\n'
    list_file = backup.with_name('restore.list')
    list_file.write_text(selected, encoding='utf-8')
    temporary_list = '/tmp/agecare-neon-' + uuid.uuid4().hex + '.list'
    try:
        with list_file.open('rb') as stream:
            run(['tee', temporary_list], stdin=stream, stdout=subprocess.DEVNULL,
                label='preparación del índice de restauración')
        with backup.open('rb') as stream:
            run(['pg_restore', '--dbname=' + target['PGDATABASE'], '--no-owner', '--no-acl',
                 '--single-transaction', '--exit-on-error', '--use-list=' + temporary_list],
                target=target, stdin=stream, label='restauración atómica en Neon', timeout=600)
    finally:
        with suppress(CopyError):
            run(['rm', '--', temporary_list], stdout=subprocess.DEVNULL,
                label='limpieza del índice temporal')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copy', action='store_true', help='respaldar y restaurar en Neon vacío')
    args = parser.parse_args()
    target = read_target()
    require_api_stopped()
    tables = query(TABLES_SQL)
    if (not REQUIRED_TABLES.issubset({t['name'] for t in tables})
            or any(t['schema'] != 'public' for t in tables)):
        raise CopyError('La fuente no coincide con el backend esperado o contiene otros esquemas; revisar antes de copiar.')
    expected = manifest(tables)
    counts = {r['name']: r['rows'] for r in expected}
    print(f"Fuente: {len(tables)} tablas, {counts['public.games_apps']} juegos, "
          f"{counts['public.admin_users']} cuentas internas.", flush=True)
    require_empty(target)
    print('Conexión Neon verificada con TLS y destino vacío.', flush=True)
    if not args.copy:
        print('Solo comprobación. No se creó respaldo ni se transfirieron datos.', flush=True)
        return
    folder = ROOT / 'backups' / datetime.now(timezone.utc).strftime('neon-%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True, exist_ok=False)
    backup = folder / 'database.dump'
    with backup.open('xb') as output:
        run(['pg_dump', '-h', '/var/run/postgresql', '-U', 'agecare', '-d', 'agecare_admin',
             '--format=custom', '--schema=public', '--lock-wait-timeout=20s', '--no-acl'],
            stdout=output, label='respaldo local')
    with backup.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = {'status': 'backup_created', 'tables': expected, 'archive_sha256': digest,
              'backup_bytes': backup.stat().st_size}
    report_file = folder / 'verification.json'
    report_file.write_text(json.dumps(report, indent=2), encoding='utf-8')
    ensure_same(expected, manifest(tables))
    require_api_stopped()
    require_empty(target)
    print(f'Respaldo creado: backups/{folder.name}/database.dump. Comienza copia atómica.', flush=True)
    restore(backup, target)
    ensure_same(tables, query(TABLES_SQL, target))
    ensure_same(expected, manifest(tables, target))
    protection = query("""SELECT json_build_object('audit_trigger', count(*)) FROM pg_trigger
        WHERE tgrelid='public.audit_log'::regclass AND tgname='agecare_audit_immutable'
        AND tgenabled='O'""", target)
    if protection['audit_trigger'] != 1:
        raise CopyError('Datos copiados, pero falta confirmar el trigger de auditoría. No publicar todavía.')
    report['status'] = 'verified'
    report['audit_trigger'] = True
    report_file.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Copia verificada: {len(tables)} tablas; cantidades y huellas coinciden. Auditoría protegida.', flush=True)
    print('Base local conservada. No se modificó la conexión de la API ni se inició su servicio.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except CopyError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print('Operación interrumpida. Revisar destino y respaldo antes de repetir.', file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print('Operación detenida por un error no esperado. No se imprime información privada; revisar antes de repetir.', file=sys.stderr)
        raise SystemExit(1) from None
