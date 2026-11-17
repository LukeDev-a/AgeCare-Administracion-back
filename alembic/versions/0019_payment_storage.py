"""Persistencia de suscripciones y cobros simulados, sin pasarela externa."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    json_type = sa.JSON().with_variant(JSONB(), 'postgresql')
    op.create_table('payment_subscriptions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('code', sa.String(24), nullable=False, unique=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('app_accounts.id'), nullable=False, unique=True),
        sa.Column('plan', sa.String(24), nullable=False), sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False), sa.Column('history', json_type, nullable=False),
        sa.Column('data_origin', sa.String(12), nullable=False),
        sa.CheckConstraint('price >= 0 AND version >= 1', name='ck_payment_subscription_values'),
        sa.CheckConstraint("state IN ('active','past_due','cancelled')", name='ck_payment_subscription_state'))
    op.create_table('payment_charges',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('code', sa.String(24), nullable=False, unique=True),
        sa.Column('subscription_id', sa.Uuid(), sa.ForeignKey('payment_subscriptions.id'), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False), sa.Column('state', sa.String(16), nullable=False),
        sa.Column('charged_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False), sa.Column('history', json_type, nullable=False),
        sa.Column('data_origin', sa.String(12), nullable=False),
        sa.CheckConstraint('amount > 0 AND version >= 1', name='ck_payment_charge_values'),
        sa.CheckConstraint("state IN ('approved','pending','failed','refunded')", name='ck_payment_charge_state'))
    op.create_index('ix_payment_charges_subscription_id', 'payment_charges', ['subscription_id'])


def downgrade():
    # No eliminar datos financieros de presentación automáticamente.
    pass
