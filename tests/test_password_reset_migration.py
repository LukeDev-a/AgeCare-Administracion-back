import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_password_reset_migration_preserves_accounts_and_supports_new_installations(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/0014_password_reset.py'
    spec = importlib.util.spec_from_file_location('password_reset_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE admin_users (id CHAR(32) PRIMARY KEY, email VARCHAR(254))'))
        connection.execute(text("INSERT INTO admin_users VALUES ('00000000000000000000000000000001', 'preserved@example.org')"))
        monkeypatch.setattr(module, 'op', Operations(MigrationContext.configure(connection)))
        module.upgrade()
        module.upgrade()
        assert connection.scalar(text('SELECT email FROM admin_users')) == 'preserved@example.org'
        assert connection.scalar(text('SELECT count(*) FROM admin_password_resets')) == 0
        assert any(index['unique'] for index in inspect(connection).get_indexes('admin_password_resets'))
    engine.dispose()
