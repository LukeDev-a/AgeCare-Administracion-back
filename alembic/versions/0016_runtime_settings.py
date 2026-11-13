"""Funciones editoriales y aviso de consola, sin sobrescribir configuraciones instaladas."""
from alembic import op
import sqlalchemy as sa

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None

NOTICE_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'notice_enabled': {'type': 'boolean'},
                   'notice_title': {'type': 'string', 'maxLength': 120},
                   'notice_body': {'type': 'string', 'maxLength': 1000}},
    'required': ['notice_enabled', 'notice_title', 'notice_body'],
    'if': {'properties': {'notice_enabled': {'const': True}}},
    'then': {'properties': {'notice_title': {'pattern': r'\S'}, 'notice_body': {'pattern': r'\S'}}},
}
FEATURE_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'news_collection_enabled': {'type': 'boolean'}, 'news_adaptation_enabled': {'type': 'boolean'}},
    'required': ['news_collection_enabled', 'news_adaptation_enabled'],
}


def upgrade():
    table = sa.table('system_settings', sa.column('key', sa.String), sa.column('description', sa.Text),
        sa.column('value', sa.JSON), sa.column('value_schema', sa.JSON), sa.column('version', sa.Integer))
    bind = op.get_bind()
    if not bind.scalar(sa.select(table.c.key).where(table.c.key == 'system_texts')):
        bind.execute(table.insert().values(key='system_texts', description='Aviso general para las personas que usan la consola.',
            value={'notice_enabled': False, 'notice_title': '', 'notice_body': ''}, value_schema=NOTICE_SCHEMA, version=1))
    if not bind.scalar(sa.select(table.c.key).where(table.c.key == 'feature_flags')):
        bind.execute(table.insert().values(key='feature_flags', description='Disponibilidad de recopilación de noticias y adaptación con Gemini.',
            value={'news_collection_enabled': True, 'news_adaptation_enabled': True}, value_schema=FEATURE_SCHEMA, version=1))


def downgrade():
    # Conservar configuraciones y su historial.
    pass
