"""Coherencia acotada de identidades ficticias y perfiles por vínculo."""
from uuid import NAMESPACE_URL, uuid5
from alembic import op
import sqlalchemy as sa

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None

# Copias fijas: no depender de cambios futuros del generador.
PAIRS = (
    (4, 'Rosa Valdés', 21, 'Rosa Valdés', 'rosa.valdes@gmail.com', 'elder', False),
    (5, 'Manuel Espinoza', 20, 'Manuel Espinoza', 'manuel.espinoza@gmail.com', 'elder', False),
    (6, 'Teresa Aguilera', 25, 'Teresa Aguilera', 'teresa.aguilera@gmail.com', 'elder', False),
    (7, 'Sergio Vidal', 26, 'Sergio Vidal', 'sergio.vidal@gmail.com', 'elder', True),
    (8, 'Elvira Paredes', 11, 'Elena Morales', 'elena.morales@gmail.com', 'family', True),
)


def identity(key):
    return uuid5(NAMESPACE_URL, 'agecare:phase18:demo:' + key)


def upgrade():
    connection = op.get_bind()
    meta = sa.MetaData()
    accounts = sa.Table('app_accounts', meta, sa.Column('id', sa.Uuid(), primary_key=True), autoload_with=connection)
    patients = sa.Table('app_patients', meta, sa.Column('id', sa.Uuid(), primary_key=True), autoload_with=connection)
    links = sa.Table('app_memberships', meta, sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('patient_id', sa.Uuid()), sa.Column('user_id', sa.Uuid()), autoload_with=connection)

    def same_account(number, name, email):
        return connection.scalar(sa.select(accounts.c.id).where(accounts.c.id == identity(f'user-{number}'),
            accounts.c.full_name == name, accounts.c.email == email)) is not None

    def same_patient(number, name):
        return connection.scalar(sa.select(patients.c.id).where(patients.c.id == identity(f'patient-{number}'),
            patients.c.full_name == name)) is not None

    if same_account(7, 'Carmen Soto', 'carmen.soto@gmail.com') and same_patient(3, 'Carmen Soto'):
        connection.execute(links.update().where(links.c.id == identity('link-3-7'),
            links.c.patient_id == identity('patient-3'), links.c.user_id == identity('user-7'),
            links.c.role == 'family', links.c.is_owner == sa.true()).values(role='elder'))

    # Una ficha nueva sin cuenta propia ilustra el otro caso; no renombrar ni borrar las previas.
    if same_account(11, 'Elena Morales', 'elena.morales@gmail.com'):
        occupied_id = connection.scalar(sa.select(patients.c.id).where(patients.c.id == identity('patient-8')))
        occupied_name = connection.scalar(sa.select(patients.c.id).where(patients.c.full_name == 'Elvira Paredes'))
        if occupied_id is None and occupied_name is None:
            connection.execute(patients.insert().values(id=identity('patient-8'), full_name='Elvira Paredes'))

    for p, patient_name, u, name, email, role, owner in PAIRS:
        if not same_patient(p, patient_name) or not same_account(u, name, email):
            continue
        pair_exists = connection.scalar(sa.select(links.c.id).where(
            links.c.patient_id == identity(f'patient-{p}'), links.c.user_id == identity(f'user-{u}')))
        id_exists = connection.scalar(sa.select(links.c.id).where(links.c.id == identity(f'link-{p}-{u}')))
        if pair_exists is None and id_exists is None:
            connection.execute(links.insert().values(id=identity(f'link-{p}-{u}'),
                patient_id=identity(f'patient-{p}'), user_id=identity(f'user-{u}'), role=role, is_owner=owner))


def downgrade():
    # No reintroducir roles incorrectos ni eliminar vínculos por reversión automática.
    pass
