"""Registra diez juegos nuevos inactivos; conserva fichas y estados existentes."""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from uuid import uuid4

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

# Instantánea de esta entrega: no importar un catálogo mutable en la migración.
GAMES = [
  {
    "slug": "sudoku",
    "title": "Sudoku sencillo",
    "description": "Completa un tablero de 4 por 4 con números del 1 al 4.",
    "category": "Lógica"
  },
  {
    "slug": "torres-hanoi",
    "title": "Torres de Hanói",
    "description": "Mueve los discos entre torres, uno a uno y sin poner uno grande sobre uno pequeño.",
    "category": "Lógica"
  },
  {
    "slug": "balanza",
    "title": "Equilibra la balanza",
    "description": "Combina pesas para conseguir el mismo peso en ambos lados.",
    "category": "Cálculo"
  },
  {
    "slug": "secuencia-luces",
    "title": "Secuencia de luces",
    "description": "Observa las figuras iluminadas a tu ritmo y repite el orden.",
    "category": "Memoria"
  },
  {
    "slug": "bolos",
    "title": "Bolos tranquilos",
    "description": "Elige dirección y fuerza para derribar los bolos en dos lanzamientos.",
    "category": "Coordinación"
  },
  {
    "slug": "une-puntos",
    "title": "Une los puntos",
    "description": "Toca los números en orden y descubre un dibujo, sin arrastrar.",
    "category": "Percepción"
  },
  {
    "slug": "refranes",
    "title": "Completa el refrán",
    "description": "Elige la expresión que completa un refrán conocido y descubre su significado.",
    "category": "Lenguaje"
  },
  {
    "slug": "dibujo-cuadricula",
    "title": "Descubre el dibujo",
    "description": "Pinta una cuadrícula pequeña siguiendo las pistas de sus filas y columnas.",
    "category": "Lógica"
  },
  {
    "slug": "codigo-secreto",
    "title": "Código secreto",
    "description": "Deduce una combinación de tres figuras usando las pistas de cada intento.",
    "category": "Lógica"
  },
  {
    "slug": "tesoro",
    "title": "El tesoro escondido",
    "description": "Explora casillas y usa las distancias para localizar el tesoro.",
    "category": "Orientación"
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

