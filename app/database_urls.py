"""Compatibilidad de conexión asyncpg; Neon siempre con TLS verificado."""
import ssl
from sqlalchemy.engine import make_url


def normalize_database_url(value: str) -> str:
    try:
        url = make_url(value)
        if url.drivername in ('postgres', 'postgresql'):
            url = url.set(drivername='postgresql+asyncpg')
        if url.drivername == 'postgresql+asyncpg' and (url.host or '').endswith('.neon.tech'):
            # Los parámetros libpq del panel no son argumentos de asyncpg.
            query = dict(url.query)
            query.pop('sslmode', None)
            query.pop('channel_binding', None)
            query['ssl'] = 'verify-full'
            url = url.set(query=query)
        return url.render_as_string(hide_password=False)
    except Exception:
        raise ValueError('Formato de conexión de base de datos no válido.') from None


def database_connect_args(value):
    url = make_url(value)
    if url.drivername == 'postgresql+asyncpg' and (url.host or '').endswith('.neon.tech'):
        # asyncpg verify-full como texto puede buscar ~/.postgresql/root.crt.
        # Usar explícitamente las CA del sistema, con hostname y cadena verificados.
        return {'ssl': ssl.create_default_context()}
    return {}
