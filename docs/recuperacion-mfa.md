# Recuperación de acceso MFA

Implementación del 12 de noviembre de 2026. Aplica a las cuentas de la consola, no a usuarios móviles. Se utiliza cuando la persona perdió tanto el autenticador como todos los códigos de recuperación. Si conserva un código, puede usar el login habitual.

## Flujo

1. Desde el login, «Perdí mi autenticador y mis códigos de recuperación» abre `/recuperar-mfa`. Se solicita correo registrado, contraseña actual y motivo de 5–500 caracteres. No incluir contraseñas ni códigos en el motivo.
2. Respuesta 202 idéntica para datos incorrectos, cuentas inexistentes/inactivas, sin MFA o solicitudes limitadas. Una contraseña incorrecta de una cuenta activa cuenta para el bloqueo compartido del login. Un acierto de contraseña aquí no reinicia fallos anteriores: todavía no acredita MFA.
3. Una solicitud aceptada genera un enlace de un uso y 30 minutos, con token aleatorio almacenado solo como hash. El enlace lleva el token en el fragmento; la pantalla lo retira del historial y pide confirmación explícita. Máximo tres solicitudes aceptadas por cuenta/hora, separadas por un minuto; una aceptada cancela enlaces/solicitudes activos anteriores. Las solicitudes ignoradas por límite no invalidan el enlace anterior.
4. Confirmar cambia a pendiente y fija una vigencia de revisión de 24 horas desde la confirmación. Se avisa por correo a las otras cuentas admin activas con contraseña configurada. No se avisa a editor, analyst, support o moderator. El destino y el rol se comprueban otra vez antes del envío. No se elimina MFA ni se inicia sesión al confirmar.
5. En Cuentas de la consola → Recuperación MFA, otro admin revisa motivo, fechas y estado. Debe verificar la identidad por un canal conocido; el correo confirmado por sí solo no basta. Para aprobar exige casilla de identidad, motivo de decisión de 5–500 caracteres, contraseña propia y TOTP propio si tiene MFA activo. Rechazar también exige motivo y verificación propia. Nadie puede resolver su propia solicitud.
6. Aprobar invalida secreto TOTP anterior, códigos de recuperación, sesiones/refresh y altas MFA pendientes; incrementa auth_version, cancela recuperaciones de contraseña pendientes y fija mfa_required=true incluso para cuentas exceptuadas en desarrollo. Conserva contraseña, rol y actividad. Todo se guarda con la decisión y auditoría en la misma transacción. Rechazar conserva el acceso y MFA anterior.
7. La persona recibe la decisión por correo. Tras aprobar, inicia sesión con la contraseña habitual: recibe únicamente un token restringido de enrolamiento y debe configurar/verificar un nuevo autenticador antes de entrar. Se reutilizan QR y presentación única de códigos existentes. Se vuelve al login al completar la configuración.

Las solicitudes dejan de ser válidas al vencer, cambiar correo/auth_version, desactivar la cuenta o dejar de tener MFA. Se muestra «Vencida o invalidada» sin permitir decidir. Las decisiones resueltas no admiten repetición. La API serializa cambios de cuentas y bloquea la solicitud para evitar doble aprobación/rechazo.

## Contrato

| Método | Ruta bajo `/api/v1/admin` | Uso |
|---|---|---|
| POST | `/auth/mfa-recovery/request` | Público: email, password, reason; respuesta genérica 202. |
| POST | `/auth/mfa-recovery/confirm` | Público: token; un uso, sin sesión. |
| GET | `/mfa-recovery/requests?page=1` | Solo admin: solicitudes confirmadas, 25 por página y total. |
| POST | `/mfa-recovery/requests/{id}/decision` | Solo admin: decision=approve/reject, identity_verified, note, password y otp_code cuando corresponda. |

Las respuestas no guardan caché y no devuelven tokens, hashes ni secretos. Listado incluye motivo, estado, confirmación/vigencia, responsable/fecha/motivo de decisión y can_decide. Auditoría incluye solicitud, fallo de contraseña, confirmación y resolución, sin secretos; la confirmación se identifica como verificación por correo, no como un login MFA.

## Correo y almacenamiento

Migración **0015** crea admin_mfa_recoveries y mfa_recovery_emails. La segunda es una cola cifrada con la clave existente ADMIN_ENCRYPTION_KEY, envío posterior al commit, cinco intentos y espera creciente. Reutiliza Brevo/SMTP y ADMIN_MAIL_WORKER_ENABLED. No necesita nuevas variables ni claves. No regenerar la clave de cifrado. Sent significa aceptación del proveedor; una caída entre aceptación y commit puede duplicar un aviso. Un fallo de envío no revierte la decisión administrativa. Datos de destinatarios y tokens pendientes se retiran de la cola al enviar/cancelar o agotar intentos.

Eliminar la cuenta retira sus solicitudes y correos asociados; el historial de auditoría conserva las decisiones. El identificador del administrador que decidió no es FK restrictiva y su nombre queda guardado.

## Aplicación y prueba manual

Local, desde el directorio del backend, ejecutar `docker compose up -d --build api`. El Compose actual aplica Alembic y prepara el rol limitado. Recargar el frontend. No ejecutar seed destructivo ni borrar volúmenes. Para esta entrega el agente no reconstruyó servicios habituales ni migró local/Neon.

Probar con una cuenta de prueba que ya tenga MFA y correo accesible, más otro administrador que conserve acceso. Solicitar y confirmar el correo; revisar desde la otra cuenta, comprobar identidad y aprobar; comprobar cierre de sesiones y nuevo enrolamiento. Probar también rechazo (conserva MFA), enlace repetido/vencido y autoaprobación bloqueada. La cuenta de prueba perderá su autenticador anterior al aprobar: ese es el efecto esperado. Si es el único administrador con acceso, este flujo no permite autoaprobarse: necesita intervención operativa separada, no una excepción pública.

**Render/Neon:** antes de desplegar el backend nuevo, aplicar 0015 mediante la conexión propietaria de migraciones, fuera del proceso de la API. Conceder SELECT/INSERT/UPDATE/DELETE de ambas tablas al rol limitado existente de Render, conservando los permisos restringidos de audit_log. Nunca introducir la conexión propietaria en Render. Mantener ADMIN_FRONTEND_URL con el dominio público estable y correo activo. run_render rechaza arrancar con una revisión anterior. La migración y los permisos de Neon siguen pendientes de operación explícita; no se hicieron en esta entrega.

## Evidencia

Suite backend: 440 pruebas aprobadas en memoria. Frontend: 139 pruebas aprobadas, build y lint dirigido correctos. Cobertura: flujo completo hasta nuevo MFA, revocación JWT/refresh, contraseña conservada, límites/bloqueo, expiración/correo/versión, identidad, permisos, autoaprobación, repetición, notificaciones y reintentos. Migración idempotente y preservación comprobadas en SQLite; PostgreSQL 16 temporal también comprobó preservación y solicitudes/confirmación/decisiones simultáneas. Contenedor temporal retirado sin volumen persistente. Prueba reproducible: `tests/check_mfa_recovery_postgres.py`, con guardas de nombre de base y host; nunca ejecutarlo contra bases habituales. No se enviaron correos reales ni se usaron cuentas habituales. Revisión visual y entrega real por correo pendientes del usuario.
