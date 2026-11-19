# Render + Neon — demostración de AgeCare

## Neon migrado hasta0022 — 19nov2026

Por autorización explícita del usuario, scripts.migrate_neon_0022 comprobó0021,45tablas incluidaversión,TLS verificado y auditoría protegida; tras7pruebas aisladas aplicó0021→0022 en transacción. Creó analytics_usage_accounts/analytics_usage_sessions e índices,ambasvacías. Huellas de44tablas existentes idénticas antes/después en la transacción:32cuentas/8adultos/19vínculos,32suscripciones/64cobros,6contenidos/20candidatos,30juegos,254tickets,configuración y auditoría conservados. No seed,copia de datos locales,correos,proveedores ni rotación de secretos.

SELECT/INSERT/UPDATE/DELETE concedidos solo en las dos tablas nuevas al rol limitado ya existente. check_database del códigohead0022 y consulta real con runtime correctos,TLS/auditoría intactos; perfiles privados sin modificar. Respaldo cifrado de revisión/huellas (no copia completa de filas) en backups/neon-schema-0022-20261119T144109882316Z/before.enc, reporte agregado report.json con transaction=committed/runtime_verified=true. Total resultante47tablas incluidaversión.

Pendiente:push/despliegue backendhead0022 por usuario y luego frontendVercel. No reiniciar imagen viejahead0021 contra esquema0022; actualizar código. Esta operación NO prepara las sesiones sintéticas de actividad/adopción en Neon; usage_data_prepared=false, tablasvacías,marker sincrear. Activarflag por sí solo no preparaelconjunto. Preparación remota requiere procedimiento específico revisado; scripts.prepare_usage_demo es solo local y debe seguir rechazando Neon. Este apartado supera pendientes históricos de migración0022,pero no acredita despliegue.

## Monitoreo: Neon actualizado hasta0021 — 18nov2026

Autorizado por usuario para comenzar el despliegue conservando Neon. scripts.migrate_neon_0021 (sin flag solo consulta) comprobó0020, TLS verificado y protección de auditoría. Después de36 pruebas aisladas, --apply añadió tabla ops_observations, constraints e índices en una transacción y verificó huellas de43 tablas previas sin cambios. Se conservan30juegos,32cuentas/8adultos/19vínculos,32suscripciones/64cobros y6contenidos. No se copió información local ni se ejecutó seed.

Permisos SELECT/INSERT/UPDATE/DELETE de tabla nueva concedidos al rol limitado existente; check_database del runtime correcto, auditoría SELECT/INSERT y trigger intactos. Perfiles privados sin modificar y secretos sin rotar. before.enc en backups/neon-schema-0021-20261118T232916453687Z contiene revisión/huellas cifradas: no es copia completa de datos. report.json conserva evidencia agregada del commit y verificación.

No se hizo push ni despliegue. Ahora subir backendhead0021 y desplegar Render, después frontendVercel. El código viejohead0020 puede rechazar un arranque con el esquema0021; no revertir la base, actualizar el código. ADMIN_OPS_MONITOR_ENABLED=true por defecto; conservar los otros valores remotos. Las observaciones empezarán a acumularse con el backend nuevo activo, sin importar historial local. Revisión visual pública pendiente tras desplegar.

## Directorio migrado a0017 — 16 de noviembre de 2026

Usuario autorizó aplicar las migraciones a Neon. Consulta previa confirmó0016,32 cuentas,7 pacientes y14 vínculos;25 pruebas dirigidas aprobadas antes de aplicar. scripts.migrate_neon_0017 --apply ejecutó0017 en una transacción: renombró demo_app_accounts/demo_app_patients/demo_app_memberships a app_accounts/app_patients/app_memberships y sustituyó únicamente las32 identidades y7 nombres de paciente originales que coincidían con el catálogo de ejemplo. UUID, estados, fechas, vínculos y demás campos comparados completos con el resultado previsto;0 relaciones huérfanas. Las38 tablas restantes, incluida configuración/cuentas administrativas/colas/auditoría, conservaron sus huellas dentro de la operación.

Respaldo cifrado de las tres tablas del directorio, revisión previa, permisos y manifiesto en backups/neon-schema-0017-20261116T172641927183Z/before.enc; reporte agregado en report.json. No es un respaldo completo de las otras tablas. Conservada la clave de cifrado y los perfiles privados, sin envíos de correo ni seed. ACL del directorio conservadas; comprobación posterior con rol limitado de Render aprobó head0017, lectura/DML de las tablas renombradas y protección inmutable de auditoría. No se ejecutó la API ni se reinició Render: se verificaron sus condiciones de base de datos.

**Siguiente paso: push del backend por el usuario y comprobar el despliegue de Render.** El código anterior del directorio utiliza los nombres antiguos y debe actualizarse junto con esta migración. No se crearon commits ni se publicaron cambios. La integración móvil continúa pendiente; estos registros siguen siendo ficticios y sus direcciones de ejemplo no autorizan correos. Las menciones históricas a0017 pendiente quedan superadas.

El procedimiento nuevo admite solo0016→0017 o comprobación de0017; sin --apply solo consulta. Ante diferencias no previstas revierte la transacción. Si una comprobación posterior al commit falla, informa la fase y requiere revisión: no promete reversión automática después del commit.

## Migraciones aplicadas a Neon — 12 de noviembre de 2026 (Santiago)

Usuario autorizó al agente las migraciones/permisos y reservó los push para sí. Neon estaba en0014; aplicadas0015 y0016 en una transacción con bloqueo, timeout y comprobación de preservación. Concedido SELECT/INSERT/UPDATE/DELETE únicamente sobre admin_mfa_recoveries y mfa_recovery_emails al rol limitado existente. check_database con esa credencial aprobó head0016, ausencia de privilegios elevados/propiedad/DDL y auditoría solo SELECT/INSERT con trigger inmutable. Ambas tablas nuevas tienen0 filas; no se enviaron correos ni se configuró MFA de nadie.

Conservadas las huellas/filas de38 tablas anteriores de negocio, y las3 filas originales de system_settings completas, incluidas sus versiones. Nuevas claves feature_flags/system_texts incorporadas sin sobrescribir valores; disponibilidad inicial habilitada y aviso oculto. Perfiles privados .env/.env.render/.env.render-mail idénticos antes/después, sin rotar credenciales ni clave MFA. Respaldo **de configuración y revisión anterior**, cifrado con la clave estable, más manifiesto de preservación/reporte en backups/neon-schema-0016-20261113T002902265990Z (sufijo UTC; operación del12 en Santiago). No es un dump completo de la base. Archivos excluidos de Git/Docker.

Procedimiento reproducible scripts.migrate_neon_0016: sin --apply solo consulta; con --apply verifica mismo destino propietario/limitado, TLS real del cliente, revisión admitida y head local0016, guarda respaldo cifrado, aplica solo0015/0016 y concede permisos acotados. No usar scripts.prepare_render para esta operación: no se necesitan cambios de rol ni perfiles. pg_stat_ssl refleja el tramo interno del proxy Neon y no acredita el TLS del cliente; la comprobación inicial se detuvo sin cambios por esa lectura, corregida verificando transporte/certificado del cliente antes de aplicar.

**Ahora corresponde al usuario hacer push del backend**, esperar despliegue correcto de Render y luego push del frontend/Vercel. La base está preparada; no se hicieron commits, push, cambios de Environment ni reinicios/despliegues por el agente. Las indicaciones de «0015/0016 pendientes en Neon» siguientes quedan superadas; no se afirma que las rutas nuevas estén publicadas hasta esos push y verificación posterior.

## Actualización de configuración0016 — 12 de noviembre de 2026

La revisión nueva requerida es0016: incorpora claves feature_flags y system_texts, conservando valores existentes. No añade tablas ni permisos sobre system_settings. Aplicar todas las revisiones pendientes mediante la conexión propietaria antes de publicar el backend: si0015 aún está pendiente, también crea sus dos tablas y requiere DML para el rol limitado existente. Mantener permisos de audit_log y credenciales. La aplicación a Neon sigue pendiente; solo se verificó con PostgreSQL temporal. Guía [configuracion-operativa.md](configuracion-operativa.md). La sección anterior en el tiempo que menciona0015 sola describe la entrega MFA previa.

## Recuperación MFA: preparar antes de desplegar — 12 de noviembre de 2026

La entrega añade migración 0015 y dos tablas: admin_mfa_recoveries y mfa_recovery_emails. Todavía no aplicada a Neon. Antes de publicar el backend, migrar por separado mediante la conexión propietaria y otorgar DML de ambas al rol limitado existente; no elevar el rol de Render ni alterar restricciones de audit_log. run_render exige head y rechazará arrancar hasta aplicar 0015. No nuevas variables: conserva clave MFA, proveedor de correo, worker habilitado y URL pública de frontend. Después publicar frontend con /recuperar-mfa y probar con dos cuentas de prueba. Procedimiento y alcance en [recuperacion-mfa.md](recuperacion-mfa.md). No se hicieron operaciones remotas en esta entrega.

## Publicación verificada — 10 de noviembre de 2026

Usuario indicó que completó los pasos. Verificación pública de solo lectura confirmó salud200, OpenAPI con request/confirm de recuperación y preflight POST200 con el origen Vercel exacto. Frontend y bundle accesibles, con pantalla de recuperación y rutas nuevas apuntando a Render. Sin credenciales, solicitudes de recuperación ni correos reales durante la verificación. Recepción desde Render y cambio real de contraseña pendientes de prueba del usuario con una cuenta propia. El orden de preparación siguiente queda como referencia del despliegue realizado.

## Actualización preparada — 10 de noviembre de 2026

Neon migrado de 0013 a 0014 en transacción, con bloqueo y comprobación del destino propietario frente al perfil limitado existente. Añadida únicamente la tabla de recuperación y concedido SELECT/INSERT/UPDATE/DELETE sobre ella al rol limitado de Render. Cantidades de cuentas y juegos conservadas, cola nueva vacía. check_database del perfil limitado aprobó revisión y protección de auditoría. No se cambiaron claves, contraseñas ni cuentas ni se enviaron correos durante esta operación.

El archivo local privado `.env.render-mail`, ignorado por Git y Docker, contiene las cinco variables a añadir o actualizar en Render. Copiar su contenido desde el editor mediante Environment → Add from .env. Mantener las demás variables actuales. El archivo incluye la clave real de Brevo, por lo que no debe publicarse ni pegarse en el chat.

| Variable | Valor o procedencia |
|---|---|
| ADMIN_MAIL_PROVIDER | brevo |
| ADMIN_BREVO_API_KEY | Clave privada de Brevo ya validada localmente |
| ADMIN_MAIL_FROM | Remitente verificado indicado por el usuario |
| ADMIN_MAIL_WORKER_ENABLED | true |
| ADMIN_FRONTEND_URL | https://age-care-administracion-front.vercel.app |

Orden para completar el despliegue.

1. Subir el backend a su repositorio y esperar que Render despliegue el código con migración 0014. La migración ya está aplicada en Neon y no se pone Alembic en Docker Command. El código anterior espera 0013 al reiniciar, por lo que completar este paso antes de redesplegarlo con nuevas variables.
2. Subir el frontend y esperar el despliegue de Vercel. Conservar su VITE_API_BASE_URL actual, que apunta a Render con el prefijo /api/v1/admin.
3. Importar `.env.render-mail` en Environment del servicio Render y guardar con redespliegue para activar el correo con el código nuevo. Conservar Dockerfile.render, Docker Command y /health actuales.
4. Verificar recuperación desde el login público con correo registrado y accesible, enlace que abre Vercel, cambio de contraseña y MFA habitual. Probar una invitación y, si se desea, un incidente nuevo cuyos avisos se dirigen a cuentas activas admin/support.

Los datos comerciales de demostración añadidos localmente no se copian por hacer push. Su carga en Neon requiere una operación separada. El worker editorial/audio conserva las limitaciones de almacenamiento del plan gratuito, detalladas más abajo. Esta preparación no acredita envío desde Render ni actualización de la interfaz pública, pendientes de completar los pasos anteriores. Los párrafos históricos que indican correo pendiente de integración HTTPS quedan superados por Brevo implementado y probado localmente.

## Conexión Vercel pendiente de confirmar

Frontend público: https://age-care-administracion-front.vercel.app. HTML/JS accesibles y bundle contiene API Render correcta. Preflight OPTIONS desde ese origen agotó timeout30s; todavía sin evidencia de CORS autorizado/login público. Perfil LOCAL .env.render actualizado únicamente en ADMIN_ALLOWS_ORIGINS (Vercel + los dos orígenes locales5173) y ADMIN_FRONTEND_URL (Vercel). Aplicar mismos valores en Render/Environment y desplegar; no reimportar secretos ni regenerarlos. Verificar después OPTIONS y flujo del usuario. No se cambió configuración remota mediante herramientas.

## Servicio publicado — 30 de octubre de 2026

Usuario desplegó desde el repositorio elegido; captura indica Deploy succeeded/Live. URL https://agecare-administracion-back.onrender.com. Comprobación externa por HTTPS sin credenciales: /health status ok; /api/v1/admin/games-apps/active devuelve11 juegos activos, direcciones propias HTTPS correctas; HEAD de juego propio con Origin null devuelve200 y Access-Control-Allow-Origin:*. Sin cambios en datos ni login. Los404 de / en los logs son esperables: la API no tiene portada. Todavía pendientes frontend Vercel, CORS con su origen real, ADMIN_FRONTEND_URL y login/MFA públicos. Los párrafos de «todavía no publicado» siguientes describen la preparación inicial; el agente no hizo commits/push ni pulsó el despliegue.

30 de octubre de 2026. Usuario eligió el repositorio LukeDev-a/AgeCare-Administracion-back, rama local main, Render Virginia y Neon Virginia. Datos ya copiados y verificados en Neon. Todavía no se ha publicado el servicio ni se han hecho commits/pushes por el agente.

## Preparación realizada

- Dockerfile.render usa python -m scripts.run_render y el puerto PORT de Render. No modifica Dockerfile/Compose local, ni migra, ni ejecuta seed/bootstrap al iniciar.
- app/database_urls.py adapta la URL libpq de Neon a asyncpg, con SSLContext de CA del sistema, hostname y cadena verificados. Alembic y los motores de aplicación/preparación usan el mismo criterio TLS. Se escapa % en ConfigParser de Alembic para contraseñas URL-encoded. La conexión local sigue igual.
- python -m scripts.prepare_render prepara el rol SQL limitado usando la conexión propietaria local NEON_MIGRATION_DATABASE_URL. Guarda una sola vez la contraseña SQL estable, un JWT propio nuevo y la MISMA ADMIN_ENCRYPTION_KEY original en .env.render, ya excluido de Git y de Docker. El propietario nunca se pone en ese archivo de despliegue. No regenerar claves MFA ni solicitar sus valores en el chat.
- La preparación repetida autentica primero la credencial SQL existente y no la rota; no cambia JWT ni claves MFA. Las concesiones de negocio y SELECT/INSERT de auditoría se confirman en una transacción. La variante Compose sin stable_password conserva su comportamiento previo de contraseña aleatoria por inicio.
- run_render comprueba rol sin privilegios elevados/membresías/propiedad/DDL, permisos y trigger de auditoría, revisión Alembic y configuración pública antes de abrir HTTP. Falla cerrado sin imprimir entradas privadas ni SQL.

## Decisión explícita sobre contraseñas

El preparador detectó cuatro cuentas activas con contraseñas conocidas de desarrollo. Usuario indicó: «no quiero modificar las contraseñas de ninguna cuenta». No se cambiaron/desactivaron cuentas ni MFA. Se preparó la excepción explícita ADMIN_RENDER_ALLOW_DEV_CREDENTIALS=true con ADMIN_ENVIRONMENT=dev, únicamente para esta demostración. En staging/prod se rechaza esa excepción. Fuera de ella, run_render rechaza contraseñas públicas de desarrollo. No confundir esta autorización con una recomendación de producción ni con permiso para desactivar MFA.

Para conservar esa decisión al repetir la preparación local:

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_render --allow-dev-credentials
```

Ese comando necesita conexión directa propietaria local y permisos para preparar el rol; no forma parte del arranque Render ni se coloca en su Docker Command. El .env local no se modifica. No mostrar los secretos del archivo generado ni copiarlos a Vercel.

## Crear Web Service en Render

Primero subir a GitHub los cambios revisados del backend, incluidos todos los nuevos módulos que importa app.main y el Dockerfile.render. No se hicieron commits/pushes durante esta preparación.

| Campo | Valor |
|---|---|
| Repositorio | LukeDev-a/AgeCare-Administracion-back |
| Branch | main |
| Name | agecare-api, o nombre disponible |
| Region | Virginia |
| Language/Runtime | Docker |
| Root Directory | Vacío si el repositorio ya comienza con app/, scripts/, requirements.txt y Dockerfile.render |
| Dockerfile Path | ./Dockerfile.render |
| Docker Build Context | . |
| Docker Command | Vacío: usa el CMD del Dockerfile.render |
| Health Check Path | /health |

En Environment, usar Add from .env y pegar el contenido del archivo privado .env.render desde el editor local. No pegarlo en el chat ni subir el archivo a GitHub. Las comillas pertenecen al formato dotenv: usar el importador .env. Docker CLI --env-file tiene otra interpretación; la comprobación local usó dotenv y variables de entorno heredadas sin valores secretos en argumentos.

El archivo contiene una configuración de demostración con bootstrap/seed y workers de correo, Gemini y analítica apagados. End-users demo permanece explícitamente como demo, sin revocación móvil real. No se copiaron audios del volumen local.

Render provee RENDER_EXTERNAL_URL; si ADMIN_GAME_PUBLIC_BASE_URL está vacía, run_render usa esa raíz HTTPS para las direcciones de juegos. Al conocer el dominio definitivo también puede configurarse explícitamente esa variable. No incluir /static/juegos ni /api/v1/admin.

Mientras se publica Vercel, el perfil permite los orígenes locales 5173. Después establecer ADMIN_ALLOWS_ORIGINS con el origen Vercel exacto (sin / final), y ADMIN_FRONTEND_URL con la URL de la consola que implementa invitación/enrolamiento MFA. Actualizar VITE_API_BASE_URL en Vercel con raíz Render + /api/v1/admin y recompilar frontend. No autorizar null ni comodines globales.

## Plan gratuito y correo

Render Free suspende servicios inactivos, no dispone de disco persistente y bloquea salida SMTP por 25/465/587, incluido Gmail STARTTLS. El perfil deja correo apagado; no afirmar que invitaciones se enviarán desde Free. Para mantener Gmail se requiere un servicio que permita ese tráfico; alternativamente integrar un proveedor por HTTPS en trabajo posterior autorizado. La generación de audios necesita almacenamiento persistente antes de habilitarse. Los juegos incluidos en la imagen no requieren subirlos a un disco de datos.

## Validación y límites

- Suite backend completa: 376 pruebas aprobadas antes del último ajuste de excepción demo; 26 seleccionadas de Render/auth/bloqueo aprobadas después. Warnings existentes por JWT corto únicamente en fixtures de tests.
- Preparador ejecutado dos veces sobre Neon: credencial estable autenticada sin rotar, esquema al día, rol limitado y auditoría SELECT/INSERT confirmados; ninguna cuenta ni dato de negocio modificado.
- Imagen Docker construida. Contenedor temporal sin puertos publicados: arranque con Neon y PORT=10000, /health correcto, 11 juegos activos, URLs locales reescritas a HTTPS y HEAD con Origin null devuelve200/ACAO:* para iframe. Confirmada ausencia de .env, .env.render y backups/ en la imagen. Contenedor de prueba detenido y eliminado automáticamente, API local no reiniciada. Esto no acredita acceso público ni CORS contra un dominio Vercel real.
- Quedan publicación GitHub/Render/Vercel, comprobación de login/MFA en el dominio real, política de confianza de proxies para IP de auditoría y decisión de correo/almacenamiento según plan. No habilitar confianza de proxy universal para inventar una IP de cliente.

## Referencias

- https://render.com/docs/docker
- https://render.com/docs/environment-variables
- https://render.com/docs/free
- https://neon.com/docs/manage/database-access
## Neon actualizado hasta0020 — 17nov2026

Usuario inicia despliegue y elige «Conservar Neon y añadir lo nuevo», sin trasladar cancelaciones/reembolsos locales. Ejecutado scripts.migrate_neon_0020 primero solo consulta y después --apply:0017→0018→0019→0020 en una transacción. TLS propietario/runtime verificados, respaldo seleccionado cifrado y relectura comprobada antes de modificar. Preservados por comparación completa las32cuentas y6noticias, por manifest37otras tablas; directorio8fichas/19vínculos según corrección autorizada. Las dos tablas de pagos nuevas quedan vacías: primera apertura con versión nueva las inicializa una vez desde las cuentas de Neon, sin copiar operaciones locales.

Concedidos SELECT/INSERT/UPDATE/DELETE de tablas de pagos al rol limitado existente, sin rotar credenciales ni otorgar DDL. check_database de Render con head0020 y auditoría protegida aprobado tras commit; acceso runtime a ambas tablas confirmado. Perfiles privados locales conservados por hashes. No seed global, copia total, envíos ni llamadas Gemini, ni cambios de Environment de Render/Vercel. Respaldo/reportes privados ignorados en backups/neon-schema-0020-20261117T181922083853Z; antes.enc incluye directorio/contenido/tablas seleccionadas y manifest del resto, no respaldo completo de base.10 pruebas aisladas de verificador/migraciones/pagos aprobadas antes de ejecutar.

Siguiente paso: el usuario hace push del backend con todos los módulos y migraciones nuevos y espera deploy Render. Un reinicio de la versión antigua puede rechazar ahora el esquema nuevo hasta que llegue el código con head0020; no revertir la base ni quitar la comprobación. Después frontend/Vercel y verificación pública. Para el nuevo avance de analítica demo, revisar en Render dev ADMIN_COMMERCIAL_DEMO_REFRESH_ENABLED=true: no se modificó esa variable en esta operación. No poner URL propietaria/clave de servidor en Vercel.
