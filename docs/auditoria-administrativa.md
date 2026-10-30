# Auditoría administrativa — fase 17

27 de octubre de 2026. El usuario autorizó añadir accesos y consulta de conversaciones, sustituyendo la restricción anterior de auditar únicamente cambios de negocio. Los clics y la navegación general siguen excluidos.

## Qué se registra

- Mutaciones reconocidas en `BUSINESS_ACTIONS`, mediante llamadas explícitas del servicio. Las mutaciones y sus eventos comparten transacción: si se rechaza o revierte el cambio, no se acredita como realizado.
- `auth.login`: únicamente después de completar contraseña y MFA cuando corresponda.
- `auth.login_failed`: credenciales incorrectas, cuenta desactivada/bloqueada, segundo factor ausente/incorrecto y configuración MFA requerida. El intento fallido se confirma antes de devolver el error. La ausencia de MFA no incrementa el contador de contraseñas/códigos incorrectos; la política de bloqueo no cambia.
- `ticket.conversation_read`: cada respuesta correcta de GET `/api/v1/admin/support/tickets/{ticket_id}/replies`, incluida una página vacía. Guarda ticket, actor y página consultada. No duplica mensajes ni afirma que la persona leyó el contenido; acredita que la API lo entregó. Recargar o cambiar página registra otra consulta.

Solicitudes que no superan la validación del formato de login no llegan a la verificación de credenciales. No se añade un capturador genérico de respuestas HTTP. Refresh/logout, listas, clics y abrir el menú no generan eventos nuevos. El ruido histórico de clics/HTTP permanece fuera de listado/exportación, sin borrarlo físicamente.

Actor identificable: UUID, nombre y rol son una fotografía del momento, sin ForeignKey que obligue a borrar o modificar la auditoría al eliminar una cuenta. Un correo desconocido no se almacena como actor inventado. No se pueden reconstruir datos históricos que nunca se guardaron. Eventos automáticos sin petición no garantizan IP/navegador/rol del editor: no inventarlos ni confundirlos con una petición humana.

Se conserva IP de `request.client` y user-agent limitado a 300 caracteres. Tras un proxy debe configurarse la confianza de Uvicorn únicamente para proxies conocidos; no se acepta ciegamente una cabecera proporcionada por el cliente como prueba de IP.

## Consulta

Solo admin. Se conservan GET `/api/v1/admin/audit-log` y `/audit-log/export`; no hay operaciones HTTP para editar/eliminar auditoría ni endpoint de eventos arbitrarios desde el navegador.

Filtros: actor_id, action, entity_type, entity_id, date_from, date_to y q. UUID de actor también permite cuentas eliminadas. La búsqueda libre contempla nombres/acciones/módulos y nombres visibles del registro, no el JSON entero de campos potencialmente sensibles. Listado con orden estable fecha/UUID, páginas 1+, tamaño 1–100. Exportación conserva filtros, admite hasta 5000 filas y protege celdas CSV frente a fórmulas.

- Sin fechas: últimos 30 días hasta la hora de consulta.
- Solo fecha final: 90 días anteriores a esa fecha.
- Solo inicial: desde esa fecha hasta la hora de consulta; más de 90 días se rechaza.
- Ambas: como máximo 90 días exactos. Superior → `RANGE_TOO_WIDE`; invertido → `INVALID_DATE_RANGE`, ambos 422.
- Fechas interpretadas/comparadas en UTC; entradas sin zona heredadas se interpretan UTC. La consola recibe hora local y la convierte a ISO UTC. Puede consultarse cualquier tramo histórico de hasta 90 días; el límite no elimina registros antiguos.

Se muestran actor histórico, acción comprensible, recurso, diferencias cuando corresponda, fecha, IP, navegador y resultado/motivo de acceso. No se presentan rutas técnicas HTTP como descripción de la actividad. Un resultado sin coincidencias es listado vacío, no un fallo.

## Secretos

`audit()` enmascara recursivamente claves de contraseñas/hashes, tokens, códigos MFA/recuperación, QR, claves SMTP/Gemini/cifrado/JWT. La respuesta vuelve a enmascarar registros heredados. `event_metadata` solo admite outcome/reason/page/page_size; no se copian cuerpos HTTP, cabeceras de autorización ni mensajes de soporte.

El enmascarado por nombre de campo no reconoce automáticamente un secreto pegado dentro de una frase libre. Los servicios deben enviar snapshots seleccionados y nunca copiar un payload completo; las notas de negocio autorizadas siguen siendo datos restringidos a admin. La publicación editorial conserva su referencia de versión, sin duplicar todos los textos en auditoría.

## PostgreSQL y arranque

Migración **0011** añade `audit_log.event_metadata` nullable y un trigger que rechaza UPDATE/DELETE/TRUNCATE con SQLSTATE 42501, también ante errores de operación del propietario. No reescribe ni elimina eventos. SQLite verifica la columna/conservación, pero no implementa permisos PostgreSQL.

Compose conserva la secuencia migraciones → bootstrap → seed seguro `--only-empty`. Después ejecuta `python -m scripts.run_api`, que:

1. Usa brevemente la conexión propietaria existente para crear/configurar un login reservado `agecare_api_<hash de base>`, sin privilegios de superusuario, creación de bases/roles, membresías ni propiedad de tablas/esquemas/bases.
2. Da SELECT/INSERT en auditoría; ninguna autorización UPDATE/DELETE/TRUNCATE/TRIGGER. Da DML habitual en las tablas de negocio y solo consulta de alembic_version. No concede DDL. Revoca permisos públicos sobre auditoría y CREATE público en el esquema public de esta base.
3. Comprueba la defensa de 0011 y los permisos efectivos; si falla, no inicia la API silenciosamente como propietario.
4. Genera una contraseña aleatoria interna y arranca Uvicorn con esa conexión limitada en el entorno del nuevo proceso. No escribe ni imprime la clave; no cambia `.env`, JWT, cuentas de consola ni `ADMIN_ENCRYPTION_KEY`.

Desde la carpeta del backend:

```powershell
docker compose up -d --build api
```

No hace falta añadir variables ni borrar volúmenes. Este cambio debe recibirse junto con migración, script y Compose. No iniciar Uvicorn directamente con la conexión propietaria para afirmar permisos limitados. Para ejecución local fuera de Docker: aplicar migraciones con propietario y ejecutar `python -m scripts.run_api` en lugar de Uvicorn directo.

El arranque requiere que el propietario pueda crear/configurar roles (el PostgreSQL local de Compose lo permite). Para un proveedor que no lo autorice, un responsable de BD debe preparar credenciales separadas y los permisos equivalentes; no sustituir este control por un rol con privilegios totales. El script está diseñado para **una API del Compose de desarrollo**: cambia la contraseña interna en cada arranque. Varias réplicas requieren un login estable gestionado aparte, no ejecutar esta rotación concurrentemente. Los administradores reales de PostgreSQL siguen teniendo capacidad de alterar esquema/restaurar respaldos; no se presenta como evidencia criptográfica contra el propietario del servidor.

## Retención

Se conserva **al menos dos años**, sin vencimiento ni limpieza automática. La API no tiene DELETE ni siquiera para eventos anteriores: en esta entrega permanecen más tiempo. La prueba conserva un evento de más de 800 días. No se incorpora un job que purgue al cumplir dos años. Un eventual archivo/purgado y sus permisos deben diseñarse aparte; no se concede esa capacidad a la API.

Respaldos y recuperación del servidor deben gestionarse al desplegar; esto no añade un sistema de backup ni garantiza conservación si un operador destruye el volumen. El seed destructivo sin `--only-empty` dejará de poder borrar auditoría por el trigger; no deshabilitarlo para volver a cargar demos. El arranque normal solo usa el seed seguro.

## Verificación y límites

`tests/test_phase17_audit.py`: accesos, rechazo MFA/recuperación, política de fallos intacta, consulta sensible, identidad eliminada, secretos, rangos/valores por defecto y roles. `tests/test_audit_migration.py`: legado SQLite. `tests/check_audit_postgres.py`: exclusivamente base vacía `agecare_audit_check_*`, migración idempotente, permisos efectivos y rechazo de modificaciones/DDL, login correcto/fallido bajo cuenta limitada, conservación histórica y limpieza de rol de prueba. Las pruebas no usan SMTP ni Gemini.

La API/base habitual no se reinició ni migró durante el desarrollo. Falta aplicar la entrega y revisión visual del usuario; las pruebas de PostgreSQL se hicieron en base temporal eliminada al terminar.
