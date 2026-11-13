"""Migración, TTL entre procesos y concurrencia sobre PostgreSQL temporal local."""
import asyncio
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from starlette.requests import Request

from app import database, models
from app.errors import ApiError
from app.routers.system import put_setting
from app.runtime_settings import SettingsCache
from app.schemas.system import SettingPutIn
from app.security import hash_password


async def main():
    engine = database.get_engine()
    assert engine.url.database == 'agecare_runtime_settings_check' and engine.url.host == '127.0.0.1'
    spec = importlib.util.spec_from_file_location('runtime_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/0016_runtime_settings.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    factory = database.get_session_factory()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(models.Base.metadata.create_all)
        async with factory() as db:
            actor = models.AdminUser(full_name='Administrador temporal', email='test@example.org', role='admin', password_hash=hash_password('Temporal123!'))
            db.add(actor)
            db.add(models.SystemSetting(key='system_texts', value={'notice_enabled': False, 'notice_title': 'Conservar', 'notice_body': ''},
                value_schema=module.NOTICE_SCHEMA, description='Conservar', version=9))
            await db.commit(); actor_id = actor.id
        def migrate(bind):
            module.op = Operations(MigrationContext.configure(bind)); module.upgrade(); module.upgrade()
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
        clock = [0]
        a, b = SettingsCache(lambda: clock[0]), SettingsCache(lambda: clock[0])
        async with factory() as db:
            assert (await a.get(db, 'system_texts'))['version'] == (await b.get(db, 'system_texts'))['version'] == 9
            assert (await db.get(models.SystemSetting, 'feature_flags')).value == {
                'news_collection_enabled': True, 'news_adaptation_enabled': True}
        async def save(title, version):
            async with factory() as db:
                actor = await db.get(models.AdminUser, actor_id)
                req = Request({'type': 'http', 'method': 'PUT', 'headers': [], 'client': ('127.0.0.1', 1)})
                req.state.actor = actor
                try:
                    await put_setting('system_texts', SettingPutIn(value={'notice_enabled': True,
                        'notice_title': title, 'notice_body': 'Aviso temporal'}, version=version,
                        change_note='Prueba de propagación'), req, db, actor)
                    return 200
                except ApiError as error:
                    await db.rollback(); return error.status_code
        assert await save('Actualizado', 9) == 200
        async with factory() as db:
            clock[0] = 59
            assert (await a.get(db, 'system_texts'))['version'] == 9
            clock[0] = 60
            assert (await a.get(db, 'system_texts'))['version'] == (await b.get(db, 'system_texts'))['version'] == 10
        assert sorted(await asyncio.gather(save('Primero', 10), save('Segundo', 10))) == [200, 409]
        async with factory() as db:
            assert (await db.get(models.SystemSetting, 'system_texts')).version == 11
            assert len((await db.scalars(select(models.AuditLog).where(models.AuditLog.action == 'settings.update'))).all()) == 2
        print('PostgreSQL temporal OK: migración conserva valores/versiones; dos cachés renuevan al TTL; edición concurrente no sobrescribe.')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
