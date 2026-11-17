import importlib.util
from pathlib import Path
from uuid import uuid4
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app import models
from app.database import Base
from app.end_user_samples import ACCOUNTS, PATIENTS
from app.end_users_demo import demo_id

LEGACY_LINKS = [(1, 1, 'family', True), (1, 2, 'caregiver', False), (1, 3, 'doctor', False), (1, 4, 'elder', False),
    (2, 1, 'caregiver', False), (2, 5, 'family', True), (2, 6, 'elder', False),
    (3, 7, 'family', True), (3, 2, 'caregiver', False), (3, 3, 'doctor', False),
    (4, 8, 'family', True), (4, 32, 'caregiver', False), (5, 9, 'family', True), (6, 10, 'family', True)]


def migration(db):
    path = Path(__file__).parents[1] / 'alembic/versions/0020_coherent_directory_samples.py'
    spec = importlib.util.spec_from_file_location('coherence', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.op = Operations(MigrationContext.configure(db))
    return module


def legacy(db):
    Base.metadata.create_all(db)
    db.execute(models.AppAccount.__table__.insert(), [dict(id=demo_id(f'user-{i}'), full_name=name,
        email=email, is_active=i != 32) for i, (name, email) in enumerate(ACCOUNTS, 1)])
    db.execute(models.AppPatient.__table__.insert(), [dict(id=demo_id(f'patient-{i}'), full_name=name)
        for i, name in enumerate(PATIENTS[:7], 1)])
    db.execute(models.AppMembership.__table__.insert(), [dict(id=demo_id(f'link-{p}-{u}'),
        patient_id=demo_id(f'patient-{p}'), user_id=demo_id(f'user-{u}'), role=role, is_owner=owner)
        for p, u, role, owner in LEGACY_LINKS])


def test_migration_fixes_self_roles_adds_no_account_example_and_is_idempotent():
    engine = sa.create_engine('sqlite://')
    with engine.begin() as db:
        db.exec_driver_sql('PRAGMA foreign_keys=ON')
        legacy(db)
        before_accounts = db.execute(sa.select(models.AppAccount.__table__)).all()
        before_patients = db.execute(sa.select(models.AppPatient.__table__)).all()
        before_links = set(db.scalars(sa.select(models.AppMembership.id)))
        module = migration(db)
        module.upgrade(); module.upgrade()
        assert db.execute(sa.select(models.AppAccount.__table__)).all() == before_accounts
        assert db.scalar(sa.select(sa.func.count()).select_from(models.AppPatient)) == 8
        assert db.scalar(sa.select(sa.func.count()).select_from(models.AppMembership)) == 19
        assert set(db.scalars(sa.select(models.AppMembership.id))) >= before_links
        for row in before_patients:
            assert db.scalar(sa.select(models.AppPatient.full_name).where(models.AppPatient.id == row.id)) == row.full_name
        for p, u in [(1, 4), (2, 6), (3, 7), (4, 21), (5, 20), (6, 25), (7, 26)]:
            assert db.scalar(sa.select(models.AppMembership.role).where(models.AppMembership.patient_id == demo_id(f'patient-{p}'),
                models.AppMembership.user_id == demo_id(f'user-{u}'))) == 'elder'
        assert db.scalar(sa.select(models.AppPatient.full_name).where(models.AppPatient.id == demo_id('patient-8'))) == 'Elvira Paredes'
        assert not db.scalar(sa.select(models.AppAccount.id).where(models.AppAccount.full_name == 'Elvira Paredes'))
        assert db.scalar(sa.select(models.AppMembership.role).where(models.AppMembership.id == demo_id('link-8-11'))) == 'family'
        assert not db.exec_driver_sql('PRAGMA foreign_key_check').all()
        module.downgrade()
        assert db.scalar(sa.select(sa.func.count()).select_from(models.AppMembership)) == 19
    engine.dispose()


def test_migration_preserves_custom_names_roles_links_and_colliding_patient_id():
    engine = sa.create_engine('sqlite://')
    with engine.begin() as db:
        legacy(db)
        db.execute(sa.update(models.AppAccount).where(models.AppAccount.id == demo_id('user-21')).values(full_name='Nombre editado'))
        db.execute(sa.update(models.AppMembership).where(models.AppMembership.id == demo_id('link-3-7')).values(role='doctor'))
        custom_link = uuid4()
        db.execute(models.AppMembership.__table__.insert().values(id=custom_link, patient_id=demo_id('patient-5'),
            user_id=demo_id('user-20'), role='caregiver', is_owner=True))
        db.execute(models.AppPatient.__table__.insert().values(id=demo_id('patient-8'), full_name='Ficha editada'))
        migration(db).upgrade()
        assert db.scalar(sa.select(models.AppMembership.role).where(models.AppMembership.id == demo_id('link-3-7'))) == 'doctor'
        assert db.scalar(sa.select(models.AppMembership.role).where(models.AppMembership.id == custom_link)) == 'caregiver'
        assert not db.scalar(sa.select(models.AppMembership.id).where(models.AppMembership.id == demo_id('link-4-21')))
        assert not db.scalar(sa.select(models.AppMembership.id).where(models.AppMembership.id == demo_id('link-8-11')))
        assert db.scalar(sa.select(models.AppPatient.full_name).where(models.AppPatient.id == demo_id('patient-8'))) == 'Ficha editada'
    engine.dispose()


def test_new_installation_has_coherent_names_and_no_accidental_self_family():
    own_pairs = [(i, next(u for u, (name, _) in enumerate(ACCOUNTS, 1) if name == patient))
                 for i, patient in enumerate(PATIENTS[:7], 1)]
    assert own_pairs == [(1, 4), (2, 6), (3, 7), (4, 21), (5, 20), (6, 25), (7, 26)]
    assert PATIENTS[7] not in {name for name, _ in ACCOUNTS}
