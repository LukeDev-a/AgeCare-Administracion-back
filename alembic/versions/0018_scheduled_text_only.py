"""Autorización explícita de programación con audio opcional."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('content_items')}
    if 'schedule_audio_exception' not in columns:
        op.add_column('content_items', sa.Column('schedule_audio_exception',
            sa.JSON().with_variant(JSONB(), 'postgresql'), nullable=True))


def downgrade():
    # La autorización/fecha no se borra mediante downgrade automático.
    pass
