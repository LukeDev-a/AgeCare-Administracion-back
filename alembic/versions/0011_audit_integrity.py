"""Metadata explícita y defensa append-only de auditoría en PostgreSQL."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    columns = {c['name'] for c in sa.inspect(connection).get_columns('audit_log')}
    if 'event_metadata' not in columns:
        op.add_column('audit_log', sa.Column('event_metadata', sa.JSON().with_variant(JSONB(), 'postgresql'), nullable=True))
    if connection.dialect.name == 'postgresql':
        op.execute("""CREATE OR REPLACE FUNCTION public.agecare_audit_immutable()
        RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        BEGIN
            RAISE EXCEPTION 'Audit log is append-only' USING ERRCODE = '42501';
        END $$""")
        op.execute('DROP TRIGGER IF EXISTS agecare_audit_immutable ON public.audit_log')
        op.execute('''CREATE TRIGGER agecare_audit_immutable
            BEFORE UPDATE OR DELETE OR TRUNCATE ON public.audit_log
            FOR EACH STATEMENT EXECUTE FUNCTION public.agecare_audit_immutable()''')


def downgrade():
    # No quitar defensas ni metadata histórica mediante un downgrade automático.
    pass
