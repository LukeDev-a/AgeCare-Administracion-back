"""Nombres de tablas estables y sustitución acotada de identidades de ejemplo."""
from uuid import NAMESPACE_URL, uuid5
from alembic import op
import sqlalchemy as sa

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None

# Copia fija: futuras ediciones del seed no deben cambiar esta migración.
ACCOUNTS = (
    ("Ana González", "ana.gonzalez@gmail.com"),
    ("Carlos Muñoz", "carlos.munoz@gmail.com"),
    ("María Torres", "maria.torres@gmail.com"),
    ("Pedro Silva", "pedro.silva@gmail.com"),
    ("Lucía Herrera", "lucia.herrera@gmail.com"),
    ("José Ramírez", "jose.ramirez@gmail.com"),
    ("Carmen Soto", "carmen.soto@gmail.com"),
    ("Miguel Rojas", "miguel.rojas@gmail.com"),
    ("Isabel Castro", "isabel.castro@gmail.com"),
    ("Andrés Fuentes", "andres.fuentes@gmail.com"),
    ("Elena Morales", "elena.morales@gmail.com"),
    ("Fernando Díaz", "fernando.diaz@gmail.com"),
    ("Patricia Vargas", "patricia.vargas@gmail.com"),
    ("Ricardo Molina", "ricardo.molina@gmail.com"),
    ("Verónica Reyes", "veronica.reyes@gmail.com"),
    ("Jorge Navarro", "jorge.navarro@gmail.com"),
    ("Claudia Salazar", "claudia.salazar@gmail.com"),
    ("Luis Contreras", "luis.contreras@gmail.com"),
    ("Gabriela Peña", "gabriela.pena@gmail.com"),
    ("Manuel Espinoza", "manuel.espinoza@gmail.com"),
    ("Rosa Valdés", "rosa.valdes@gmail.com"),
    ("Francisco Araya", "francisco.araya@gmail.com"),
    ("Daniela Sepúlveda", "daniela.sepulveda@gmail.com"),
    ("Héctor Paredes", "hector.paredes@gmail.com"),
    ("Teresa Aguilera", "teresa.aguilera@gmail.com"),
    ("Sergio Vidal", "sergio.vidal@gmail.com"),
    ("Marta Carrasco", "marta.carrasco@gmail.com"),
    ("Álvaro Campos", "alvaro.campos@gmail.com"),
    ("Paula Cárdenas", "paula.cardenas@gmail.com"),
    ("Roberto Escobar", "roberto.escobar@gmail.com"),
    ("Beatriz León", "beatriz.leon@gmail.com"),
    ("Eduardo Sanhueza", "eduardo.sanhueza@gmail.com"),
)
PATIENTS = (
    "Pedro Silva",
    "José Ramírez",
    "Carmen Soto",
    "Rosa Valdés",
    "Manuel Espinoza",
    "Teresa Aguilera",
    "Sergio Vidal",
)

RENAMES = (
    ('demo_app_accounts', 'app_accounts'),
    ('demo_app_patients', 'app_patients'),
    ('demo_app_memberships', 'app_memberships'),
)


def upgrade():
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    # No fusionar ni borrar grupos distintos si un destino ya existe.
    for old, new in RENAMES:
        if old in tables and new in tables:
            raise RuntimeError('Existen tablas de origen y destino; revisar antes de migrar.')
        if old not in tables and new not in tables:
            raise RuntimeError('Falta una tabla del directorio; revisar antes de migrar.')
    for old, new in RENAMES:
        if old in tables:
            op.rename_table(old, new)
    if connection.dialect.name == 'postgresql':
        # Las FK y los permisos siguen vinculados a la tabla renombrada.
        for column in ('patient_id', 'user_id'):
            op.execute(sa.text(f'ALTER INDEX IF EXISTS ix_demo_app_memberships_{column} RENAME TO ix_app_memberships_{column}'))
        constraint_names = {c['name'] for c in sa.inspect(connection).get_unique_constraints('app_memberships')}
        constraint_names |= {c['name'] for c in sa.inspect(connection).get_check_constraints('app_memberships')}
        for old, new in (('uq_demo_patient_user', 'uq_app_patient_user'), ('ck_demo_member_role', 'ck_app_member_role')):
            if old in constraint_names:
                op.execute(sa.text(f'ALTER TABLE app_memberships RENAME CONSTRAINT {old} TO {new}'))
    else:
        # SQLite conserva los nombres de constraints, sin cambiar su efecto.
        for column in ('patient_id', 'user_id'):
            indexes = {i['name'] for i in sa.inspect(connection).get_indexes('app_memberships')}
            old, new = f'ix_demo_app_memberships_{column}', f'ix_app_memberships_{column}'
            if old in indexes:
                op.drop_index(old, table_name='app_memberships')
                op.create_index(new, 'app_memberships', [column])
    accounts = sa.Table('app_accounts', sa.MetaData(), sa.Column('id', sa.Uuid(), primary_key=True), autoload_with=connection)
    patients = sa.Table('app_patients', sa.MetaData(), sa.Column('id', sa.Uuid(), primary_key=True), autoload_with=connection)
    for i, (name, email) in enumerate(ACCOUNTS, 1):
        identity = uuid5(NAMESPACE_URL, 'agecare:phase18:demo:user-' + str(i))
        legacy = sa.and_(accounts.c.id == identity, accounts.c.full_name == f'Persona de prueba {i:02}',
                         accounts.c.email == f'persona{i:02}@example.test')
        if connection.scalar(sa.select(accounts.c.id).where(legacy)) is None:
            continue
        if connection.scalar(sa.select(accounts.c.id).where(accounts.c.email == email, accounts.c.id != identity)) is not None:
            raise RuntimeError('Un correo de destino ya está ocupado; no se sobrescribirá la cuenta.')
        connection.execute(accounts.update().where(legacy).values(full_name=name, email=email))
    for i, name in enumerate(PATIENTS, 1):
        identity = uuid5(NAMESPACE_URL, 'agecare:phase18:demo:patient-' + str(i))
        connection.execute(patients.update().where(patients.c.id == identity,
            patients.c.full_name == f'Paciente de prueba {i:02}').values(full_name=name))


def downgrade():
    raise RuntimeError('Reversión manual requerida para conservar nombres, correos y referencias.')
