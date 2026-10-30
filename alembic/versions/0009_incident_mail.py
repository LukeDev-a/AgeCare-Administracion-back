"""Avisos de incidentes persistentes y opcionales, sin destinatarios por defecto."""
from alembic import op
import sqlalchemy as sa
from app.models import IncidentEmail

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if 'notification_status' not in {column['name'] for column in sa.inspect(bind).get_columns('ops_incidents')}:
        op.add_column('ops_incidents', sa.Column('notification_status', sa.String(20), nullable=False, server_default='not_configured'))
    IncidentEmail.__table__.create(bind, checkfirst=True)

def downgrade():
    # Conservar avisos y estado de entrega; no borrar información al retroceder.
    pass
