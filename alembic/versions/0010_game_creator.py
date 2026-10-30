"""Identidad del creador del juego; legado sin atribución inventada."""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('games_apps')}
    for name, kind in [('created_by', sa.Uuid()), ('created_by_name', sa.String(120))]:
        if name not in columns:
            op.add_column('games_apps', sa.Column(name, kind, nullable=True))


def downgrade():
    pass  # Conservar atribución histórica.
