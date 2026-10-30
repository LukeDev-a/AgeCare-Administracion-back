import importlib.util
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_0012_creates_only_demo_tables_and_preserves_legacy_and_changes():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/0012_demo_end_users.py'
    spec = importlib.util.spec_from_file_location('demo_users_migration', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE admin_users (id INTEGER PRIMARY KEY, full_name TEXT)'))
        connection.execute(text("INSERT INTO admin_users VALUES (1, 'Conservar personal')"))
        connection.execute(text('CREATE TABLE audit_log (id INTEGER PRIMARY KEY, action TEXT)'))
        connection.execute(text("INSERT INTO audit_log VALUES (1, 'staff.create')"))
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        connection.execute(text("INSERT INTO demo_app_accounts (id, full_name, email, is_active, deactivation_reason) VALUES ('00000000000000000000000000000001', 'Ejemplo conservado', 'ejemplo@example.test', false, 'Motivo conservado')"))
        module.upgrade(); module.downgrade()
        assert connection.scalar(text('SELECT full_name FROM admin_users')) == 'Conservar personal'
        assert connection.scalar(text('SELECT count(*) FROM audit_log')) == 1
        assert tuple(connection.execute(text('SELECT is_active, deactivation_reason FROM demo_app_accounts')).one()) == (0, 'Motivo conservado')
        tables = inspect(connection).get_table_names()
        assert set(tables) == {'admin_users', 'audit_log', 'demo_app_accounts', 'demo_app_patients', 'demo_app_memberships'}
    engine.dispose()
