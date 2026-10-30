# Usuarios y pacientes de demostración

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
