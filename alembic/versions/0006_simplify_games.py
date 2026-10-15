"""Retira campos sin consumidor del catálogo de juegos, conservando las fichas."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

REMOVED = ('icon_url', 'banner_url', 'preview_image_url', 'sort_order', 'accessibility')


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('games_apps')}
    # 0001 usa metadata actual: en bases nuevas estas columnas ya no existen.
    present = columns.intersection(REMOVED)
    if not present:
        return
    indexes = inspector.get_indexes('games_apps')
    with op.batch_alter_table('games_apps') as batch:
        for index in indexes:
            if present.intersection(index['column_names']):
                batch.drop_index(index['name'])
        for name in REMOVED:
            if name in present:
                batch.drop_column(name)


def downgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('games_apps')}
    # Recupera estructura, no los valores eliminados por upgrade.
    with op.batch_alter_table('games_apps') as batch:
        for name in ('icon_url', 'banner_url', 'preview_image_url'):
            if name not in columns:
                batch.add_column(sa.Column(name, sa.String(500), nullable=True))
        if 'sort_order' not in columns:
            batch.add_column(sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
            batch.create_index('ix_games_apps_sort_order', ['sort_order'])
        if 'accessibility' not in columns:
            batch.add_column(sa.Column('accessibility', sa.JSON().with_variant(JSONB(), 'postgresql'), nullable=True))
