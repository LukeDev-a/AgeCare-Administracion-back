"""SQLite verifica conservación/columna; permisos y triggers requieren PostgreSQL."""
import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_0011_preserves_legacy_and_metadata_on_repeated_upgrade_and_downgrade():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/0011_audit_integrity.py'
    spec = importlib.util.spec_from_file_location('audit_integrity_migration', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE audit_log (id INTEGER PRIMARY KEY, actor_name TEXT, created_at TEXT)'))
        connection.execute(text("INSERT INTO audit_log VALUES (1, 'Actor eliminado', '2023-01-01')"))
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade(); module.upgrade(); module.downgrade()
        assert tuple(connection.execute(text('SELECT actor_name, created_at, event_metadata FROM audit_log')).one()) == ('Actor eliminado', '2023-01-01', None)
    engine.dispose()
