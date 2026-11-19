# Modelo de datos para dbdiagram.io

## Ampliación de actividad/adopción — 19nov2026

Migración0022 añade `analytics_usage_accounts` (4columnas) y `analytics_usage_sessions` (6columnas), con FK de sesión a cuenta analítica, para la demostración compartida de actividad/adopción. No son cuentas de login ni del directorio y no se relacionan con pagos. El DBML incorpora estas dos tablas y su relación; las cifras de la entrega histórica del17nov de abajo no incluyen esta ampliación ni ops_observations de0021. Reglas/horizonte y evidencia local en [actividad-adopcion-diaria.md](actividad-adopcion-diaria.md).

Actualizado el **17 de noviembre de 2026** desde los modelos actuales del backend: **43 tablas, 432 columnas y 18 claves foráneas**.

El archivo [modelo-datos.dbml](modelo-datos.dbml) contiene el código completo para pegar en https://dbdiagram.io/d.

1. Abrir el archivo `.dbml` como texto en el editor.
2. Copiar todo su contenido.
3. En dbdiagram.io, crear un diagrama y reemplazar el ejemplo del panel de código por ese contenido.

Representa las tablas declaradas en `app/models.py` y `app/analytics_models.py`. Incluye autenticación y MFA, cuentas de la consola, recuperación de acceso y colas de correo, analítica, tickets, contenido y audio, marketplace, moderación, juegos, configuración, legales, auditoría, directorio de cuentas y adultos mayores, y suscripciones y cobros persistidos.

El directorio `app_accounts`, `app_patients` y `app_memberships` conserva las identidades ficticias autorizadas para la presentación; **no representa un servicio móvil real ya integrado**. Las tablas de pagos también almacenan operaciones simuladas, sin pasarela ni credenciales financieras. El modelo no incluye la tabla técnica `alembic_version`, registros ni el esquema de otra API móvil. La interfaz React utiliza esta API y no tiene una base independiente que añadir al diagrama. Los permisos y triggers de auditoría de 0011 se explican en [auditoría administrativa](auditoria-administrativa.md); DBML representa columnas y relaciones, no esos permisos.

## Cambios recientes incluidos

| Migración | Cambio | Representación en el modelo |
|---|---|---|
| 0017 | Nombres definitivos del directorio. | `app_accounts`, `app_patients` y `app_memberships`, conservando identificadores y vínculos. |
| 0018 | Autorización de publicación programada sin audio tras fallo, con revisión explícita. | Columna JSONB opcional `content_items.schedule_audio_exception`. |
| 0019 | Persistencia de suscripciones y cobros de presentación. | Tablas `payment_subscriptions` y `payment_charges`: 20 columnas y dos relaciones nuevas. |
| 0020 | Corrección de roles propios y ejemplo de adulta mayor sin cuenta. | Solo registros y vínculos; no añade tablas, columnas ni claves foráneas. |

En suscripciones se guardan la cuenta asociada, el plan, el precio mensual, el estado, las fechas del período, la versión, el historial de operaciones y el origen de los datos. Cada cobro conserva su suscripción, importe, estado, fecha, versión e historial.

Las relaciones añadidas son `payment_subscriptions.user_id → app_accounts.id` y `payment_charges.subscription_id → payment_subscriptions.id`. Los historiales se almacenan en JSONB; no se inventa una tabla adicional de movimientos. Las restricciones CHECK validan importes, versiones y estados; los códigos son únicos y cada cuenta tiene una suscripción en este alcance.

Los nombres y correos de personas son registros y no aparecen en el DBML. La corrección de Carmen Soto y la nueva ficha de Elvira Paredes se documentan en [usuarios y pacientes](usuarios-pacientes-demo.md), y los pagos en [pagos simulados](pagos-simulados.md).

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

## Validación y estado

Exportación inicial: 24 de octubre de 2026. Regenerado el 17 de noviembre de 2026 desde metadata ORM y validado correctamente con el parser de `@dbml/cli` mediante conversión a SQL PostgreSQL. El SQL de comprobación se conserva en `outputs/modelo-datos-validacion.sql` del workspace; no se ejecuta contra ninguna base. No se ha importado el archivo en una cuenta de dbdiagram.io.

La migración hasta 0020 ya se aplicó y verificó en Docker local y Neon. La exportación DBML se obtiene del código y no consulta esas bases; la evidencia del despliegue se documenta por separado en [Render y Neon](render-neon.md).
