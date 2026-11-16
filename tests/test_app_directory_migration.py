"""0017 conserva datos y vínculos; solo sustituye los ejemplos originales."""
import importlib.util
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5, uuid4
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def load(filename):
    spec = importlib.util.spec_from_file_location(filename[:4], Path(__file__).resolve().parents[1] / 'alembic/versions' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identity(key):
    return uuid5(NAMESPACE_URL, 'agecare:phase18:demo:' + key)


def run(module, connection):
    module.op = Operations(MigrationContext.configure(connection))
    module.upgrade()


def test_rename_preserves_ids_states_links_custom_people_and_is_idempotent():
    engine = sa.create_engine('sqlite://')
    with engine.begin() as db:
        db.exec_driver_sql('PRAGMA foreign_keys=ON')
        run(load('0012_demo_end_users.py'), db)
        accounts = sa.Table('demo_app_accounts', sa.MetaData(), sa.Column('id', sa.Uuid(), primary_key=True), autoload_with=db)
        patients = sa.Table('demo_app_patients', sa.MetaData(), sa.Column('id', sa.Uuid(), primary_key=True), autoload_with=db)
        memberships = sa.Table('demo_app_memberships', sa.MetaData(), sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('patient_id', sa.Uuid()), sa.Column('user_id', sa.Uuid()), autoload_with=db)
        for i in range(1, 33):
            db.execute(accounts.insert().values(id=identity(f'user-{i}'), full_name=f'Persona de prueba {i:02}',
                email=f'persona{i:02}@example.test', is_active=i != 32,
                deactivation_reason='Conservar motivo' if i == 32 else None))
        for i in range(1, 8):
            db.execute(patients.insert().values(id=identity(f'patient-{i}'), full_name=f'Paciente de prueba {i:02}'))
        # Una edición previa y una persona ajena al seed se deben conservar.
        db.execute(accounts.update().where(accounts.c.id == identity('user-2')).values(full_name='Nombre editado'))
        extra = uuid4()
        db.execute(accounts.insert().values(id=extra, full_name='Persona existente', email='existente@example.test', is_active=True))
        link = uuid4()
        db.execute(memberships.insert().values(id=link, patient_id=identity('patient-1'), user_id=identity('user-1'), role='family', is_owner=True))
        migration = load('0017_app_directory_names.py')
        run(migration, db)
        run(migration, db)
        tables = set(sa.inspect(db).get_table_names())
        assert tables == {'app_accounts', 'app_patients', 'app_memberships'}
        assert db.scalar(sa.text('SELECT count(*) FROM app_accounts')) == 33
        assert db.scalar(sa.text('SELECT count(*) FROM app_patients')) == 7
        row = db.execute(sa.text('SELECT full_name,email FROM app_accounts WHERE id=:id'), {'id': identity('user-1').hex}).one()
        assert tuple(row) == ('Ana González', 'ana.gonzalez@gmail.com')
        assert db.scalar(sa.text('SELECT full_name FROM app_accounts WHERE id=:id'), {'id': identity('user-2').hex}) == 'Nombre editado'
        assert tuple(db.execute(sa.text('SELECT is_active,deactivation_reason FROM app_accounts WHERE id=:id'),
            {'id': identity('user-32').hex}).one()) == (0, 'Conservar motivo')
        assert db.scalar(sa.text('SELECT full_name FROM app_patients WHERE id=:id'), {'id': identity('patient-1').hex}) == 'Pedro Silva'
        assert db.scalar(sa.text('SELECT id FROM app_memberships')) == link.hex
        assert not db.exec_driver_sql('PRAGMA foreign_key_check').all()
        assert {fk['referred_table'] for fk in sa.inspect(db).get_foreign_keys('app_memberships')} == {'app_accounts', 'app_patients'}
    engine.dispose()


def test_conflicting_tables_are_rejected_instead_of_merging():
    engine = sa.create_engine('sqlite://')
    with engine.begin() as db:
        run(load('0012_demo_end_users.py'), db)
        db.exec_driver_sql('CREATE TABLE app_accounts (id INTEGER PRIMARY KEY)')
        with pytest.raises(RuntimeError, match='origen y destino'):
            run(load('0017_app_directory_names.py'), db)
        assert 'demo_app_accounts' in sa.inspect(db).get_table_names()
    engine.dispose()


def test_seed_names_match_frozen_migration_and_emails_are_unique():
    from app.end_user_samples import ACCOUNTS, PATIENTS
    migration = load('0017_app_directory_names.py')
    assert migration.ACCOUNTS == ACCOUNTS and migration.PATIENTS == PATIENTS
    assert len(ACCOUNTS) == len({email for _, email in ACCOUNTS}) == 32
    assert len(PATIENTS) == 7
    assert all(email.endswith('@gmail.com') and ' ' in name for name, email in ACCOUNTS)
