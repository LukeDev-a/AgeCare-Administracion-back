"""Procedencia de monitoreo sin convertir el legado en mediciones reales."""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for table in ('ops_component_state', 'ops_latency_window', 'ops_critical_process_state'):
        names = {column['name'] for column in sa.inspect(bind).get_columns(table)}
        if 'data_origin' not in names:
            op.add_column(table, sa.Column('data_origin', sa.String(12), nullable=False, server_default='unknown'))
        if table == 'ops_critical_process_state' and 'execution_kind' not in names:
            op.add_column(table, sa.Column('execution_kind', sa.String(12), nullable=False, server_default='unknown'))


def downgrade():
    # No eliminar la procedencia registrada al retroceder la revisión.
    pass
