# Modelo de datos para dbdiagram.io

El archivo [modelo-datos.dbml](modelo-datos.dbml) contiene el código completo para pegar en https://dbdiagram.io/d.

1. Abrir el archivo `.dbml` como texto en el editor.
2. Copiar todo su contenido.
3. En dbdiagram.io, crear un diagrama y reemplazar el ejemplo del panel de código por ese contenido.

Incluye **41 tablas, 411 columnas y 16 claves foráneas** declaradas en `app/models.py` y `app/analytics_models.py`, registrado desde el primero, del backend administrativo. Actualizado el 16 de noviembre de 2026: incluye recuperación de contraseña, recuperación de acceso MFA y colas de correo, además de las tres tablas `app_accounts`, `app_patients` y `app_memberships` de fase18, autoría de juegos y event_metadata de auditoría, además de fases 04, 05 y 06. Las nuevas tablas son exclusivamente de demostración, **no el modelo canónico de cuentas/pacientes de la API móvil real**. Es un modelo físico obtenido del código, no una inspección de una base desplegada. No incluye la tabla técnica `alembic_version`, registros ni el esquema de otra API móvil. La interfaz React no tiene una base independiente que añadir aquí. Los permisos/triggers de 0011 se explican en [auditoría administrativa](auditoria-administrativa.md); DBML representa columnas/relaciones, no esos permisos.

Migración0017 actualiza los nombres físicos del directorio y conserva sus datos. El DBML refleja esos nombres; debe migrarse una instalación anterior antes de desplegar el backend nuevo. Los nombres/correos de personas se guardan como registros: no aparecen dentro del DBML, que solo representa estructura.

## Cómo interpretarlo

- `pk`: clave primaria.
- `not null` / `null`: obligatoriedad de la columna.
- `indexes`: índices, restricciones de unicidad y claves primarias compuestas. Las restricciones CHECK se describen en notas de tabla.
- `Ref`: claves foráneas reales, con la acción de eliminación cuando está declarada.
- `jsonb`: objeto/lista JSON almacenado en PostgreSQL; sus propiedades internas no son tablas adicionales.
- Las notas diferencian valores iniciales generados por Python de `DEFAULT` definidos en PostgreSQL. No se ejecutan generadores ni consultas para exportar.

Algunos campos como `actor_id`, `created_by` o identificadores de usuarios externos **no declaran ForeignKey en este backend**. El diagrama los conserva como UUID sin inventar relaciones. Por eso hay tablas sin líneas: es la estructura actual, no una omisión del dibujo. Los roles siguen siendo columnas de texto; no se dibuja una tabla de roles ni un enum SQL que no existe. Relaciones adicionales de negocio requerirían otro modelo conceptual, identificado como tal.

`games_apps` refleja la limpieza reciente: sin icon_url, banner_url, preview_image_url, sort_order ni accessibility. La presencia de `deleted_at` no implica que el endpoint de juegos use borrado lógico: actualmente elimina la ficha permanentemente.

## Regenerar cuando cambien los modelos

Desde la raíz del backend, con las dependencias ya instaladas:

```powershell
.\venv\Scripts\python.exe -m scripts.export_dbml
```

El exportador importa metadata de SQLAlchemy sin abrir una conexión a PostgreSQL, leer el `.env`, cargar registros ni ejecutar migraciones. Solo escribe `docs/modelo-datos.dbml`. No modifica código de negocio ni la base.

Exportación inicial: 24 de octubre de 2026. Regenerado el 16 de noviembre de 2026 desde metadata ORM y validado con el parser de `@dbml/cli` mediante conversión a SQL PostgreSQL. El SQL de comprobación está en `outputs/modelo-datos-validacion.sql` del workspace y no se ha ejecutado contra ninguna base. No se ha importado el archivo en una cuenta de dbdiagram.io. El diagrama describe la estructura del código actual, no certifica el estado de una base desplegada.
