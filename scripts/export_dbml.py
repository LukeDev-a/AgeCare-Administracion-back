"""Exporta la estructura ORM a DBML sin conectar a una base ni leer el .env."""
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.database import Base
from app import models  # noqa: F401: registrar todas las tablas


def quote(value):
    return "'" + str(value).replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n') + "'"


def render():
    lines = [
        '// Modelo físico del backend administrativo AgeCare. Fuente: app/models.py.',
        '// No consulta registros, secretos, una base desplegada ni la app Flutter.',
        '// Solo Ref declara ForeignKey reales. UUID sin FK conserva su independencia.',
        '// default representa valores del servidor; los defaults Python se explican en notas.',
        'Project AgeCare_Admin {',
        "  database_type: 'PostgreSQL'",
        "  Note: 'Estructura ORM actual. No incluye alembic_version ni tablas de otra API móvil.'",
        '}', '',
    ]
    dialect = postgresql.dialect()
    for table in Base.metadata.tables.values():
        lines.append(f'Table {table.name} {{')
        for column in table.columns:
            kind = str(column.type.compile(dialect=dialect)).lower()
            kind = kind.replace('timestamp with time zone', 'timestamptz')
            if ' ' in kind:
                kind = '"' + kind + '"'
            settings = ['pk'] if column.primary_key else []
            settings.append('null' if column.nullable else 'not null')
            notes = []
            if column.server_default is not None:
                value = str(column.server_default.arg)
                if value.lower() in ('true', 'false') or value.isdigit():
                    settings.append('default: ' + value.lower())
                elif isinstance(column.server_default.arg, str):
                    settings.append('default: ' + quote(value))
                else:
                    settings.append('default: `' + value + '`')
            elif column.default is not None:
                if column.default.is_scalar:
                    notes.append('Valor inicial asignado por Python: ' + str(column.default.arg))
                else:
                    notes.append('Valor inicial generado por Python al insertar; no es un DEFAULT SQL.')
            if column.onupdate is not None:
                notes.append('Actualización automática desde SQLAlchemy.')
            if isinstance(column.type, sa.Uuid) and not column.primary_key and not column.foreign_keys:
                notes.append('Identificador sin clave foránea declarada en este modelo.')
            if notes:
                settings.append('note: ' + quote(' '.join(notes)))
            lines.append(f'  {column.name} {kind} [{", ".join(settings)}]')
        indexes = []
        for constraint in table.constraints:
            if isinstance(constraint, sa.UniqueConstraint):
                indexes.append((tuple(c.name for c in constraint.columns), True, constraint.name))
        for index in sorted(table.indexes, key=lambda item: item.name or ''):
            indexes.append((tuple(c.name for c in index.columns), index.unique, index.name))
        if indexes:
            lines.extend(['', '  indexes {'])
            for columns, unique, name in sorted(indexes, key=lambda item: item[0]):
                value = columns[0] if len(columns) == 1 else '(' + ', '.join(columns) + ')'
                options = ['unique'] if unique else []
                if name:
                    options.append('name: ' + quote(name))
                suffix = ' [' + ', '.join(options) + ']' if options else ''
                lines.append('    ' + value + suffix)
            lines.append('  }')
        lines.extend(['}', ''])
    lines.append('// Relaciones físicas (muchos a uno).')
    for table in Base.metadata.tables.values():
        for fk in sorted(table.foreign_keys, key=lambda item: item.parent.name):
            action = ' [delete: ' + fk.ondelete.lower() + ']' if fk.ondelete else ''
            lines.append(f'Ref: {table.name}.{fk.parent.name} > {fk.column.table.name}.{fk.column.name}{action}')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    output = Path(__file__).resolve().parents[1] / 'docs/modelo-datos.dbml'
    output.write_text(render(), encoding='utf-8')
    print(f'DBML generado: {len(Base.metadata.tables)} tablas, '
          f'{sum(len(table.columns) for table in Base.metadata.tables.values())} columnas, '
          f'{sum(len(table.foreign_keys) for table in Base.metadata.tables.values())} relaciones.')
