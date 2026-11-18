"""Observaciones operativas reales, separadas de los ejemplos previos."""
from alembic import op
import sqlalchemy as sa

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ops_observations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('component_key', sa.String(30), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('duration_ms', sa.Float(), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('source', sa.String(24), nullable=False),
        sa.Column('failure_kind', sa.String(20), nullable=True),
        sa.CheckConstraint("component_key IN ('api_core', 'auth', 'database')", name='ck_ops_observation_component'),
        sa.CheckConstraint('duration_ms >= 0', name='ck_ops_observation_duration'),
        sa.CheckConstraint("source IN ('http_requests', 'database_probe')", name='ck_ops_observation_source'))
    op.create_index('ix_ops_observations_component_key', 'ops_observations', ['component_key'])
    op.create_index('ix_ops_observations_observed_at', 'ops_observations', ['observed_at'])
    op.create_index('ix_ops_observations_component_time', 'ops_observations', ['component_key', 'observed_at', 'id'])


def downgrade():
    op.drop_table('ops_observations')
