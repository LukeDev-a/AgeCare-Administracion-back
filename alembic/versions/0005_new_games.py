"""Registra diez juegos nuevos inactivos; conserva fichas y estados existentes."""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from uuid import uuid4

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

# Instantánea de esta entrega: no importar un catálogo mutable en la migración.
GAMES = [
  {
    "slug": "domino",
    "title": "Dominó tranquilo",
    "description": "Une fichas con números iguales, a tu ritmo.",
    "category": "Dominó"
  },
  {
    "slug": "lista-compras",
    "title": "Mi lista de compras",
    "description": "Recuerda una lista y encuentra sus productos.",
    "category": "Memoria"
  },
  {
    "slug": "palabras-silabas",
    "title": "Palabras por sílabas",
    "description": "Construye palabras tocando sus sílabas.",
    "category": "Lenguaje"
  },
  {
    "slug": "cada-cosa",
    "title": "Cada cosa en su lugar",
    "description": "Elige el grupo al que pertenece cada objeto.",
    "category": "Asociación"
  },
  {
    "slug": "camino-casa",
    "title": "Camino a casa",
    "description": "Encuentra un camino en un laberinto diferente en cada ronda.",
    "category": "Orientación"
  },
  {
    "slug": "continua-patron",
    "title": "Continúa el patrón",
    "description": "Descubre qué figura sigue en la serie.",
    "category": "Lógica"
  },
  {
    "slug": "reloj",
    "title": "Pon el reloj en hora",
    "description": "Ajusta las agujas para representar la hora indicada.",
    "category": "Vida cotidiana"
  },
  {
    "slug": "cuenta-elige",
    "title": "Cuenta y elige",
    "description": "Cuenta los objetos y elige su cantidad.",
    "category": "Atención"
  },
  {
    "slug": "tres-raya",
    "title": "Tres en raya",
    "description": "Forma una línea de tres símbolos sin prisa.",
    "category": "Estrategia"
  },
  {
    "slug": "mi-paisaje",
    "title": "Mi paisaje",
    "description": "Construye una escena colocando elementos a tu gusto.",
    "category": "Creatividad"
  }
]


def upgrade():
    bind = op.get_bind()
    # Leer el esquema de esta instalación, independiente del ORM actual.
    # 0001 crea metadata actual: bases nuevas pueden no tener columnas antiguas.
    table = sa.Table('games_apps', sa.MetaData(), autoload_with=bind)
    for game in GAMES:
        if bind.execute(sa.select(table.c.id).where(table.c.slug == game['slug'])).first() is None:
            game_id = uuid4()
            values = dict(game, id=game_id.hex if bind.dialect.name == 'sqlite' else game_id,
                item_type='game', min_tier='gratuito',
                is_active=False, featured=False, target_url=f"/static/juegos/{game['slug']}/index.html",
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
            if 'sort_order' in table.c:
                values['sort_order'] = 0
            bind.execute(table.insert().values(**values))


def downgrade():
    # No borrar fichas que el administrador pudo editar/activar después del alta.
    pass

