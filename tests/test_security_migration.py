import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.database import Base


@pytest.mark.parametrize('existing', [False, True])
def test_invitation_migration_preserves_existing_accounts(existing):
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        if existing:
            connection.execute(sa.text('CREATE TABLE admin_users (id CHAR(32) PRIMARY KEY, full_name VARCHAR(120), email VARCHAR(254), role VARCHAR(20), is_active BOOLEAN, mfa_secret VARCHAR(64))'))
            connection.execute(sa.text('CREATE TABLE admin_sessions (id CHAR(32) PRIMARY KEY, admin_id CHAR(32))'))
            connection.execute(sa.text("INSERT INTO admin_users(id, full_name, email, role, is_active, mfa_secret) VALUES ('123', 'Cuenta existente', 'existente@wellq.co.uk', 'admin', 1, 'BASE32')"))
        else:
            Base.metadata.create_all(connection)
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/0002_invitations_mfa.py'
        spec = importlib.util.spec_from_file_location('security_migration', path)
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = sa.inspect(connection)
        assert {'admin_invitations', 'invitation_emails', 'mfa_enrollments'}.issubset(inspector.get_table_names())
        assert {'mfa_required', 'auth_version', 'recovery_hashes'}.issubset({column['name'] for column in inspector.get_columns('admin_users')})
        if existing:
            row = connection.execute(sa.text("SELECT full_name, mfa_secret, auth_version FROM admin_users WHERE id='123'")).one()
            assert tuple(row) == ('Cuenta existente', 'BASE32', 0)
        migration.upgrade()  # La revisión también funciona tras el create_all de 0001.
    engine.dispose()


@pytest.mark.parametrize('existing', [False, True])
def test_login_window_migration(existing):
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        if existing:
            connection.execute(sa.text('CREATE TABLE admin_users (id CHAR(32) PRIMARY KEY, full_name VARCHAR(120))'))
            connection.execute(sa.text("INSERT INTO admin_users VALUES ('123', 'Cuenta conservada')"))
        else:
            Base.metadata.create_all(connection)
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/0003_login_attempt_window.py'
        spec = importlib.util.spec_from_file_location('login_window_migration', path)
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade(); migration.upgrade()
        assert 'failed_attempt_times' in {c['name'] for c in sa.inspect(connection).get_columns('admin_users')}
        if existing:
            assert connection.execute(sa.text('SELECT full_name FROM admin_users')).scalar() == 'Cuenta conservada'
    engine.dispose()
