# Incidentes operativos — fase 06

26 de octubre de 2026. Gestión manual integrada en Estado operativo, debajo de procesos críticos. Fase cerrada funcionalmente el 27 de octubre de 2026 con aceptación del usuario. No crea incidentes automáticamente ni modifica el estado de los componentes al registrar uno.

## Rutas y autorización

Se completan tres rutas existentes bajo `/api/v1/admin/ops`:

| Método | Ruta | Permiso |
|---|---|---|
| GET | `/incidents?days=30&status=observing&component=auth&page=1&page_size=10` | admin, support, analyst |
| POST | `/incidents` | admin, support |
| PATCH | `/incidents/{id}` | admin, support |

Editor/moderator: 403; sin sesión válida: 401. No hay endpoint de eliminar. El frontend usa apiFetch; la visibilidad usa canManageIncidents y no sustituye el control de la API. El creador procede de la sesión, no del cuerpo.

GET conserva days 1–365, default 30; page desde 1 y page_size 1–100, default 25 en API (10 en panel). Orden estable started_at/id descendentes. Desde now-days sin tope superior para conservar mantenimientos futuros. Vacío es items=[]/total=0, no error.

POST requiere título 5–160, descripción 1–4000, severidad degraded/outage y started_at con zona; componente opcional y is_maintenance false por defecto. Recorta espacios. Inicio futuro no permitido salvo mantenimiento. Estado inicial investigating u observing respectivamente. Guarda creador, auditoría y avisos en la misma transacción.

PATCH admite únicamente los campos de contrato estado, descripción (1–4000) y resolución (1–2000), conservando omitidos. Rechaza cuerpo vacío, null explícito y textos vacíos. Incidentes: investigating → observing → resolved. Mantenimientos: observing → completed. No permite retroceder, reabrir, repetir estado ni saltar etapas. Cierre requiere nota no vacía enviada o previamente guardada; fija resolved_at. Descripción/nota pueden corregirse después del cierre sin reabrir el registro.

Se bloquea la fila antes de validar para serializar cambios de estado en PostgreSQL. Las validaciones se hacen antes de mutar. Cambios reales actualizan updated_at y auditan campos antes/después, actor e instante. Un PATCH sin cambios reales no crea una edición falsa. La concurrencia de transiciones y cola se comprobó en PostgreSQL temporal el 27 de octubre de 2026, con SMTP simulado.

## Correo opcional

El usuario eligió reutilizar SMTP de las invitaciones, **sin destinatarios por ahora**. No se editó `.env`. Para dejarlo desactivado:

```ini
ADMIN_INCIDENT_MAIL_RECIPIENTS=
```

Más adelante, en el `.env` del backend y con destinatarios autorizados:

```ini
ADMIN_INCIDENT_MAIL_RECIPIENTS=operaciones@example.org,soporte@example.org
ADMIN_MAIL_WORKER_ENABLED=true
```

Son ejemplos, no direcciones de envío acordadas. Reutiliza ADMIN_SMTP_* y ADMIN_MAIL_FROM existentes; no repetir contraseñas ni ponerlas en VITE_*. Mantener la misma ADMIN_ENCRYPTION_KEY. Cambios de entorno requieren recrear el contenedor (`docker compose up -d --force-recreate api`); si también cambió código, usar `docker compose up -d --build api`.

Sin destinatarios, direcciones inválidas o configuración incompleta, el incidente se guarda con notification_status=not_configured, sin crear avisos. Configuración válida: se deduplican destinatarios y se encola un aviso por correo. Las ediciones no vuelven a notificar y configurar destinatarios no envía registros antiguos automáticamente.

Modelos: Incident.notification_status y nueva IncidentEmail (`ops_incident_emails`, FK a incidente). Migración **0009** agrega columna y tabla sin borrar datos; registros previos quedan not_configured. Guards para instalaciones nuevas con metadata actual. Downgrade conserva los datos deliberadamente.

El payload con destinatario/título/identificador/severidad/inicio se cifra con Fernet; no incluye descripción libre ni notas de resolución. Se elimina al enviar o agotar intentos. Se comparte transporte SMTP/TLS, sin reutilizar el texto o los tokens de invitaciones.

Un worker ligado a ADMIN_MAIL_WORKER_ENABLED procesa fuera de la petición, después del commit, con bloqueo skip_locked. Reintenta hasta cinco fallos, con espera creciente; no registra errores SMTP/payloads que puedan revelar datos. Estado agregado queued, sent o failed. sent significa aceptación por SMTP, no confirmación de llegada al buzón. La entrega técnica conserva updated_at de la edición de negocio. No hay reenvío manual implementado.

Bloqueos evitan envíos simultáneos normales del mismo registro, pero SMTP no garantiza exactamente una entrega ante un fallo después de aceptación y antes de commit. No afirmar entrega exactamente una vez.

## Interfaz y verificación

Panel IncidentsPanel, formulario IncidentForm, cliente api/incidents.ts y etiquetas lib/incidentsMeta.ts. No añade otra ruta de menú. Al aplicar filtros vuelve a página 1. Formularios validan límites, solo ofrecen siguiente estado permitido y exigen nota al cerrar. PATCH envía solo cambios del formulario. Errores conservan el formulario; no se muestran controles de gestión a analyst.

Pruebas con HTTP/base aislados y SMTP sustituido, no correos reales. DDL 0009 validado en SQLite; script tests/check_incidents_postgres.py preparado para base temporal restringida. El 27 de octubre se completó esa comprobación en PostgreSQL temporal y el usuario aprobó la revisión funcional. La base temporal se eliminó al terminar; datos habituales intactos.
