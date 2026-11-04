"""Solo PostgreSQL temporal content_test en localhost:55441; sin seed/proveedores reales."""
import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update({
    'ADMIN_DATABASE_URL': 'postgresql+asyncpg://content_test:content_test@127.0.0.1:55441/content_test',
    'ADMIN_JWT_SECRET': 'content-isolated-test-key-at-least-32-bytes',
    'ADMIN_ALLOWS_ORIGINS': 'http://localhost:5173',
    'ADMIN_MAIL_WORKER_ENABLED': 'false', 'ADMIN_CONTENT_WORKER_ENABLED': 'false',
    'ADMIN_GEMINI_API_KEY': 'test-only-never-sent', 'ADMIN_GEMINI_FREE_TIER_CONFIRMED': 'true',
})
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app import database, models, content_pipeline as pipeline
from app.config import get_settings


async def main():
    engine = database.get_engine()
    assert engine.url.database == 'content_test' and engine.url.port == 55441 and engine.url.host == '127.0.0.1'
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/0004_content_pipeline.py'
    spec = importlib.util.spec_from_file_location('migration_content_pg', path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    def upgrade(connection):
        old = sa.MetaData()
        table = models.ContentItem.__table__.to_metadata(old)
        for field in migration.FIELDS:
            table._columns.remove(table.c[field.name])
        old.create_all(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        database.Base.metadata.create_all(connection)
    async with engine.begin() as connection:
        await connection.run_sync(upgrade)
    async with database.get_session_factory()() as db:
        quota = await pipeline.control(db, 'quota_tts'); quota.data = {}; await db.commit()
    # Durable cuota serializa reservas de procesos concurrentes.
    reservations = await asyncio.gather(*[pipeline.reserve_quota('tts') for _ in range(8)])
    assert sum(result is None for result in reservations) == 3  # RPM=3
    async with database.get_session_factory()() as db:
        quota = await pipeline.control(db, 'quota_tts'); quota.data = {}; await db.commit()
    calls = []
    async def fake_audio(text):
        calls.append(text); await asyncio.sleep(0.05); return b'RIFF-isolated-test'
    pipeline.narrate = fake_audio
    with TemporaryDirectory() as directory:
        get_settings().content_audio_dir = directory
        async with database.get_session_factory()() as db:
            item = models.ContentItem(type='news', title='Texto aprobado', body='Contenido de prueba.', tags=[],
                text_version=1, approved_version=1, reviewed_by=uuid4(), reviewed_by_name='Prueba')
            db.add(item); await db.flush()
            for _ in range(2): db.add(models.ContentJob(kind='tts', target_id=item.id, version=1))
            item_id = item.id; await db.commit()
        await asyncio.gather(pipeline.process_one(), pipeline.process_one())
        assert len(calls) == 1
        async with database.get_session_factory()() as db:
            item = await db.get(models.ContentItem, item_id)
            assert item.tts_ready and item.audio_version == item.text_version
    await engine.dispose()
    print('PostgreSQL: migración 0004 desde tabla anterior, cuotas concurrentes y dos workers/sin audio duplicado aprobados.')


if __name__ == '__main__':
    asyncio.run(main())
