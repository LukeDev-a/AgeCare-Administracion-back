"""Recuperación de contraseña y cola cifrada de correos."""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table('admin_password_resets'):
        return
    op.create_table('admin_password_resets',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('admin_id', sa.Uuid(), sa.ForeignKey('admin_users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('auth_version', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True)),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('payload_encrypted', sa.Text()),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_admin_password_resets_admin_id', 'admin_password_resets', ['admin_id'])
    op.create_index('ix_admin_password_resets_token_hash', 'admin_password_resets', ['token_hash'], unique=True)


def downgrade():
    # Conservar trazabilidad de recuperaciones y correos pendientes.
    pass
