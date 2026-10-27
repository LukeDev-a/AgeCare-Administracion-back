"""Origen de agregados y fuentes de cohortes; sin inventar observaciones reales."""
from alembic import op
import sqlalchemy as sa
from app.analytics_models import (AnalyticsAccount, AnalyticsActivity, AnalyticsPayment,
                                  AnalyticsSource, AnalyticsCohortSnapshot)
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    for name in ('metrics_daily_users', 'metrics_hourly_users', 'metrics_plan_snapshot'):
        if 'data_origin' not in {column['name'] for column in sa.inspect(bind).get_columns(name)}:
            op.add_column(name, sa.Column('data_origin', sa.String(12), nullable=False, server_default='unknown'))
    for model in (AnalyticsAccount, AnalyticsActivity, AnalyticsPayment, AnalyticsSource, AnalyticsCohortSnapshot):
        model.__table__.create(bind, checkfirst=True)
    if 'bucket_minutes' not in {column['name'] for column in sa.inspect(bind).get_columns('metrics_hourly_users')}:
        op.add_column('metrics_hourly_users', sa.Column('bucket_minutes', sa.Integer(), nullable=False, server_default='180'))
        with op.batch_alter_table('metrics_hourly_users') as batch:
            batch.alter_column('bucket_minutes', server_default='60')

def downgrade():
    # Conservar observaciones para no perder datos de una futura integración.
    pass
