"""Preparar credencial estable limitada y .env.render privado desde este equipo.

Usa la conexión propietaria de transferencia solo aquí; no la envía a Render.
No cambia cuentas, datos de negocio, clave MFA ni el .env local.
"""
import asyncio
import argparse
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import secrets
import tempfile

from cryptography.fernet import Fernet
from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from app.database_urls import database_connect_args

from scripts.copy_to_neon import ROOT, read_target
from scripts.run_api import provision_runtime
from scripts.run_render import check_database, development_password_count

MARKER = '# AgeCare Render privado v1'
PHASE = 'configuración privada'


def read_local(name, default=None):
    found = []
    with (ROOT / '.env').open(encoding='utf-8-sig') as stream:
        for line in stream:
            candidate = line.strip().removeprefix('export ').lstrip()
            if candidate.partition('=')[0].strip() == name:
                found.append(dotenv_values(stream=StringIO(candidate), interpolate=False).get(name))
    if len(found) > 1:
        raise ValueError('Hay una variable de configuración duplicada; revisarla privadamente.')
    return found[0] if found else default


def owner_url(target):
    return URL.create('postgresql+asyncpg', username=target['PGUSER'],
                      password=target['PGPASSWORD'], host=target['PGHOST'], port=5432,
                      database=target['PGDATABASE'], query={'ssl': 'verify-full'})


def private_environment(owner, destination):
    role = 'agecare_api_' + hashlib.sha256(owner.database.encode()).hexdigest()[:16]
    if destination.exists():
        with destination.open(encoding='utf-8') as stream:
            if stream.readline().strip() != MARKER:
                raise ValueError('El archivo privado existente no fue creado por este preparador.')
        data = dict(dotenv_values(destination, interpolate=False))
        runtime = make_url(data['ADMIN_DATABASE_URL'])
        if (runtime.host, runtime.database, runtime.username) != (owner.host, owner.database, role):
            raise ValueError('El archivo privado no corresponde a este destino y rol.')
        if data['ADMIN_ENCRYPTION_KEY'] != read_local('ADMIN_ENCRYPTION_KEY'):
            raise ValueError('La clave MFA del archivo privado no coincide con la original; no se sustituirá.')
        return data, runtime.password
    encryption_key = read_local('ADMIN_ENCRYPTION_KEY')
    if not encryption_key:
        raise ValueError('Falta conservar la clave de cifrado original antes de preparar Render.')
    Fernet(encryption_key.encode())
    password = secrets.token_hex(32)
    runtime = owner.set(username=role, password=password)
    data = {
        # Entorno de demostración acordado; sin bootstrap ni carga automática.
        'ADMIN_ENVIRONMENT': 'dev',
        'ADMIN_RENDER_ALLOW_DEV_CREDENTIALS': 'false',
        'ADMIN_DATABASE_URL': runtime.render_as_string(hide_password=False),
        'ADMIN_JWT_SECRET': secrets.token_hex(32),
        'ADMIN_ENCRYPTION_KEY': encryption_key,
        'ADMIN_MFA_REQUIRED_ROLES': read_local('ADMIN_MFA_REQUIRED_ROLES', 'admin'),
        'ADMIN_ALLOWED_EMAIL_DOMAINS': read_local('ADMIN_ALLOWED_EMAIL_DOMAINS', 'wellq.co.uk,wellq.co'),
        'ADMIN_ALLOWS_ORIGINS': 'http://localhost:5173,http://127.0.0.1:5173',
        'ADMIN_FRONTEND_URL': 'http://localhost:5173',
        'ADMIN_GAME_PUBLIC_BASE_URL': '',  # run_render usa RENDER_EXTERNAL_URL.
        'ADMIN_BOOTSTRAP_DEV_ACCOUNTS': 'false',
        'ADMIN_SEED_DEMO_ENABLED': 'false',
        'ADMIN_END_USERS_DEMO_ENABLED': read_local('ADMIN_END_USERS_DEMO_ENABLED', 'true'),
        'ADMIN_MAIL_WORKER_ENABLED': 'false',
        'ADMIN_CONTENT_WORKER_ENABLED': 'false',
        'ADMIN_COMMERCIAL_WORKER_ENABLED': 'false',
        'ADMIN_GEMINI_FREE_TIER_CONFIRMED': 'false',
    }
    # Crear una sola vez: repetir preparación conserva contraseña y JWT.
    with destination.open('x', encoding='utf-8') as stream:
        stream.write(MARKER + '\n# Solo para Environment de Render. Nunca Git ni Vercel.\n')
        for key, value in data.items():
            stream.write(key + '=' + json.dumps(value, ensure_ascii=True) + '\n')
    return data, password


async def prepare(*, allow_dev_credentials=False):
    global PHASE
    owner = owner_url(read_target())
    data, password = private_environment(owner, ROOT / '.env.render')
    if allow_dev_credentials:
        data['ADMIN_RENDER_ALLOW_DEV_CREDENTIALS'] = 'true'
        # Solo la opción solicitada; conservar todos los valores y secretos.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=ROOT,
                                         prefix='.env.render-', suffix='.tmp', delete=False) as stream:
            pending = Path(stream.name)
            stream.write(MARKER + '\n# Solo para Environment de Render. Nunca Git ni Vercel.\n')
            for key, value in data.items():
                if key.startswith('ADMIN_'):
                    stream.write(key + '=' + json.dumps(value, ensure_ascii=True) + '\n')
        os.replace(pending, ROOT / '.env.render')
    # Comprobar si es primera preparación evita rotar una credencial desconocida.
    # La contraseña almacenada se reutiliza en ejecuciones posteriores.
    PHASE = 'permisos del rol Neon'
    runtime = await provision_runtime(owner.render_as_string(hide_password=False), stable_password=password)
    if make_url(runtime) != make_url(data['ADMIN_DATABASE_URL']):
        raise ValueError('No coincide la conexión limitada preparada.')
    PHASE = 'comprobación del esquema y auditoría'
    await check_database(runtime, check_accounts=False)
    PHASE = 'revisión de contraseñas de desarrollo'
    engine = create_async_engine(runtime, hide_parameters=True, connect_args=database_connect_args(runtime))
    try:
        async with engine.connect() as connection:
            count = await development_password_count(connection)
    finally:
        await engine.dispose()
    print('Rol limitado Neon verificado; esquema al día y auditoría solo SELECT/INSERT.', flush=True)
    print('Archivo privado .env.render preparado. Clave MFA original conservada; JWT y contraseña SQL estables.', flush=True)
    if count and data.get('ADMIN_RENDER_ALLOW_DEV_CREDENTIALS') == 'true':
        print(f'Demostración autorizada: se conservan las contraseñas de las {count} cuentas de desarrollo. MFA sin cambios.', flush=True)
    elif count:
        print(f'Antes de publicar: {count} cuentas activas conservan contraseñas públicas de desarrollo. El arranque las rechaza.', flush=True)
    else:
        print('No se encontraron contraseñas públicas de desarrollo en cuentas activas.', flush=True)
    print('Sin cambios en cuentas, datos de negocio ni .env local. Render todavía no desplegado.', flush=True)


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--allow-dev-credentials', action='store_true',
                            help='excepción explícita para demo dev, sin cambiar contraseñas')
        arguments = parser.parse_args()
        asyncio.run(prepare(allow_dev_credentials=arguments.allow_dev_credentials))
    except Exception as exc:
        state = getattr(getattr(exc, 'orig', None), 'sqlstate', None)
        diagnostic = f' SQLSTATE {state}.' if isinstance(state, str) and len(state) == 5 and state.isalnum() else ''
        raise SystemExit(f'Preparación detenida en {PHASE} ({type(exc).__name__}).{diagnostic} Revisar configuración privada; no se imprimen valores ni SQL.') from None
