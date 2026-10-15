"""Contenido editorial, trabajos y cuotas persistentes; no publicar demos."""
from alembic import op
import sqlalchemy as sa
from app.models import NewsCandidate, ContentJob, ContentControl, PortableJSON

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

FIELDS = [
    sa.Column('text_version', sa.Integer(), nullable=False, server_default='1'),
    sa.Column('audio_version', sa.Integer(), nullable=True),
    sa.Column('audio_file', sa.String(160), nullable=True),
    sa.Column('audio_status', sa.String(20), nullable=False, server_default='pending'),
    sa.Column('audio_error', sa.String(300), nullable=True),
    sa.Column('source_candidate_id', sa.Uuid(), nullable=True),
    sa.Column('provenance', PortableJSON, nullable=True),
    sa.Column('approved_version', sa.Integer(), nullable=True),
    sa.Column('reviewed_by', sa.Uuid(), nullable=True),
    sa.Column('reviewed_by_name', sa.String(120), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
]

def upgrade():
    bind = op.get_bind()
    existing = {c['name'] for c in sa.inspect(bind).get_columns('content_items')}
    for column in FIELDS:
        if column.name not in existing:
            op.add_column('content_items', column)
    for table in [NewsCandidate.__table__, ContentJob.__table__, ContentControl.__table__]:
        table.create(bind, checkfirst=True)
    # Marcadores legacy nunca demuestran que exista un audio real.
    bind.execute(sa.text("UPDATE content_items SET tts_ready = false WHERE audio_file IS NULL"))
    for key in ['collection', 'quota_text', 'quota_tts']:
        if bind.execute(sa.select(ContentControl.__table__.c.key).where(ContentControl.__table__.c.key == key)).first() is None:
            bind.execute(ContentControl.__table__.insert().values(key=key, data={}))

def downgrade():
    for table in [ContentJob.__table__, NewsCandidate.__table__, ContentControl.__table__]:
        table.drop(op.get_bind(), checkfirst=True)
    with op.batch_alter_table('content_items') as batch:
        for column in reversed(FIELDS):
            batch.drop_column(column.name)
