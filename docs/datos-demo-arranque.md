# Datos de demostración al arrancar Docker

Desde el 26 de octubre de 2026, el Compose local ejecuta:

1. `alembic upgrade head`: prepara la estructura.
2. `python -m scripts.bootstrap_dev_accounts`: crea cuentas solo si se habilita y no existe ninguna.
3. `python -m scripts.seed --only-empty`: carga ejemplos únicamente en módulos vacíos.
4. `python -m scripts.run_api`: prepara un login PostgreSQL limitado e inicia Uvicorn con esa conexión. Desde fase 17, migración 0011 y permisos de auditoría se entregan juntos; véase [auditoría administrativa](auditoria-administrativa.md).

Para el profesor basta recibir estos cambios, configurar el `.env` y ejecutar desde la carpeta backend:

```powershell
docker compose up -d --build api
```

## Condición que protege los datos

Si un módulo tiene **cualquier registro en alguna de sus tablas**, se conserva el grupo completo: no se borran registros, no se sobrescriben valores y no se rellenan huecos de módulos parcialmente poblados. Si está completamente vacío, se añaden ejemplos. Vaciar todo un módulo hará que reciba ejemplos en el próximo arranque habilitado; no es una sincronización continua.

| Grupo comprobado | Tablas |
|---|---|
| Analítica comercial | metrics_daily_users, metrics_hourly_users, metrics_plan_snapshot |
| Actividad por rol | role_activity_window, role_weekly_active |
| Funcionalidades | features, feature_usage_window |
| Monitoreo | ops_component_state, ops_latency_window, ops_critical_process_state |
| Incidentes | ops_incidents |
| Tickets | support_tickets, support_ticket_replies |
| Contenido | content_items, news_candidates, content_jobs |
| Cuidadoras | marketplace_caregivers |
| Productos | marketplace_products |
| Moderación | moderation_queue |
| Configuración | system_settings |
| Legales | legal_versions |
| Usuarios y pacientes de demostración (fase18) | demo_app_accounts, demo_app_patients, demo_app_memberships |

Los controles técnicos/cuotas de `content_control` se conservan y no impiden cargar contenido si no hay candidatos, trabajos ni artículos. Los ejemplos de contenido entran en **borrador**, sin audio válido ni publicación automática. El seed no envía correos ni consume Gemini; la habilitación de workers es independiente.

Los juegos se comprueban por dos colecciones: los diez originales y los diez nuevos. La migración 0005 ya puede haber registrado los nuevos; eso no impide completar los originales en una instalación nueva. Si una colección tiene algún juego, se conserva entera: no restablece nombres, activaciones, planes ni juegos individuales eliminados. Si la colección está completamente vacía, carga sus ejemplos. Las rutas nuevas son relativas para que la API resuelva su dominio público.

Las cuentas, hashes de contraseñas, MFA, sesiones, invitaciones y auditoría **no se modifican** en `--only-empty`. El bootstrap de cuentas mantiene su condición y su variable propias. Si no existen cuentas porque está deshabilitado, los ejemplos pueden cargarse sin atribuirlos a un administrador inexistente.

El grupo de fase18 se carga adicionalmente solo con `ADMIN_END_USERS_DEMO_ENABLED=true` y entorno dev (Compose dev lo habilita por defecto). Son cuentas ficticias **sin credenciales ni sesiones**, no las cuentas internas protegidas en el párrafo anterior. Si cualquiera de las tres tablas tiene datos, se conserva todo: no se reactivan cuentas ni se reinician motivos/vínculos al reconstruir. [Uso y límites](usuarios-pacientes-demo.md).

## Variables

```dotenv
ADMIN_ENVIRONMENT=dev
ADMIN_BOOTSTRAP_DEV_ACCOUNTS=true
ADMIN_SEED_DEMO_ENABLED=true
```

`ADMIN_SEED_DEMO_ENABLED` tiene valor predeterminado **true en el Compose local**, para que un profesor que no añada la variable también reciba la demo. Fuera de Compose, el valor predeterminado del settings es false. El modo automático rechaza entornos distintos de dev si se habilita.

Para impedir cualquier futura reposición de ejemplos:

```dotenv
ADMIN_SEED_DEMO_ENABLED=false
```

Aplicar cambios del entorno con `docker compose up -d --force-recreate api`. No se cambia el `.env` real del usuario ni se regenera su clave de cifrado. La base habitual no se reinicia ni se borra para aplicar este cambio.

## Fechas, límites y pruebas

La carga automática inicial genera métricas hasta el día actual de `ADMIN_BUSINESS_TIMEZONE` y fechas relativas de demostración. Si esas tablas ya tienen datos antiguos, **los conserva**: no los convierte en actuales ni actualiza su fecha artificialmente. Los datos siguen siendo ejemplos, no mediciones del móvil.

Los procesos automáticos concurrentes se serializan mediante un advisory lock PostgreSQL dentro de la misma transacción que comprueba e inserta. Un error revierte la carga de esa ejecución.

Evidencia del 26 de octubre: **130 pruebas backend aprobadas**, con seis casos nuevos de SQLite que verifican primera carga, repetición sin cambios, protección de cuentas/MFA/sesiones y valores editados, recarga de un módulo vacío, grupos parciales, colecciones de juegos, control técnico de contenido, flags/entorno y rollback. Prueba adicional PostgreSQL en una base temporal `agecare_seed_check_*`: migraciones 0001–0006, dos cargas simultáneas, repetición, recarga exclusiva de productos, 20 juegos, tres borradores y consulta de analítica del mes actual con datos. Se llamó al handler de resumen con PostgreSQL; el ensayo no sustituye una comprobación visual. Base temporal eliminada después de validar. No se modificó `agecare_admin` durante esas pruebas. Script reproducible: `tests/check_demo_seed_postgres.py`; exige una base temporal propia, migrada, y no acepta el nombre de la base habitual.

**Atención:** `python -m scripts.seed` **sin** `--only-empty` conserva el modo destructivo manual anterior. Nunca es el comando usado por Compose. No utilizarlo para un arranque normal ni para actualizar una instalación con datos.
