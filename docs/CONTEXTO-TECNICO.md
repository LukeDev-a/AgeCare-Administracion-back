# Mapa del backend

## Neon preparado hasta0016 — 12 de noviembre de 2026

Usuario delegó migraciones/permisos, mantiene push a su cargo. Ejecutadas0014→0015→0016 atómicamente mediante scripts.migrate_neon_0016 --apply, después de consultar destino/versiones y verificar TLS del cliente y rol limitado. DML concedido solo en las dos tablas MFA nuevas; check_database de Render aprobó esquema, rol limitado y auditoría protegida.38 tablas anteriores cotejadas sin cambios y3 configuraciones originales conservadas, dos claves nuevas incorporadas y colas MFA vacías. No cambios de cuentas/credenciales/perfiles ni correos. Respaldo cifrado de configuración/revisión y manifiesto/reporte privado en backups/neon-schema-0016-20261113T002902265990Z. No es un respaldo completo de todos los datos. Pendiente push backend por usuario, despliegue Render, luego frontend/Vercel y revisión publicada. Los pendientes de migración Neon anteriores son históricos. Guía docs/render-neon.md.

## Configuración operativa de funciones y avisos — 12 de noviembre de 2026

Implementadas feature_flags (recopilación/adaptación noticias, alcance aprobado) y system_texts (aviso de consola) mediante0016, sin sobrescribir claves. Caché por proceso60s/copia independiente/single-flight/no copia vencida y worker cada5s. PUT settings confirma valor/auditoría y luego invalida copia local; GET admin siempre vigente. Restricciones reales manuales/scheduler/lote automático, sin cortar trabajos aceptados. GET runtime/notice para cuentas autenticadas, content/runtime añade disponibilidad. Seed seguro ajustado para instalar grupo anterior cuando solo existen claves de0016, preservándolas.446 pruebas backend completas y13 dirigidas finales aprobadas; PostgreSQL temporal preservación/TTL/concurrencia aprobado y retirado. Sin servicios/datos habituales tocados. Guía docs/configuracion-operativa.md. Alertas/medicación y consumidores de las claves anteriores pendientes; no declarar RF15 cerrado. Neon debe migrar hasta0016 antes de subir Render;0015 y sus permisos aún pendientes si no se aplicaron después del último reporte.

## Recuperación de acceso MFA — 12 de noviembre de 2026

Flujo implementado por solicitud del usuario: contraseña + confirmación por correo + aprobación/rechazo de otro admin tras comprobar identidad. Dos rutas públicas y dos protegidas, mfa_recovery.py, cola cifrada reutilizando correo existente, modelos nuevos y migración 0015. Aprobación invalida MFA/códigos/sesiones/enrolamientos anteriores, incrementa auth_version y exige enrolamiento nuevo, conserva contraseña/rol. No autoaprobación; pruebas de identidad y reautenticación del revisor obligatorias. Eventos explícitos de auditoría con request_id y motivo. Eliminación de cuentas limpia referencias nuevas. No hay variables adicionales. 440 pruebas backend y 139 frontend aprobadas; migración/concurrencia verificadas en PostgreSQL temporal retirado. No migración local/Neon ni despliegues/correos reales. Antes de Render, aplicar 0015 y DML de tablas nuevas al rol limitado. Guía [recuperacion-mfa.md](recuperacion-mfa.md).

## Unidad de planes y tarifa configurable — 12 de noviembre de 2026

Acuerdo: todos los planes mensuales por cuenta; prestaciones fuera de alcance. PlanRow añade billing_unit=account y billing_period=month como regla fija común, sin migración. Se conserva plan_prices existente, PUT admin, esquema de enteros no negativos, motivo/versionado/auditoría. Seed solo precisa descripción; ningún importe cambiado ni seed ejecutado. 43 pruebas dirigidas settings/commercial_cohorts aprobadas en memoria, incluida actualización de precio que conserva intacta respuesta histórica y rechazo de negativos. No se conecta un proveedor de cobros ni se cambia el origen de los snapshots; integración con suscripciones y TTL de configuración siguen pendientes. Sin migración, reinicio o modificación de bases habituales.

## Limpieza del entorno local — 11 de noviembre de 2026

Por solicitud del usuario, se retiraron del `.env` local ADMIN_SMTP_HOST, ADMIN_SMTP_PORT, ADMIN_SMTP_SECURITY, ADMIN_SMTP_USERNAME y ADMIN_SMTP_PASSWORD porque el proveedor seleccionado es Brevo; SMTP sigue disponible en el código si se configura de nuevo. También se retiró ADMIN_INCIDENT_MAIL_RECIPIENTS, ya ignorada: los destinatarios se calculan según las cuentas activas admin/support. Se conservó NEON_MIGRATION_DATABASE_URL porque scripts.copy_to_neon todavía la utiliza. Las demás líneas y valores se conservaron exactamente, sin regenerar claves, modificar otros perfiles ni reiniciar servicios.

## Programación editorial con requisitos obligatorios — 11 de noviembre de 2026

Cambio acordado: separar guardado incompleto de programación confirmada. content.py rechaza publish_at en creación (REVIEW_REQUIRED) y valida draft/fecha futura/aprobación/procedencia/audio vigente antes de programar por PATCH; rechaza cambios de texto y programación simultáneos sin alterar datos. Cancelación por null conservada. Editar texto ya programado mantiene fecha y bloquea publicación hasta nueva revisión/audio, sin cambios del scheduler. Sin nuevas rutas, columnas ni migración. Doce pruebas tests/test_content.py aprobadas en memoria, sin proveedores reales. Guía docs/contenido-editorial.md. API habitual no reconstruida ni reiniciada; usuario debe aplicar build.

## Demostración comercial cargada en Neon — 10 de noviembre de 2026

Usuario autorizó trasladar la demostración analítica local a la base publicada. Confirmado Neon con 426 días unknown y 18 cuentas analíticas demo, sin conflictos en el rango nuevo. Historial diario cotejado con local, cifras idénticas. Respaldo de siete tablas en backups/commercial-demo-20261110T213637Z con SHA-256, ignorado por Git/Docker. Ejecutado seed_commercial_demo --apply --target neon --complete-legacy-history mediante rol limitado. Confirmados 125 días nuevos, 19.569 cuentas, 15.604 acciones, 2.850 pagos, 28 planes y 18 horas, más clasificación demo de 426 días legados sin cambiar cifras.

Verificación mediante routers con sesiones sobre Neon aprobó mes actual (3.405 descargas, 1.585 altas, 149 bajas), últimos 30 días, año y últimos 12 meses con totales numéricos. Septiembre con 3.921/3.124/413, completo, descargas acumuladas 57.610 y planes de 27.972 usuarios al 10 de noviembre. Datos futuros almacenados siguen fuera del cálculo hasta su fecha. No copia de cuentas internas, reinicios ni acceso a sesión del usuario. Pendiente revisión visual pública por él. Los estados anteriores «solo local» son históricos. Detalles en datos-demo-comerciales.md.

## Preparación de Render — 10 de noviembre de 2026

Usuario pidió preparar Render antes de subir todos los cambios. Perfiles propietario y limitado cotejados sin mostrar secretos. Neon estaba en 0013 y se aplicó 0014 con bloqueo en una transacción, preservando cantidades de cuentas y juegos y dejando cola nueva vacía. Permisos DML de tabla nueva concedidos al rol limitado existente. check_database con esa credencial aprobó revisión y auditoría protegida. Sin cambios de claves ni cuentas ni correos enviados.

Preparado `.env.render-mail` privado e ignorado por Git/Docker con proveedor Brevo, clave local, remitente verificado, worker de correo y URL pública Vercel. Usuario debe subir backend, esperar despliegue del código 0014, subir frontend y luego importar bloque de correo en Render/Environment con redespliegue. No se hicieron commits, push ni cambios remotos de Environment. Carga de demostración comercial local sigue sin copiar a Neon. Corregidas dos expectativas desactualizadas de pruebas de seed de 20 a 30 juegos. Verificación final con 425 pruebas backend aprobadas, además de las 116 frontend y compilación ya verificadas. Los fallos de catálogo mencionados en la entrega anterior quedaron resueltos. Ver docs/render-neon.md para orden y validación real pendiente.

## Recuperación de contraseña por correo — 10 de noviembre de 2026

Usuario autorizó completar recuperación por correo aprovechando Brevo local. Nueva tabla admin_password_resets y migración 0014, módulo password_reset y dos rutas públicas request/confirm. Vigencia de 30 minutos, intervalo de 60 segundos y tres solicitudes aceptadas por cuenta/hora como decisiones de implementación. Respuesta genérica para cuentas inexistentes/inactivas/pendientes/limitadas. Token de un uso con hash SHA-256, correo en cola cifrada, enlace por fragmento, validación del correo original y auth_version. Worker comparte proveedor y bandera de correo, revalida antes de enviar, reintenta cinco veces y notifica cambio exitoso sin credenciales.

Confirmación atómica bloquea cuenta antes de token, cambia hash Argon2id, consume token, revoca sesiones e incrementa auth_version, cierra enrolamientos pendientes y audita. MFA/códigos vigentes conservados, vuelta a login requerida. El borrado de cuentas elimina recuperaciones asociadas. Migración idempotente contempla 0001 que usa metadata actual. PostgreSQL temporal verificó preservación de cuenta, doble confirmación (200/422) y solicitudes simultáneas serializadas, contenedor retirado. Veinte pruebas HTTP/migración/invitaciones aprobadas. Suite general backend con 423 aprobadas y dos fallos ajenos a recuperación en test_seed_empty_modules.py, cuyas expectativas de 20 juegos están desactualizadas respecto al catálogo de 30. No presentar la suite completa como aprobada. Sin migración a base habitual/Neon, reinicios de Docker ni cambios de contraseña reales. Aplicación local vía Compose. Render necesita migración y permisos de nueva tabla antes de desplegar. Guía en invitaciones-mfa.md.

## Correo Brevo HTTPS — 10 de noviembre de 2026

Regla posterior aprobada, destinatarios automáticos para incidentes nuevos y mantenimientos, cuentas activas admin/support con password_hash no nulo. Se retira incident_mail_recipients de Settings; variable antigua del entorno se ignora. Colas ya creadas se revalidan antes de enviar por email, actividad, rol y contraseña; destinatarios que perdieron acceso se cancelan con payload eliminado. No se añaden cuentas nuevas a avisos antiguos. Si todos cancelados, agregado not_configured. Pruebas aisladas verifican roles, pendientes, inactivos, cambio de correo/rol, cancelación y colas. Sin migración ni modificación de cuentas, servicios o datos reales. Aplicación al Docker requiere reconstruir API.

Usuario confirmó recepción del mensaje de prueba y posteriormente del aviso generado al crear incidente desde Docker/consola. Entrega local confirmada por él. Aviso visual seguía queued por selección obsoleta en frontend, corregida con sincronización y consulta periódica de avisos pendientes. Render aún pendiente.

Prueba posterior autorizada por el usuario con su correo como remitente y destinatario. Actualizados únicamente ADMIN_MAIL_PROVIDER=brevo, ADMIN_MAIL_FROM y ADMIN_INCIDENT_MAIL_RECIPIENTS en .env local. Un mensaje de prueba enviado por el transporte compartido desde Python local fue aceptado por Brevo. Entrega en bandeja pendiente de confirmación del usuario. Docker no reconstruido/reiniciado, colas existentes no procesadas en esta prueba. Falta aplicar el código y entorno al contenedor para probar un incidente nuevo desde la consola. El estado de preparación sin modificar .env del párrafo posterior es histórico.

Usuario eligió Brevo y guardó la clave privada. Añadidos mail_provider (smtp predeterminado, brevo explícito) y brevo_api_key. invitation_mail.send_message selecciona transporte para invitaciones y avisos de incidentes. app/brevo_mail usa HTTPS con certificado verificado, timeout20s, endpoint fijo y errores saneados. Colas/estados/reintentos existentes conservados, sin migración. Auditoría enmascara brevo_api_key. Pruebas fijan proveedor SMTP y clave Brevo vacía para aislar credenciales reales.

47 pruebas de transporte, diagnóstico, invitaciones e incidentes aprobadas. Diagnóstico real de solo lectura usando ADMIN_MAIL_PROVIDER=brevo temporal confirmó conexión con Brevo sin envíos. Falta confirmar remitente verificado, destinatario y actualizar selección del proveedor en .env, luego reconstruir Docker de forma autorizada y probar entrega. No se modificó .env, no se reiniciaron servicios ni se enviaron correos. Consultar docs/invitaciones-mfa.md para variables y límites de aceptación frente a entrega. Render pendiente para después de validar local.

## Demostración comercial ampliada — 10 de noviembre de 2026

Corrección posterior del bloque Descargas acumuladas tras captura del usuario. Su suma incluye todo el historial y seguía encontrando unknown en 2025. Añadida --complete-legacy-history al script, con continuidad, bloqueo y rechazo de orígenes reales, conservando cifras/fechas. Aplicado solo local a 186 días restantes del seed de 2025. Tres pruebas aisladas aprobadas. Router verificado devolvió 57.610 descargas acumuladas al 10 noviembre sin aviso de frescura, y Últimos12meses 50.693 descargas/25.446 altas. La limitación previa de historial mixed queda resuelta localmente. Carga Neon continúa pendiente.

Actualización posterior autorizada para Año en curso. Añadida opción explícita --complete-legacy-year que comprueba cobertura enero–28 agosto, bloquea filas y cambia solo data_origin unknown a demo en registros confirmados del seed antiguo. Conserva cifras y computed_at, rechaza orígenes reales. Aplicada solo local a 240 días, sin duplicar colección nueva. Verificación con routers existentes obtuvo 24.363 altas, 2.753 bajas y 48.647 descargas del 1 enero al 10 noviembre, once bloques mensuales con cifras. Dos pruebas aisladas aprobadas. La advertencia previa de Año en curso sin totales queda resuelta en local, persiste como pendiente de operación en Neon. Últimos12meses puede incluir diciembre2025 aún unknown, fuera de este ajuste.

Usuario pidió muchos datos para septiembre a diciembre después del último agosto disponible y eligió probar local, dejando la carga preparada para Neon. Creado script explícito scripts.seed_commercial_demo, con dry-run predeterminado, --apply y destino local/neon. Aplicado únicamente a PostgreSQL local. Rango 29 agosto–31 diciembre 2026, 125 filas diarias, 19.569 cuentas analíticas, 15.604 actividades, 2.850 pagos, 28 filas de planes al corte de hoy y 15 horas completas. Se conservaron las 426 filas históricas unknown y las 18 cuentas demo previas. Diciembre es futuro al momento de carga y no se presenta como actividad observada por la API. Snapshot de planes nunca futuro. Identificadores estables y conflicto de inserción evitan duplicados; transacción, bloqueo PostgreSQL y rechazo de orígenes ajenos a demo en rango. No ejecutar scripts.seed destructivo para este trabajo.

Prueba aislada aprobada y consultas locales de cálculo verificadas. Mes actual obtuvo 1.585 altas/149 bajas/3.405 descargas; últimos30d 4.695/453/9.840. Septiembre embudo 3.921/3.124/413, completo; octubre/noviembre provisionales. Año en curso sigue sin totales comparables por filas unknown anteriores, no darlo por resuelto por la nueva carga. Neon sin cambios en esta tarea, requiere operación explícita posterior. Guía y comandos en docs/datos-demo-comerciales.md.

Cuenta de pruebas solicitada el 4 de noviembre de 2026: administrador@gmail.com, nombre administrador, admin activo, mfa_required=false y mfa_enabled=false, creada y auditada en Neon sin tocar otras cuentas. Contraseña solo archivo privado .env.editor-* ignorado. Excepción nueva ADMIN_MFA_TEST_EXEMPT_ACCOUNT_IDS limitada a UUID explícitos en environment=dev y cuentas sin obligación individual; MFA ya habilitado sigue exigido. Diecinueve pruebas de cuentas/login/invitaciones aprobadas, incluidos aislamiento, refresh y rechazo de excepción en staging/prod. Para uso remoto falta desplegar backend y configurar UUID de esta cuenta en Render; no afirmar acceso sin MFA ya aplicado en Render ni cambiar ADMIN_MFA_REQUIRED_ROLES globalmente. No commits/push/despliegues realizados.

Login, contador de bloqueo (4 de noviembre de 2026): auth.login añade details con locked_until UTC y retry_after_seconds calculado al informar bloqueo, también en el fallo que alcanza el umbral, conservando códigos/status existentes. ACCOUNT_LOCKED ya no fija quince minutos en mensaje. No cambia umbral de cinco, ventana diez minutos ni duración configurada; no migración. Cuatro pruebas aisladas confirman conteo mixto, caducidad, reset y tiempo restante que disminuye sin extender bloqueo. Instalación habitual y Render no se reiniciaron/desplegaron. Frontend necesita estos metadatos para mostrar contador.

## Catálogo original ampliado — 4 de noviembre de 2026

Aplicación remota autorizada posteriormente: el usuario reportó que Render rechazó el arranque por revisión desactualizada. Consulta confirmó Neon 0012 frente a código 0013; usuario autorizó explícitamente aplicar. Migración 0013 ejecutada con credencial propietaria de migraciones conservada localmente y destino cotejado con perfil limitado, en transacción con bloqueo y verificación de fichas: 20 anteriores idénticas, diez nuevas inactivas, treinta totales. Comprobación posterior con rol limitado de Render aprobó revisión 0013 y protección de auditoría. No seed, cambios de cuentas, rotaciones de claves ni migración local; falta reintentar despliegue Render, no afirmar nuevo servicio publicado por esta operación.

Validación: 19 pruebas Node de mecánicas y reinicio aprobadas, diez entradas HTML y sus estilos/scripts locales verificados; 26 pruebas backend de migración no destructiva/idempotencia y disponibilidad aprobadas sobre bases de prueba. No acredita ensayo visual nuevo ni migración PostgreSQL habitual aplicada.

Usuario pidió trasladar los últimos diez juegos al backend original y dejar de trabajar sobre el repositorio de integración. Añadidos sudoku, torres-hanoi, balanza, secuencia-luces, bolos, une-puntos, refranes, dibujo-cuadricula, codigo-secreto y tesoro, con coleccion.json y CSS/JS compartidos. Catálogo original esperado tras migraciones y carga inicial: treinta juegos. Rutas globales originales, sin organización ni autenticación de la API de colegas. Migración 0013 (posterior a 0012) registra únicamente slugs ausentes como inactivos y conserva fichas/estados existentes; downgrade no elimina fichas. Seed seguro incorpora colección separada conservando grupos con datos. No se aplicó a PostgreSQL local/Neon ni se reiniciaron servicios: Compose local aplica migración al reconstruir; Render usa proceso de migración separado existente. No copiar 0008_games de la integración a este backend.

Alta de Max completada el 2 de noviembre de 2026 tras recuperar .env.render: max@gmail.com, nombre Max, admin activo, MFA obligatorio y pendiente de enrolamiento personal. Creación y auditoría operativa confirmadas en Neon mediante acceso limitado; contraseña aleatoria solo en archivo privado .env.editor-* (el prefijo histórico no determina el rol). Sin correo, reinicios ni cambios a cuentas previas. El bloqueo de configuración descrito abajo quedó resuelto. No guardar secretos aquí ni regenerar credenciales.

Alta solicitada de Max (max@gmail.com), admin, el 2 de noviembre de 2026: script operativo admite --role admin explícito, editor continúa como predeterminado; tres pruebas aisladas de hash/MFA/auditoría/duplicados aprobadas. Intento de alta detenido antes de conectar porque falta .env.render local (solo existe .env). No cuenta ni contraseña creada por este intento. Restaurar perfil privado limitado existente para continuar; no regenerar claves MFA/JWT ni acceso SQL por inferencia. No marcar alta realizada ni sustituir por conexión propietaria.

Actualización de curación del 2 de noviembre: clave guardada por el usuario,
ambos modelos accesibles; adaptación real y audio TTS recibidos. Respuesta TTS
usa MIME audio/l16 en minúsculas: corregido content_providers.narrate para admitir
variaciones de mayúsculas y validar tipo, rate, channels y codec; WAV real capturado
verificado sin gastar otra solicitud. 25 pruebas específicas aprobadas. WordPress
responde con texto/autor. No publicación ni cambios en contenido de base habitual;
worker todavía no activado. Usuario debe aplicar flags locales y reconstruir API,
después aceptar flujo visual. Las referencias anteriores a clave vacía son
históricas y resueltas. No mostrar clave ni afirmar cierre del feed móvil.

Curación retomada el 2 de noviembre de 2026: usuario elige Docker local y confirma
Gemini gratuito sin facturación. 16 pruebas específicas aprobadas con proveedores
simulados; check_content_postgres.py comprobado en PostgreSQL 16 temporal
(migración desde tabla anterior, cuotas concurrentes y dos trabajadores sin
audio duplicado), contenedor retirado. Script ahora establece raíz de imports.
Settings carga clave Gemini vacía; usuario debe guardarla sin duplicados en el
archivo privado. No leer/imprimir valor ni habilitar worker automáticamente.
No se llamó a Gemini ni se modificaron entornos/datos habituales. Proveedores
reales, recorrido visual completo e integración móvil siguen pendientes.

Alta operativa autorizada (30 de octubre): scripts.create_editor_accounts creó en Neon dos editores solicitados por el usuario, sin correo ni cambios en cuentas anteriores/local. MFA obligatorio por cuenta, todavía sin configurar, hashes Argon2 y contraseñas iniciales aleatorias distintas en archivos privados .env.editor-* ignorados por Git y Docker. Nunca imprimir/versionar sus valores. CLI default solo consulta; --apply crea altas y auditoría juntas y rechaza duplicados sin reset. Rol editor conserva matriz completa (juegos/contenido/marketplace), no limitar ni ampliar permisos por inferencia. Auditoría staff.create identifica operación local, sin suplantar una sesión admin/actor humano, sin IP inventada. Dos tests aislados aprobados y consulta posterior Neon confirma hashes/MFA, dos eventos y cero invitaciones; primer acceso/MFA queda a los titulares. No nueva ruta ni formulario frontend ni reinicio/publicación requerido. Usuario confirmó antes login admin Vercel funcional.

Render preparado (30 de octubre): Dockerfile.render → scripts.run_render valida conexión Neon limitada, esquema y auditoría, usa PORT y base pública de RENDER_EXTERNAL_URL. app/database_urls normaliza URL asyncpg/TLS con SSLContext del sistema; API/Alembic/scripts lo usan, local intacto. prepare_render crea/reutiliza .env.render privado con rol SQL estable (sin rotación al reiniciar), JWT propio y MISMA clave MFA; propietario solo en equipo local. Cuatro contraseñas dev conservadas por instrucción expresa: excepción ADMIN_RENDER_ALLOW_DEV_CREDENTIALS=true solo dev/demo, no admitida en staging/prod; MFA sin cambios. Sin seed/migración/bootstrap automático ni cambios en cuentas/datos. 376 pruebas completas +26 seleccionadas aprobadas, imagen y arranque Linux/Neon comprobados (salud, 11 juegos activos, HTTPS, HEAD iframe); temporal eliminado. Repo elegido LukeDev-a/AgeCare-Administracion-back, sin commit/push/publicación aún. [Guía Render](render-neon.md). No imprimir/versionar .env.render ni copiarlo a Vercel; correo Free/almacenamiento pendientes.

Copia autorizada a Neon (30 de octubre): script operativo scripts.copy_to_neon lee solo la variable de transferencia NEON_MIGRATION_DATABASE_URL, por defecto comprueba sin escribir y con --copy exige destino vacío, API local apagada, host directo Neon y TLS verify-full. Siete pruebas aisladas aprobadas. Ejecutado respaldo+restauración transaccional, sin seed/DROP/clean ni roles/ACL locales; 39 tablas, 20 juegos y cinco cuentas internas, cantidades/huellas coincidentes y trigger de auditoría habilitado. Base local intacta; solo db se inició. backups/neon-20261030T032533210562Z contiene dump/índice/reporte verificado, excluidos de Git y Docker: no leer/mostrar ni publicar su contenido. Neon ocupado no se vuelve a sobrescribir. ADMIN_DATABASE_URL sigue local. Pendientes rol limitado estable para Render, migraciones respecto a código, misma clave de cifrado y credenciales públicas de desarrollo antes de publicar. Audios del volumen no copiados; juegos están en imagen. [Guía](../../../docs/DESPLIEGUE-VERCEL-RENDER-NEON.md).

Corrección posterior de vista previa de juegos: GameStaticFiles añade ACAO:* solo a HEAD público de juegos locales (también403); disponibilidad.js usa credentials:omit para el origen opaco del sandbox. No CORS global nuevo, GET/admin sin esa autorización; iframe conserva aislamiento y bloqueo activo/eliminado. Sin migración ni variables. 32 pruebas backend y6 Node aprobadas; navegador con API temporal SQLite: juego permanece al interactuar y se retira al desactivar. API habitual no reconstruida. [Entrega al integrador](diagnostico-vista-previa-juegos.md).

Fase18 demo autorizada (28 de octubre): routers/end_users.py + schemas/end_users.py añaden cinco rutas /end-users y /patients bajo prefijo admin, end_users solo admin. 0012 crea tres tablas demo_app_ en models.py, sin autenticación móvil. end_users_demo.py carga 32 cuentas/7 pacientes/14 vínculos solo grupo totalmente vacío y dev+end_users_demo_enabled; scripts.seed --only-empty lo llama sin sobrescribir. Compose dev activa ADMIN_END_USERS_DEMO_ENABLED por defecto, fuera false; apagada/fuera dev503, después de comprobar permisos. No conectar ni renombrar estas tablas ficticias como users reales.

Respuestas data_origin=demo/deactivation_effect=demo_only; POST exige confirmation_user_id y motivo recortado5–500, bloqueo por fila, revalida, confirma cambio/auditoría antes de responder, mobile_sessions_revoked=false. Conserva AdminSession y relaciones. Búsqueda literal de nombre/correo; pacientes por correo de miembro con EXISTS sin duplicados; detalles mínimos, roles por vínculo y sin datos clínicos. Listados/detalles y desactivación auditados con acciones demo explícitas; no copiar filtros/resultados a historial. Fuente/revocación real pendientes; sin operaciones extra. 355 pruebas completas backend y PostgreSQL temporal aprobados, base/rol/contenedores/red eliminados; habitual sin iniciar/migrar. [Operación y contrato](usuarios-pacientes-demo.md), fase Por validar en demo, abierta para integración.

**Cierre funcional de fase 17 — 27 de octubre de 2026:** usuario confirmó registro de login y aprobó la revisión restante. Auditoría cerrada en el alcance acordado, con pruebas automatizadas y PostgreSQL temporal documentados. Los estados Por validar de la entrega inicial son históricos; no se afirma inspección directa de permisos de la base habitual ni nuevos respaldos.

Fase 16: administración aprobada por el usuario el 27 de octubre de 2026 tras probar la consola; alcance administrativo cerrado. La integración móvil/reaceptación conserva su pendiente separado.

Fase 17: audit.py admite mutaciones y eventos explícitos auth.login/auth.login_failed/ticket.conversation_read autorizados por usuario; no clics/HTTP/refresh/logout. Fallos persisten pese a error, sin cambiar qué cuenta para bloqueo. Lectura por página en GET support/tickets/{id}/replies; nunca copia mensajes. event_metadata nullable (0011), allowlist de resultado/causa/página; enmascarado también al consultar y búsqueda solo campos visibles. Actor histórico sin FK conserva nombre/rol tras eliminación. Rango máximo90 incluso con fechas parciales; default30d, solo final90d, solo inicial hasta ahora. Consola muestra filtros de entidad/ID y UUID histórico, detalle IP/navegador/resultado.

0011 protege UPDATE/DELETE/TRUNCATE por trigger PostgreSQL. Compose ejecuta scripts.run_api tras migraciones/bootstrap/seed seguro; prepara login interno no propietario y solo SELECT/INSERT en auditoría, DML en negocio, sin DDL; reemplaza conexión en proceso Uvicorn con clave aleatoria sin escribir .env ni cambiar claves MFA. Se necesita propietario con CREATEROLE, una API Compose; réplicas/hosting con roles externos requieren adaptación. Retención mínima2años sin purga; no afirmar backups nuevos ni protección contra propietario del servidor. 332 pruebas backend y PostgreSQL temporal aprobados, base/rol temporales eliminados; habitual sin migrar/reiniciar. Fase Por validar. [Operación y límites](auditoria-administrativa.md).

Fase 16: app/legal_documents.py define semver numérico/canónico, vigencia desde medianoche America/Santiago, fecha sugerida y aviso de 360 horas desde publicación. Bloqueo advisory transaccional por tipo + filas serializa creación/publicación incluso sin versión previa. system.py mantiene tres rutas; GET conserva current/drafts y añade versions completas/situación/effective_at y metadatos. Solo published con fecha alcanzada puede ser current; futuras no lo reemplazan. Nuevas versiones y fechas superan última publicada/programada; revalidar al publicar, no mutar si falla. Audita creación/publicación y preserva texto/IDs; sin edición/borrado/cancelación nuevos. Schema limita semver a 10 (columna existente), normaliza ceros y rechaza extras/blancos. Sin modelos/migración/rutas nuevas. 319 pruebas completas y carreras PostgreSQL temporal aprobadas, base temporal eliminada; no se tocó la habitual. Consentimientos/reaceptación móvil pendientes. [Contrato y límites](../../../Requerimientos/fase-16/requisitos.md).

Fase 14: ModerationItemOut añade is_safety/decision_note/reject_reason_code/content_available ya derivados del registro; para photo/chat_message devuelve content={} y false hasta integrar acceso temporal, sin purgar DB. _get_pending usa bloqueo de fila y populate_existing, rechaza duplicado con ALREADY_MODERATED y protegido no disponible con CONTENT_UNAVAILABLE. Notas reales con strip/max1000, other exige texto; enum existente. Cola desempata antigüedad por ID; auditoría registra transición/nota/motivo sin copiar contenido protegido. No envíos ni job de reincidencia (excluidos), ni efectos reales sobre contenido fuente; no asumirlos por el estado local. Sin modelos/migración/rutas nuevas; [integraciones pendientes](../../../Requerimientos/fase-14/requisitos.md). Fase Por validar.

**Cierre administrativo de fase 13 — 27 de octubre de 2026:** usuario aprobó gestión de artículos y restauración a borrador y pidió confirmar cierre. Administración cerrada en el alcance acordado. T13.06 (vitrina pública, RF13.12 y parte pública de RF13.01/09) sigue pendiente por separado, sin certificación de integración. Los estados Por validar de los relatos siguientes son históricos. Consulta sobre sesión al reconstruir Docker no produjo cambios de autenticación ni causa confirmada; en la última comprobación del usuario la sesión se conservó.

**Restauración de artículos (27 de octubre de 2026):** autorizada e implementada transición archived → draft mediante PATCH existente y botón «Restaurar a borrador» para admin/editor. Conserva registro/datos, actualiza fecha y audita; no publicar desde archived directamente. RF13.03/RF13.11 actualizados; este ajuste sustituye la regla previa de archivo terminal. Sin migración ni rutas nuevas. Validación visual pendiente.

Fase 13: schemas ProductCreateIn/ProductPatchIn en operation.py recortan espacios, rechazan extras y precio no entero/negativo; null solo precio/imagen. marketplace.py fuerza draft al crear, PATCH aplica campos enviados (null borra opcionales), valida transición draft↔published→archived→draft y revalida datos completos al publicar, con bloqueo de fila. Guardar idéntico no altera fecha/auditoría; cambios auditan todos los campos antes/después. Listado desempata por ID. Sin modelos/migración/rutas nuevas; no toca cuidadoras. 279 pruebas backend aprobadas; no certifica concurrencia PostgreSQL. No hay catálogo público de productos: RF13.12 y parte pública de RF13.01/09 pendientes conforme acuerdo de documentar ampliaciones. [Alcance](../../../Requerimientos/fase-13/requisitos.md).

**Cierre de fase 11 — 27 de octubre de 2026:** el usuario confirmó «cumplimos con lo rf de la fase 11». Consola/juegos servidos por API cerrados funcionalmente en el alcance acordado, con excepción informada para externos y formulario sin cierre por clic exterior. Validación móvil pendiente por separado (T11.08), no certificada. Los estados Por validar de las entregas siguientes son históricos.

**Ajuste posterior de fase 11 (27 de octubre):** el usuario autorizó también juegos externos. Sustituye las restricciones exclusivas a juegos propios descritas más abajo. Campo URL bloqueado inicialmente, casilla para modificar/restaurar; admin/editor gestionan. Externos solo HTTPS válido sin credenciales ni espacios, sin sondeos de red; backend devuelve resource_kind local/external y conserva URL externa. Desactivar un externo solo lo retira del catálogo, sin bloquear otra web ni detener partidas: aviso visible antes de guardar, en información y vista previa. Los propios conservan bloqueo estático y control de partidas. Cambio de ficha propia a externa también bloquea sus antiguos archivos locales. Sin migración adicional. 55 pruebas backend y 6 frontend seleccionadas aprobadas, build correcto. Fase Por validar visualmente.

Fase 11: game_resources.py valida recurso /static/juegos/<slug>/index.html existente/local sin escapar de raíz. create nace inactivo, PUT parcial rechaza cambiar estado y null obligatorio, toggle valida entrada. 0010 añade created_by/created_by_name nullable para legado, preservados al editar/eliminar cuentas. GameStaticFiles en main conserva /static pero consulta ficha activa/no eliminada para archivos de cada juego y devuelve 403 sin disponibilidad; HTML inyecta control compartido, no-store y sin 304. disponibilidad.js consulta HEAD cada 5 s/foco/visibilidad y abandona partida si rechaza/falla; copias offline y clientes previos no son revocables. No montar esos juegos por otro servidor estático/CDN que omita este control. URL externa prohibida por acuerdo explícito. 256 pruebas backend aprobadas, migración SQLite; no certifica PostgreSQL ni WebView móvil. Fase Por validar visualmente. [Contrato y evidencia](../../../Requerimientos/fase-11/requisitos.md).

Fase 09 cerrada funcionalmente en el alcance acordado el 27 de octubre de 2026, tras revisión y aprobación del usuario. Directorio móvil real pendiente por separado. Mejora de diseño diferida por el usuario: texto demasiado junto; revisar espaciado/interlineado/legibilidad más adelante, sin cambios visuales ahora. Las referencias siguientes a validación pendiente son históricas.

Fase 09 (27 de octubre): support.py restringe GET /support/agents y assigned_to en PATCH a cuentas activas con rol en WRITE['support']; una asignación inválida rechaza toda la transacción. Listado ordena priority por severidad (low/medium/high/critical), con desempate por ID; conversación ordena por created_at e ID. Sin rutas/modelos/migración nuevos. 245 pruebas backend aprobadas; fase Por validar visualmente. Decisión posterior: no notificar respuestas ni enviar CSAT; RF09.09 eliminado. Quedan fuera del alcance, no pendientes. Se conserva consulta de CSAT histórico. Búsqueda de solicitante por histórico de tickets sigue siendo aproximación, no directorio móvil. Correlativo max+1 sin garantía nueva de concurrencia. [Alcance y pendientes](../../../Requerimientos/fase-09/requisitos.md).

Fase 08: [uso-por-funcionalidad.md](uso-por-funcionalidad.md) documenta la ampliación autorizada de RF08.04–06: estados/causas de adopción, cero explícito, filtro común de ranking/alertas y compatibilidad. Cambia router/schema de las tres rutas existentes, sin DDL/modelos nuevos. No recuperar el fallback de denominador ausente a cero ni asumir una fila de uso ausente como cero.

Fase 07, ampliación puntual autorizada el 27 de octubre: GET metrics/roles/weekly-active conserva weeks/series/computed_at y añade week_details alineado: start_date, end_date inclusive (inicio+6 días), is_current_week según business_today/Santiago. Utiliza week_start ya persistido, sin migración ni nueva ruta. Marca temporal de semana en curso, no prueba de cobertura completa histórica. Pruebas de cruce de mes/año, límite UTC/Santiago y lista vacía aprobadas; otras ampliaciones de fase 07 siguen diferidas.

Fase 06: [incidentes-operativos.md](incidentes-operativos.md) documenta rutas existentes, transiciones estrictas, auditoría, correo opcional y 0009. Nueva IncidentEmail y transporte SMTP compartido con invitaciones; destinatarios vacíos por decisión del usuario. PostgreSQL temporal aprobado el 27 de octubre de 2026; aceptación del usuario y cierre funcional registrados. No iniciar servicios ni enviar avisos reales por una mera revisión.

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
