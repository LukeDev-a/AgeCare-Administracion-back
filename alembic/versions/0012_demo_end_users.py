"""Directorio de demostración separado de identidades/sesiones móviles reales."""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    if 'demo_app_accounts' not in tables:
        op.create_table('demo_app_accounts',
            sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('full_name', sa.String(120), nullable=False),
            sa.Column('email', sa.String(254), nullable=False, unique=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('deactivated_at', sa.DateTime(timezone=True)),
            sa.Column('deactivated_by', sa.Uuid()),
            sa.Column('deactivation_reason', sa.String(500)),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    if 'demo_app_patients' not in tables:
        op.create_table('demo_app_patients',
            sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('full_name', sa.String(120), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    if 'demo_app_memberships' not in tables:
        op.create_table('demo_app_memberships',
            sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('patient_id', sa.Uuid(), sa.ForeignKey('demo_app_patients.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('user_id', sa.Uuid(), sa.ForeignKey('demo_app_accounts.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('role', sa.String(20), nullable=False),
            sa.Column('is_owner', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint('patient_id', 'user_id', name='uq_demo_patient_user'),
            sa.CheckConstraint("role IN ('family', 'caregiver', 'elder', 'doctor')", name='ck_demo_member_role'))
        op.create_index('ix_demo_app_memberships_patient_id', 'demo_app_memberships', ['patient_id'])
        op.create_index('ix_demo_app_memberships_user_id', 'demo_app_memberships', ['user_id'])


def downgrade():
    pass  # No borrar directorio ni trazabilidad mediante downgrade automático.
