"""Recuperación MFA con aprobación y cola cifrada de correo."""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('admin_mfa_recoveries'):
        op.create_table('admin_mfa_recoveries',
            sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('admin_id', sa.Uuid(), sa.ForeignKey('admin_users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('token_hash', sa.String(64), nullable=False),
            sa.Column('auth_version', sa.Integer(), nullable=False),
            sa.Column('email_encrypted', sa.Text(), nullable=False),
            sa.Column('reason', sa.String(500), nullable=False),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('confirmed_at', sa.DateTime(timezone=True)),
            sa.Column('decided_at', sa.DateTime(timezone=True)),
            sa.Column('decided_by', sa.Uuid()),
            sa.Column('decided_by_name', sa.String(120)),
            sa.Column('decision_note', sa.String(500)),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        op.create_index('ix_admin_mfa_recoveries_admin_id', 'admin_mfa_recoveries', ['admin_id'])
        op.create_index('ix_admin_mfa_recoveries_token_hash', 'admin_mfa_recoveries', ['token_hash'], unique=True)
    if not sa.inspect(bind).has_table('mfa_recovery_emails'):
        op.create_table('mfa_recovery_emails',
            sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('recovery_id', sa.Uuid(), sa.ForeignKey('admin_mfa_recoveries.id', ondelete='CASCADE'), nullable=False),
            sa.Column('recipient_id', sa.Uuid(), sa.ForeignKey('admin_users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('kind', sa.String(20), nullable=False),
            sa.Column('payload_encrypted', sa.Text()),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('attempts', sa.Integer(), nullable=False),
            sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        op.create_index('ix_mfa_recovery_emails_recovery_id', 'mfa_recovery_emails', ['recovery_id'])
        op.create_index('ix_mfa_recovery_emails_recipient_id', 'mfa_recovery_emails', ['recipient_id'])


def downgrade():
    # Conservar las solicitudes y decisiones; no eliminar trazabilidad automáticamente.
    pass
