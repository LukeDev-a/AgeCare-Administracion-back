"""Sesiones compartidas de actividad y adopción; no modifica pagos ni directorio."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('analytics_usage_accounts',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('profile', sa.String(12), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('data_origin', sa.String(12), nullable=False),
        sa.CheckConstraint("profile IN ('family','caregiver','elder','doctor')", name='ck_usage_profile'))
    op.create_index('ix_analytics_usage_accounts_created_at', 'analytics_usage_accounts', ['created_at'])
    op.create_table('analytics_usage_sessions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('account_id', sa.Uuid(), sa.ForeignKey('analytics_usage_accounts.id'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('feature_keys', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
        sa.Column('data_origin', sa.String(12), nullable=False),
        sa.CheckConstraint('duration_seconds > 0', name='ck_usage_duration'))
    op.create_index('ix_analytics_usage_sessions_account_id', 'analytics_usage_sessions', ['account_id'])
    op.create_index('ix_analytics_usage_sessions_started_at', 'analytics_usage_sessions', ['started_at'])
    op.create_index('ix_usage_sessions_time_account', 'analytics_usage_sessions', ['started_at','account_id'])


def downgrade():
    op.drop_table('analytics_usage_sessions')
    op.drop_table('analytics_usage_accounts')
