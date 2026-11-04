"""Alta operativa explícita de cuentas sin correo. No modifica cuentas existentes.

Sin --apply solo comprueba. Con --apply crea cuentas y auditoría atómicamente,
con MFA obligatorio, y guarda cada contraseña inicial en .env.* privado.
Rol editor por defecto; --role admin requiere solicitud explícita del operador.
No suplanta una sesión admin: el actor de auditoría se identifica como operativo.
"""
import argparse
import asyncio
from io import StringIO
from pathlib import Path
import secrets

from dotenv import dotenv_values
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database_urls import database_connect_args, normalize_database_url
from app.models import AdminUser, AuditLog
from app.schemas.auth import AdminCreateIn
from app.security import hash_password
from scripts.copy_to_neon import ROOT


def render_value(name):
    with (ROOT / '.env.render').open(encoding='utf-8') as stream:
        for line in stream:
            if line.partition('=')[0] == name:
                return dotenv_values(stream=StringIO(line), interpolate=False).get(name)
    raise ValueError('Falta una variable en el perfil privado Render.')


def validate_accounts(records, domains, role='editor', require_mfa=True):
    accounts = [AdminCreateIn(full_name=name, email=email.lower().strip(), role=role,
                              require_mfa=require_mfa) for name, email in records]
    emails = [str(account.email).lower() for account in accounts]
    if len(set(emails)) != len(emails) or not accounts:
        raise ValueError('Los correos deben ser distintos.')
    if any(email.split('@')[1] not in domains for email in emails):
        raise ValueError('Un dominio no está autorizado por el perfil Render.')
    return accounts


async def existing_accounts(session, accounts):
    return (await session.scalars(select(AdminUser.email).where(
        func.lower(AdminUser.email).in_([str(a.email).lower() for a in accounts])))).all()


async def create_accounts(factory, accounts, output_dir):
    created_files = []
    committed = False
    result = []
    try:
        async with factory() as session:
            async with session.begin():
                if await existing_accounts(session, accounts):
                    raise ValueError('Un correo ya existe; no se creó ni modificó ninguna cuenta.')
                for account in accounts:
                    password = secrets.token_urlsafe(24)
                    # Nombre aleatorio evita reemplazar credenciales previas.
                    path = output_dir / ('.env.editor-' + secrets.token_hex(6))
                    with path.open('x', encoding='utf-8') as stream:
                        created_files.append(path)
                        stream.write('# Credenciales privadas de una sola cuenta. No subir ni pegar en el chat.\n')
                        stream.write('ACCOUNT_NAME=' + account.full_name + '\n')
                        stream.write('ACCOUNT_EMAIL=' + str(account.email).lower() + '\n')
                        stream.write('INITIAL_PASSWORD=' + password + '\n')
                        stream.write('CONSOLE_URL=https://age-care-administracion-front.vercel.app\nMFA_REQUIRED=' + str(account.require_mfa).lower() + '\n')
                    user = AdminUser(full_name=account.full_name, email=str(account.email).lower(),
                                     role=account.role, password_hash=hash_password(password),
                                     is_active=True, mfa_required=account.require_mfa, mfa_enabled=False)
                    session.add(user)
                    await session.flush()
                    session.add(AuditLog(action='staff.create', entity_type='admin_user', entity_id=user.id,
                        actor_id=None, actor_name='Alta operativa autorizada', actor_role=None,
                        ip=None, user_agent='AgeCare: operación local sin sesión HTTP',
                        after={'full_name': user.full_name, 'email': user.email, 'role': account.role,
                               'is_active': True, 'mfa_required': account.require_mfa},
                        event_metadata={'outcome': 'success', 'reason': 'Alta de pruebas sin obligación MFA individual' if not account.require_mfa else 'Alta operativa sin invitación por correo'}))
                    result.append((user.email, path))
            committed = True
        return result
    finally:
        if not committed:
            # Solo archivos recién creados por esta operación, nunca previos.
            for path in created_files:
                path.unlink(missing_ok=True)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', action='append', nargs=2, metavar=('NAME', 'EMAIL'), required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--role', choices=['editor', 'admin'], default='editor')
    parser.add_argument('--without-mfa-for-testing', action='store_true', help='No obliga MFA individual; la excepción de rol requiere configuración dev explícita por UUID.')
    arguments = parser.parse_args()
    accounts = validate_accounts(arguments.account,
        {d.strip().lower() for d in render_value('ADMIN_ALLOWED_EMAIL_DOMAINS').split(',')}, role=arguments.role,
        require_mfa=not arguments.without_mfa_for_testing)
    value = normalize_database_url(render_value('ADMIN_DATABASE_URL'))
    url = make_url(value)
    if not (url.host or '').endswith('.neon.tech') or not (url.username or '').startswith('agecare_api_'):
        raise ValueError('Esta operación requiere el acceso limitado Neon del perfil Render.')
    engine = create_async_engine(value, hide_parameters=True, connect_args=database_connect_args(value))
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            if await existing_accounts(session, accounts):
                raise ValueError('Un correo ya existe; no se creó ni modificó ninguna cuenta.')
        if not arguments.apply:
            print(f'Comprobación correcta: {len(accounts)} correos disponibles; rol {arguments.role}. Sin cambios.')
            return
        results = await create_accounts(factory, accounts, ROOT)
        async with factory() as session:
            users = (await session.scalars(select(AdminUser).where(
                AdminUser.email.in_([email for email, _ in results])))).all()
            if len(users) != len(accounts) or not all(u.role == arguments.role and u.is_active and
                    u.mfa_required == (not arguments.without_mfa_for_testing) and not u.mfa_enabled and u.password_hash for u in users):
                raise ValueError('Revisar la verificación posterior; no repetir ni restablecer contraseñas.')
        for email, path in results:
            print(f'Cuenta creada y verificada: {email}. Archivo privado: {path.name}')
        if arguments.without_mfa_for_testing:
            print('Excepción dev por UUID: ' + ','.join(str(user.id) for user in users))
            print('Requiere desplegar y configurar ADMIN_MFA_TEST_EXEMPT_ACCOUNT_IDS; no desactiva MFA de otras cuentas.')
        print('Sin correos enviados ni cambios en cuentas anteriores. Auditoría operativa registrada.')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except ValueError as exc:
        # Los errores de validadores externos podrían incluir entradas privadas.
        message = str(exc) if type(exc) is ValueError else 'Revisar nombre, correo y formato de alta.'
        raise SystemExit(message) from None
    except Exception:
        raise SystemExit('Alta detenida. Revisar conexión, duplicados y archivos privados sin imprimir credenciales ni SQL.') from None
