"""Invitaciones, cola de correo y MFA. Compatible con instalaciones nuevas y existentes."""
from alembic import op
import sqlalchemy as sa
from app import models

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {c['name'] for c in sa.inspect(bind).get_columns('admin_users')}
    additions = [
        sa.Column('mfa_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('mfa_last_step', sa.Integer(), nullable=True),
        sa.Column('auth_version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('recovery_hashes', models.PortableJSON, nullable=True),
        sa.Column('invitation_cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('invitation_delivery_status', sa.String(20), nullable=True),
    ]
    with op.batch_alter_table('admin_users') as batch:
        for column in additions:
            if column.name not in columns: batch.add_column(column)
        if bind.dialect.name == 'postgresql':
            batch.alter_column('mfa_secret', existing_type=sa.String(64), type_=sa.String(512), existing_nullable=True)
    if 'mfa_verified' not in {c['name'] for c in sa.inspect(bind).get_columns('admin_sessions')}:
        op.add_column('admin_sessions', sa.Column('mfa_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    if 'auth_version' not in {c['name'] for c in sa.inspect(bind).get_columns('admin_sessions')}:
        op.add_column('admin_sessions', sa.Column('auth_version', sa.Integer(), nullable=False, server_default='0'))
    for table in [models.AdminInvitation.__table__, models.InvitationEmail.__table__, models.MfaEnrollment.__table__]:
        table.create(bind, checkfirst=True)


def downgrade():
    for table in [models.MfaEnrollment.__table__, models.InvitationEmail.__table__, models.AdminInvitation.__table__]:
        table.drop(op.get_bind(), checkfirst=True)
    op.drop_column('admin_sessions', 'mfa_verified')
    op.drop_column('admin_sessions', 'auth_version')
    with op.batch_alter_table('admin_users') as batch:
        for name in ['mfa_required', 'mfa_last_step', 'auth_version', 'recovery_hashes', 'invitation_cancelled_at', 'invitation_delivery_status']:
            batch.drop_column(name)
    # Mantiene el ancho de mfa_secret para no truncar secretos cifrados existentes.
