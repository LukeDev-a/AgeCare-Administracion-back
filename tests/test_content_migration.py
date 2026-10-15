import importlib.util
from pathlib import Path
import sqlalchemy as sa
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.database import Base


@pytest.mark.parametrize('existing', [True, False])
def test_content_migration_preserves_legacy_and_rejects_fake_audio(existing):
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        if existing:
            connection.execute(sa.text('CREATE TABLE content_items (id CHAR(32) PRIMARY KEY, title TEXT, body TEXT, status TEXT, tts_ready BOOLEAN)'))
            connection.execute(sa.text("INSERT INTO content_items VALUES ('test', 'Conservado', 'Texto', 'published', true)"))
        else:
            Base.metadata.create_all(connection)
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/0004_content_pipeline.py'
        spec = importlib.util.spec_from_file_location('content_migration', path)
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade(); migration.upgrade()
        assert {'news_candidates', 'content_jobs', 'content_control'} <= set(sa.inspect(connection).get_table_names())
        if existing:
            row = connection.execute(sa.text('SELECT title, status, tts_ready, text_version FROM content_items')).one()
            assert tuple(row) == ('Conservado', 'published', 0, 1)
    engine.dispose()
