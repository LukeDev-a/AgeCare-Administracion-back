"""Alta inicial no destructiva de cuatro cuentas de desarrollo.

Se ejecuta después de las migraciones. Solo actúa con habilitación explícita,
entorno dev y tabla admin_users vacía; no modifica cuentas existentes.
"""
import asyncio

from sqlalchemy import select, text

from app.account_security import cipher
from app.config import get_settings
from app.database import get_engine, get_session_factory
from app.models import AdminUser
from app.security import hash_password


# Credenciales públicas de desarrollo acordadas por el usuario; nunca producción.
DEV_ACCOUNTS = (
    ('Administrador', 'admin@wellq.co.uk', 'Admin123!', 'admin'),
    ('Soporte', 'soporte@wellq.co.uk', 'Soporte123!', 'support'),
    ('Analista', 'analista@wellq.co.uk', 'Analista123!', 'analyst'),
    ('Editora', 'editora@wellq.co.uk', 'Editora123!', 'editor'),
)


async def bootstrap(session, settings):
    """El llamador controla commit/rollback de toda la carga."""
    if not settings.bootstrap_dev_accounts:
        return 'Carga inicial de cuentas de desarrollo deshabilitada.'
    if settings.environment.strip().lower() != 'dev':
        raise RuntimeError('Las cuentas de desarrollo solo pueden crearse con ADMIN_ENVIRONMENT=dev.')
    if session.get_bind().dialect.name == 'postgresql':
        # Evitar que dos arranques simultáneos intenten inicializar la misma tabla.
        await session.execute(text('LOCK TABLE admin_users IN SHARE ROW EXCLUSIVE MODE'))
    if await session.scalar(select(AdminUser.id).limit(1)) is not None:
        return 'Ya existen cuentas: no se creó ni modificó ninguna.'
    # MFA se configurará en el primer acceso; comprobar antes su clave de cifrado.
    cipher()
    for full_name, email, password, role in DEV_ACCOUNTS:
        session.add(AdminUser(full_name=full_name, email=email,
            password_hash=hash_password(password), role=role, is_active=True,
            mfa_enabled=False, mfa_required=(role == 'admin')))
    await session.flush()
    return 'Se crearon cuatro cuentas de desarrollo sin MFA configurado. Admin debe configurarlo al entrar.'


async def main():
    settings = get_settings()
    if not settings.bootstrap_dev_accounts:
        print('Carga inicial de cuentas de desarrollo deshabilitada.')
        return
    try:
        async with get_session_factory()() as session:
            async with session.begin():
                message = await bootstrap(session, settings)
        print(message)
    finally:
        await get_engine().dispose()


if __name__ == '__main__':
    asyncio.run(main())
