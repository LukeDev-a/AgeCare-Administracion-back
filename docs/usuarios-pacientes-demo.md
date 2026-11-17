# Usuarios y pacientes de demostración

## Coherencia para presentación — 17nov2026, migración0020

Usuario pide resolver la confusión de Carmen Soto y revisar todos los ejemplos. El conjunto actual conserva32 cuentas, añade una ficha hasta8 adultos mayores y tiene19 vínculos. Se mantienen todas las cuentas, UUID de fichas anteriores y vínculos previos. Las cantidades7/14 citadas más abajo son históricas.

| Adulto mayor | Cuenta propia y rol | Otras personas del círculo |
|---|---|---|
| Pedro Silva | Pedro Silva · Adulto mayor | Ana González · Familiar; Carlos Muñoz · Cuidador; María Torres · Médico |
| José Ramírez | José Ramírez · Adulto mayor | Ana González · Cuidador; Lucía Herrera · Familiar |
| Carmen Soto | Carmen Soto · Adulto mayor | Carlos Muñoz · Cuidador; María Torres · Médico |
| Rosa Valdés | Rosa Valdés · Adulto mayor | Miguel Rojas · Familiar; Eduardo Sanhueza · Cuidador (cuenta inicialmente inactiva) |
| Manuel Espinoza | Manuel Espinoza · Adulto mayor | Isabel Castro · Familiar |
| Teresa Aguilera | Teresa Aguilera · Adulto mayor | Andrés Fuentes · Familiar |
| Sergio Vidal | Sergio Vidal · Adulto mayor | Sin otras personas vinculadas |
| Elvira Paredes | Sin cuenta propia | Elena Morales · Familiar |

Una cuenta propia y una ficha pueden compartir nombre porque representan a la misma persona; el vínculo self tiene rol elder. No vincular personas por coincidencia textual de nombres en futuras fuentes reales: estos ejemplos usan UUID explícitos. Rol por vínculo y responsable del círculo son conceptos separados; una misma persona puede tener roles distintos en otros círculos.

0020 solo corrige Carmen cuando coinciden UUID, nombre/correo original y vínculo family/is_owner original. Añade cuatro vínculos propios faltantes y la ficha de Elvira con familiar Elena, únicamente sobre identidades originales conocidas. Conserva nombres/correos editados, roles cambiados, pares ya existentes y colisiones de UUID/nombre; es idempotente. No modificar0017 ni reconstruir el seed sobre bases pobladas. El seed para instalaciones vacías coincide con el resultado nuevo. Downgrade no borra los vínculos ni restaura el rol incorrecto. No cambia esquema ni cuentas/pagos/permisos/sesiones; sin integración móvil real ni envíos.

Validación:34 pruebas dirigidas de API/directorio/migraciones/pagos aprobadas. Docker local0020,32cuentas/8fichas/19vínculos,7 self elder y Elvira→Elena family; health200. Huellas de todas las cuentas y de todas las suscripciones/cobros idénticas antes/después. Respaldo seleccionado (no base completa) en backups/directory-coherence-local-20261117/before.sql, ignorado por Git/Docker, SHA256E31B70656467AB94EFB0113475E8C6A941EB8BF6E207F418CC0AA0B078531B0E. Sin Neon/push/despliegue. Para publicado queda pendiente migrar hasta0020 y desplegar backend; no requiere frontend nuevo por este ajuste.

## Nombres para la entrega — 16 de noviembre de 2026

Por petición del usuario,0017 renombra las tablas a `app_accounts`, `app_patients` y `app_memberships`. El ORM utiliza AppAccount/AppPatient/AppMembership. No crea otro directorio ni elimina filas: conserva identificadores, vínculos, estados, fechas y motivos. Los párrafos históricos que mencionan demo_app_ describen0012; los nombres actuales son app_. La integración móvil y la revocación real siguen pendientes; se conservan la configuración de habilitación y los indicadores data_origin/deactivation_effect y los eventos de auditoría anteriores.

El seed de instalaciones vacías usa32 nombres de personas y siete pacientes, con correos nombre.apellido@gmail.com. Son identidades ficticias: no acreditan titularidad de esas direcciones ni deben recibir correo.0017 sustituye una cuenta existente solo si coinciden su UUID de ejemplo, nombre numerado original y correo example.test original; si se editó, la conserva. En pacientes exige UUID y nombre numerado originales. Si un correo destino pertenece a otra fila o existen tablas origen/destino simultáneamente, rechaza la migración en lugar de fusionar personas. No se borran datos de otros módulos.

Antes de desplegar el backend en Render debe aplicarse `alembic upgrade head` hasta0017 con el rol propietario de migraciones. El rol limitado de la API conserva los permisos al renombrar las mismas tablas. En local, el arranque habitual de Docker aplica las migraciones; no ejecutar seed destructivo ni borrar volúmenes. El cambio de nombres no habilita producción ni conecta identidades externas por sí solo. Esta implementación no ha aplicado0017 a las bases habituales.

Fase 18, 28 de octubre de 2026. El usuario eligió preparar el módulo con demostración e integrar el servicio móvil más adelante. Esta entrega permite probar la administración; **no administra ni revoca sesiones móviles reales**.

## Arranque y uso

Desde la carpeta que contiene el Compose del backend:

```powershell
docker compose up -d --build api
```

El arranque aplica 0012, mantiene bootstrap y seed `--only-empty` y prepara el login PostgreSQL limitado de fase 17. No requiere regenerar ninguna clave ni borrar datos/volúmenes. La API habitual no se inició ni migró durante el desarrollo.

Como admin, abrir **Operación → Usuarios y pacientes** (`/usuarios-app`). La vista ofrece dos pestañas: cuentas de la app y pacientes. `/usuarios` sigue siendo analítica; `/cuentas` continúa siendo personal interno.

La demostración contiene 32 cuentas, 7 pacientes y 14 vínculos. Hay cuentas sin vínculos, un paciente sin miembros, una cuenta inactiva inicial y una persona con distintos perfiles según el paciente. Los nombres son ficticios y los correos usan example.test, un dominio de prueba; no son credenciales para iniciar sesión.

Se puede buscar por nombre/correo y filtrar cuentas activas/inactivas, paginar, consultar detalle y recorrer los vínculos. En pacientes, la búsqueda por correo corresponde a una **cuenta vinculada**, sin duplicar al paciente cuando varios miembros coinciden. Una ficha de paciente no implica una cuenta de acceso propia. No se muestran historia clínica, prescripciones ni notas de salud.

Para desactivar: abrir detalle de la cuenta, pulsar «Desactivar cuenta de prueba», indicar motivo recortado de 5–500 caracteres y marcar la confirmación. El diálogo muestra nombre/correo, no se cierra al pulsar fuera y conserva texto/error si el guardado falla. No hay reactivación, creación, edición, borrado ni reenvío de invitaciones en este módulo.

## Fuente y configuración

Los datos viven exclusivamente en `demo_app_accounts`, `demo_app_patients`, `demo_app_memberships`. Sus modelos DemoEndUser/DemoPatient/DemoPatientMember están separados de AdminUser, AnalyticsAccount y de las futuras identidades móviles canónicas. No almacenan contraseñas, tokens ni sesiones móviles.

- `ADMIN_END_USERS_DEMO_ENABLED=true`: habilita la demostración **solo con ADMIN_ENVIRONMENT=dev**. Compose dev lo activa por defecto. Fuera de Compose su valor predeterminado es false.
- `ADMIN_SEED_DEMO_ENABLED=true`: permite la carga automática segura, incluido este grupo demo. Compose ya lo habilita por defecto.
- Si la demostración está apagada o el entorno es distinto de dev, la API responde 503 `END_USERS_UNAVAILABLE`, después de comprobar autenticación/permisos. Apagar la demostración no conecta un servicio real ni elimina sus ejemplos almacenados.

El seed solo carga este directorio si las tres tablas están completamente vacías. Si cualquiera tiene un registro, conserva todo el grupo: no reactivará cuentas, sobrescribirá motivos ni rellenará una instalación parcial al reconstruir Docker. Usa bloqueo transaccional PostgreSQL para evitar duplicados si dos cargas ocurren a la vez. No importa personas de mocks Flutter, tickets ni métricas.

## Contrato implementado

Prefijo `/api/v1/admin`; permiso específico `end_users`, solo admin tanto en READ como en WRITE. Los otros cuatro roles reciben 403; sin sesión, 401. Usar apiFetch compartido desde la consola; no entregar credenciales administrativas a la app móvil.

| Método y ruta | Resultado |
|---|---|
| GET `/end-users` | q por nombre/correo, is_active opcional, page/page_size (máximo100); lista/total del mismo filtro. |
| GET `/end-users/{user_id}` | Identificación/estado y membresías con patient_id/patient_name/role/is_owner, más motivo/fecha demo si existe. |
| GET `/patients` | q por nombre o correo de miembro vinculado; páginas y total sin duplicados. |
| GET `/patients/{patient_id}` | Identificación mínima y círculo de cuidado con cuenta/rol/is_owner/estado. |
| POST `/end-users/{user_id}/deactivate` | confirmation_user_id coincidente y reason de 5–500, sin campos extras. Cambia solo cuenta ficticia, conserva vínculos. |

Respuestas de listas/detalles y de modificación identifican `data_origin="demo"` y `deactivation_effect="demo_only"`. La modificación devuelve además `mobile_sessions_revoked=false`. La consola rechaza procedencias incompatibles en lugar de presentarlas como una integración real.

Desactivar toma bloqueo de fila y revalida estado; repeticiones devuelven 409 `ACCOUNT_ALREADY_INACTIVE`. Confirmación distinta recibe 422 `CONFIRMATION_MISMATCH`; datos inválidos no modifican estado ni auditoría. Cuenta inexistente: 404. Estado/fecha/responsable/motivo y evento demo se confirman en la misma transacción antes de responder; no se revocan AdminSession ni sesiones externas. No hay cascada que desactive a miembros del círculo o elimine al paciente.

## Auditoría

Eventos explícitos `end_users.demo_list`, `end_users.demo_read`, `patients.demo_list`, `patients.demo_read` y `end_users.demo_deactivate`, con etiquetas que indican prueba/demostración. Listados guardan página/tamaño, sin copiar búsqueda, correos ni resultados. Detalles guardan identificador del recurso, sin copiar miembros ni información de salud. Desactivación guarda estado anterior/posterior y motivo; no escribir contraseñas/códigos/datos de salud en ese texto libre. Se mantiene política de fase17 y actor histórico sin FK. La tabla de auditoría sigue protegida; no se cambia su integridad para permitir la demo.

## Integración real pendiente

Los documentos móviles aportan users/refresh_tokens/patients/patient_members y AGE-208, pero no son código de un servicio integrado. No renombrar tablas demo ni convertir UUID ficticios en identidades reales. Antes de habilitar una fuente real hay que conciliar modelo/contrato, autenticación administrativa del servicio y revocación atómica de login, refresh y access JWT existentes. Revocar solo refresh no cumple RF18.03. Un timeout remoto no acredita éxito.

La fase permanece abierta por integración móvil; la aceptación visual del alcance demo se registra aparte. No añadir operaciones de salud, cambios de perfiles/planes, borrado, reactivación ni reenvío de invitaciones del plan de referencia sin acuerdo adicional.

## Evidencia

355 pruebas backend completas y 110 frontend aprobadas, más comprobaciones posteriores de auditoría/listados y seed seguro. Build y lint de los archivos del módulo aprobados. SQLite cubre migración/contrato/roles/rollback; pruebas de frontend usan renderizado y lógica, sin acreditar navegador E2E.

`tests/check_end_users_postgres.py` se ejecutó en PostgreSQL temporal aislado: 0012 idempotente; carga concurrente sin duplicados; desactivación simultánea 200/409 con un único evento; relaciones, personal, sesiones internas e historial conservados; compatible con el login limitado de fase17. Contenedores/red/rol/base temporales eliminados, sin puertos publicados ni volumen persistente. Servicios/base habituales intactos. No se enviaron correos ni consumió IA.
