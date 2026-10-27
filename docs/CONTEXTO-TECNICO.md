# Mapa del backend

Fase 05: [monitoreo-operativo.md](monitoreo-operativo.md) documenta RF05.01–03, tipos/origen/fechas, selección de latencias y 0008. Consultas probadas; no hay recolector real nuevo ni ejecutor sintético. Legado queda unknown. API habitual pendiente de reconstruir; validación PostgreSQL solo temporal.

La fase 04 añade migración 0007 y cálculo/caché diaria de cohortes. Leer [analitica-comercial.md](analitica-comercial.md): explica tablas nuevas, frescura por fuente, contrato del embudo y límites de la futura ingesta real. La API habitual del usuario no se actualizó durante esta entrega; PostgreSQL se verificó en base temporal. RF04.03 sigue pendiente de unidad facturable.

## Estructura

| Archivo o carpeta | Responsabilidad |
|---|---|
| `app/main.py` | FastAPI, CORS, errores, routers, estáticos y lifespan del correo |
| `app/config.py` | Settings con prefijo `ADMIN_`, `.env` y caché |
| `app/database.py` | Motor async, fábrica de sesiones y transacción por petición |
| `app/models.py` | Modelos ORM, incluyendo negocio, agregados, cuentas y acceso |
| `app/analytics_models.py` | Observaciones mínimas de cuentas móviles, actividad, pagos, frescura y cachés de cohortes; registrado desde models.py |
| `app/commercial_analytics.py` | Cálculo por cohortes y worker de caché diaria; no ingesta real |
| `app/schemas/` | Entradas/salidas y validación Pydantic |
| `app/routers/` | Operaciones HTTP por módulo |
| `app/deps.py`, `app/enums.py` | Autenticación, autorización y matriz de roles |
| `app/security.py` | Contraseñas, tokens y utilidades de fechas/hashes |
| `app/account_security.py` | Cifrado, TOTP, QR y códigos de recuperación |
| `app/login_attempts.py` | Ventana móvil de fallos, bloqueo temporal y reinicio de intentos |
| `app/invitation_mail.py` | Cola cifrada, envío SMTP y worker |
| `app/audit.py` | Registro de cambios de negocio y etiquetas |
| `app/errors.py` | Errores JSON y request_id |
| `app/periods.py` | Fechas y agrupación de periodos de negocio |
| `app/static/` | Juegos y otros recursos servidos bajo `/static` |
| `alembic/` | Migraciones; incluye alta inicial e invitaciones/MFA |
| `tests/` | Pruebas HTTP, seguridad, negocio y migraciones sobre SQLite |
| `scripts/seed.py` | `--only-empty`: demo por módulos vacíos sin sobrescritura; sin flag: reinicialización destructiva manual |

## Contratos y datos

Desde el 26 de octubre de 2026: GET `/api/v1/admin/support/agents` requiere escritura de soporte (admin/support) y entrega un array mínimo de `{id, full_name}` de cuentas activas para asignar tickets, respetando la selección de cuentas activas anterior. No expone correo, rol ni datos de seguridad; no concede acceso a `/users`. Seis pruebas por rol/sesión ausente verifican autorización, campos y cuentas inactivas; suite completa 124 pruebas aprobadas. No requiere migración. Frontend lector no consulta este selector. Evidencia y límites en seguimiento de fase 3.

Prefijo: `/api/v1/admin`. OpenAPI: `/api/v1/admin/openapi.json`. Swagger: `/api/v1/admin/docs`. `/health` es una respuesta de salud básica, no el recolector de métricas operativas.

Routers: `auth` (sesiones y cuentas), `account_access` (invitaciones/MFA), `games_apps`, `auditing`, `metrics_commercial`, `metrics_roles`, `metrics_features`, `ops`, `support`, `content`, `marketplace`, `moderation`, `system`. Usa las declaraciones reales para obtener rutas, métodos y schemas; no inferir el contrato a partir del nombre de archivo.

Los errores se presentan como `error` con `code`, `message`, `details` y `request_id`. Las listas paginadas usan los schemas comunes cuando corresponde. Fechas UTC y fechas de negocio tienen propósitos diferentes: revisar conversiones y `ADMIN_BUSINESS_TIMEZONE` al trabajar con periodos.

Los agregados comerciales/operativos no se recalculan por el mero hecho de consultar un endpoint. El código incluye carga de demostración, no una conexión completa con cobros, tiendas de aplicaciones o comprobaciones periódicas externas.

## Configuración y operación local

Consulta `.env.example` y `app/config.py` para nombres y valores predeterminados, sin copiar secretos reales. Familias principales: base de datos, CORS, JWT, vencimientos, dominios de correo, SMTP, URL del frontend, MFA, cifrado y zona horaria.

Compose inicia PostgreSQL 16 y la API en puertos locales 5432 y 8000. PostgreSQL usa el volumen `pgdata`. Ejecuta migraciones, bootstrap de cuentas condicionado y `scripts.seed --only-empty` antes de Uvicorn. Desde el 26 de octubre, la demo local se habilita por defecto en Compose con `ADMIN_SEED_DEMO_ENABLED`, solo en dev; conserva grupos con cualquier dato y rellena grupos totalmente vacíos. El seed destructivo sin flag nunca se ejecuta automáticamente. [Guía y evidencia](datos-demo-arranque.md).

La sección `environment` de Compose establece la conexión a `db` y un secreto JWT de desarrollo, y tiene prioridad sobre `env_file` para esas variables. La configuración actual es local; no reutilizar las credenciales de desarrollo en producción.

Comandos desde esta carpeta, cuando el usuario autorice operar servicios:

```powershell
# Actualizar código/dependencias de API
docker compose up -d --build api
# Aplicar cambios de variables sin reconstruir imagen
docker compose up -d --force-recreate api
# Estado y diagnóstico
docker compose ps
docker compose logs -f api
```

`restart` no reconstruye imágenes ni vuelve a cargar variables del `.env`. No hace falta borrar imágenes para actualizar código. `down -v` puede borrar los datos del volumen y no es un paso de actualización.

## Seguridad y límites

Lee `invitaciones-mfa.md` para el detalle de los tokens restringidos, envío, vencimientos y recuperación. Conserva la clave Fernet junto con los respaldos protegidos de la base que la requiere. Una rotación requiere migrar los secretos cifrados.

El restablecimiento MFA autorizado por otro admin no existe todavía. No introducir una omisión de MFA global para resolver una cuenta bloqueada. No enviar correos reales ni modificar cuentas reales como efecto lateral de pruebas.

Las migraciones se han probado con SQLite; comprueba PostgreSQL en un entorno aislado cuando un cambio dependa de bloqueos, tipos o DDL específico. La migración inicial utiliza metadata del modelo, por lo que conviene revisar tanto bases nuevas como actualización de esquemas anteriores.

La fase 01 incorporó la migración `0003` (JSON de timestamps de intentos), ventana móvil de diez minutos para contraseña/TOTP/recuperación y revocación inmediata de JWT ante reutilización de refresh rotado. La carrera de dos renovaciones fue probada cinco veces en PostgreSQL 16 temporal mediante `tests/check_refresh_postgres.py`. Ese script solo apunta al puerto local 55439 y base `phase1_test`; no debe adaptarse para una base real. Esta prueba valida concurrencia, no certifica migraciones sobre el despliegue del usuario. La base habitual no se modificó.
