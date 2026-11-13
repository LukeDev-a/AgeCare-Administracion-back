"""Lecturas operativas con TTL fijo; GET administrativo siempre consulta PostgreSQL."""
import asyncio
import copy
import time

from sqlalchemy import select

from app import models
from app.database import get_session_factory
from app.errors import ApiError

KEYS = ('system_texts', 'feature_flags')


class SettingsCache:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.entries = {}
        self.locks = {}
        self.generations = {}

    def invalidate(self, key):
        self.entries.pop(key, None)
        self.generations[key] = self.generations.get(key, 0) + 1

    async def get(self, db, key):
        entry = self.entries.get(key)
        if entry is not None and self.clock() < entry[0]:
            return copy.deepcopy(entry[1])
        async with self.locks.setdefault(key, asyncio.Lock()):
            entry = self.entries.get(key)
            if entry is not None and self.clock() < entry[0]:
                return copy.deepcopy(entry[1])
            generation = self.generations.get(key, 0)
            try:
                row = await db.scalar(select(models.SystemSetting).where(models.SystemSetting.key == key)
                                      .execution_options(populate_existing=True))
                result = {'version': row.version, 'value': copy.deepcopy(row.value)} if row else None
            except Exception:
                raise ApiError(503, 'SETTINGS_UNAVAILABLE', 'No se pudo actualizar la configuración. Intenta nuevamente.') from None
            previous = self.entries.get(key)
            if previous and result and previous[1] and result['version'] < previous[1]['version']:
                raise ApiError(503, 'SETTINGS_UNAVAILABLE', 'La configuración disponible no está actualizada.')
            if generation == self.generations.get(key, 0):
                self.entries[key] = (self.clock() + 60, copy.deepcopy(result))
            return result


cache = SettingsCache()


async def feature_enabled(db, key):
    if key not in ('news_collection_enabled', 'news_adaptation_enabled'):
        raise ValueError('Función no configurada')
    setting = await cache.get(db, 'feature_flags')
    # Mantener las funciones existentes mientras una instalación anterior migra.
    value = setting['value'].get(key, True) if setting else True
    if not isinstance(value, bool):
        raise ApiError(503, 'SETTINGS_UNAVAILABLE', 'La disponibilidad de la función no está configurada correctamente.')
    return value


async def require_feature(db, key):
    if not await feature_enabled(db, key):
        raise ApiError(409, 'FEATURE_DISABLED', 'Esta función está desactivada en la configuración del sistema.')


async def notice(db):
    setting = await cache.get(db, 'system_texts')
    value = setting['value'] if setting else {}
    enabled = value.get('notice_enabled', False)
    return {'version': setting['version'] if setting else None, 'enabled': enabled,
            'title': value.get('notice_title', '') if enabled else '',
            'body': value.get('notice_body', '') if enabled else ''}


async def refresh_worker():
    while True:
        for key in KEYS:
            try:
                async with get_session_factory()() as db:
                    await cache.get(db, key)
            except Exception:
                # No servir una copia vencida; el siguiente ciclo vuelve a intentar.
                pass
        await asyncio.sleep(5)
