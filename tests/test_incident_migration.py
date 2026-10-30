"""DDL real de 0009 sobre SQLite aislado; PostgreSQL se comprueba por separado."""
import importlib.util
from pathlib import Path
from sqlalchemy import create_engine, text, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations

def test_0009_preserves_legacy_incident_and_is_idempotent(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/0009_incident_mail.py'
    spec = importlib.util.spec_from_file_location('incident_mail_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE ops_incidents (id CHAR(32) PRIMARY KEY, title VARCHAR(160) NOT NULL)'))
        conn.execute(text("INSERT INTO ops_incidents VALUES ('00000000000000000000000000000009', 'Incidente conservado')"))
        monkeypatch.setattr(module, 'op', Operations(MigrationContext.configure(conn)))
        module.upgrade()
        module.upgrade()
        row = conn.execute(text('SELECT title, notification_status FROM ops_incidents')).one()
        assert tuple(row) == ('Incidente conservado', 'not_configured')
        assert 'ops_incident_emails' in inspect(conn).get_table_names()
        assert conn.scalar(text('SELECT count(*) FROM ops_incident_emails')) == 0
    engine.dispose()
