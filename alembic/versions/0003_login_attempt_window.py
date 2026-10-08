"""Ventana móvil de intentos fallidos sin alterar cuentas existentes."""
from alembic import op
import sqlalchemy as sa
from app.models import PortableJSON

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('admin_users')}
    if 'failed_attempt_times' not in columns:
        op.add_column('admin_users', sa.Column('failed_attempt_times', PortableJSON, nullable=True))


def downgrade():
    with op.batch_alter_table('admin_users') as batch:
        batch.drop_column('failed_attempt_times')
