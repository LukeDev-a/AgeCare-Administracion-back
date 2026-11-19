# Monitoreo operativo — fase 05

## Límites de Configuración conectados — 19nov2026

Validado con592pruebas API completas y12frontend dirigidas,build/lint correctos. Local reconstruido/health200 y lectura PostgreSQL confirma500ms/2% con361muestras,p9547ms,operational. Sin edición de parámetros/observaciones locales, migración ni despliegue remoto.

Con monitor habilitado, api_core consume ops_thresholds.api_core mediante caché60s, invalidada localmente tras guardar/commit y actualizada por TTL en otros procesos, sin reiniciar. El worker de configuración incluye esta clave. Si falta, aplica los valores iniciales500ms/0,02; valor corrupto o lectura fallida devuelve SETTINGS_UNAVAILABLE y no se afirma salud con una configuración inválida.

La evaluación exige actividad en últimos180s. Si todas esas solicitudes recientes fallan, informa outage; sin actividad reciente conserva estado desconocido. Con alguna correcta, compara el p95 de respuestas correctas de última hora (mínimo20) y la proporción de fallos técnicos de todas las observaciones de esa hora con los máximos configurados. Superar cualquiera causa degraded; igualdad con el límite se acepta. Dentro de ambos límites, operational. Si no hay20correctas, no evalúa latencia y lo explica en note, conservando evaluación por fallos. Los4xx siguen siendo respuestas técnicas correctas. La nota indica límites, ventana y muestras faltantes; overall conserva agregación del peor estado real conocido. No cambia mediciones, tiempos de espera, rendimiento, base de datos, autenticación ni servicios conservados. No genera incidentes/correos automáticamente. Sin migración ni edición de parámetros existentes.

## Mediciones reales acotadas — 18 de noviembre de 2026

Esta ampliación incorpora un recolector para **API administrativa (`api_core`), autenticación de la consola (`auth`) y base de datos (`database`)**. Sustituye las limitaciones de recolector pendiente descritas en la entrega histórica de abajo. No acredita la salud de la app móvil ni de proveedores externos. La aceptación de la consulta de fase 05 se conserva como antecedente; la ampliación tiene su validación propia.

### Configuración, almacenamiento y privacidad

`ADMIN_OPS_MONITOR_ENABLED` es `true` por defecto en `app/config.py`; las pruebas lo deshabilitan salvo que ejerciten el recolector. El middleware y el worker se integran en `app/main.py`. La migración **0021**, posterior a 0020, crea `ops_observations` e índices, sin convertir ni borrar los estados, agregados o procesos anteriores. Se debe aplicar la migración antes de desplegar el backend actualizado y después publicar el frontend compatible. Este documento no acredita aplicación de 0021 a la base habitual, Neon ni otro entorno remoto.

Con el monitor habilitado, las consultas operativas usan exclusivamente las observaciones nuevas: no mezclan las demostraciones anteriores. Con el flag deshabilitado, conservan la consulta de los agregados heredados. No se añade un endpoint público de ingesta.

Cada observación guarda identificador, componente, instante, duración, éxito, fuente y categoría técnica de fallo. No guarda URL, parámetros, cuerpos HTTP, cabeceras, IP, identidad, credenciales ni texto de excepciones. El búfer pendiente admite hasta **5.000 observaciones**; al llenarse descarta las más antiguas. Solo retira del búfer el lote persistido después del commit. La retención es de **31 días**, con máximo de **100.000 filas por componente**. Los resultados describen el historial observado que permanece disponible, sin extrapolar observaciones descartadas. El downgrade de 0021 elimina la nueva tabla y su historial, por lo que no es una vía para conservar esas mediciones.

### Qué se observa

- **API administrativa:** duración de solicitudes HTTP reales bajo `/api/v1/admin/`, excluyendo OPTIONS y documentación/OpenAPI. La duración se mide en el servidor; no es el tiempo completo percibido por el navegador. Las solicitudes a `auth` también generan una observación de autenticación.
- **Autenticación de la consola:** respuestas técnicas de las rutas `auth`, sin ejecutar logins sintéticos. Los 4xx, incluidos rechazos de credenciales o permisos, cuentan como respuestas técnicas válidas. Un 5xx o una excepción de transporte cuenta como fallo. Este porcentaje no significa que todas las personas hayan iniciado sesión correctamente.
- **Base de datos:** `SELECT 1` en una sesión independiente al iniciar el worker y después de cada ciclo con espera de **60 s**, con timeout de **3 s**. La medición verifica respuesta básica de la base; no valida todos los procesos de negocio.

El worker solo funciona mientras el proceso está activo. No hay pinger externo para despertar Render, respaldo de monitoreo externo, generación de actividad ni relleno de pausas. Si falla la persistencia se conserva lo pendiente dentro del límite del búfer y se emite una marca genérica de diagnóstico, sin presentar el lote como guardado.

### Estado, ventanas y porcentajes

Se conservan permisos y rutas: GET `/api/v1/admin/ops/status`, `/latency` y `/critical-processes` para admin/analyst/support; editor/moderator reciben 403 y sesión inválida 401.

`/status` añade `monitoring_enabled=true` y `sample_window=1h`. Solo los tres componentes conectados pueden tener un estado medido. Los demás devuelven `status=null`, métricas y fechas null, `data_origin=unavailable` y `freshness=not_integrated`: son neutrales y no intervienen en `overall`. El estado de cada componente usa las observaciones de los últimos **180 s**: todas correctas = operational, todas fallidas = outage, mezcla = degraded. Sin observaciones recientes el estado es null. `overall` es el peor estado conocido, o null si ninguno tiene estado vigente. Esto no certifica el estado general de toda la plataforma.

Los metadatos incluyen `sample_count`, primera/última observación disponible, `observed_success_rate`, cobertura cuando corresponde, fuente, mínimo de muestras y frescura (`fresh`, `stale`, `no_data`, `not_integrated`). En resumen, el conteo y porcentaje corresponden a la última hora; `checked_at` conserva la última observación recibida. No se actualiza una fecha solo por consultar.

El porcentaje de éxito observado divide observaciones correctas entre observaciones realizadas. **No sustituye la disponibilidad temporal de 30 días.** Para HTTP, `uptime_30d` permanece null. Para base de datos solo se publica cuando la cobertura de los últimos 30 días alcanza **95 %**: se consideran pares de comprobaciones consecutivas separados por no más de 90 s, con máximo de 60 s de cobertura por par; el intervalo solo cuenta como correcto si ambas comprobaciones lo fueron. Una comprobación aislada no acredita un minuto y la última no rellena hasta el presente. Pausas, falta de historial o recortes de retención pueden dejar la disponibilidad sin datos suficientes.

`/latency` conserva ventanas **1h/24h/7d**, selección múltiple, deduplicación y validación de componentes/ventana. Calcula p50/p95 mediante rango más cercano sobre **duraciones individuales exitosas**, con un mínimo de **20 éxitos por componente y ventana**; con menos devuelve ambos null. No calcula percentiles de percentiles ni convierte ausencia en cero. `sample_count` cuenta todas las observaciones de la ventana, incluidos fallos; no acredita por sí solo que se alcance el mínimo de éxitos. Los componentes no integrados y los conectados sin muestras aparecen en `missing_components`. Las fechas proceden de la última observación disponible.

Con el monitor habilitado, `/critical-processes` devuelve `processes=[]` y fecha null: SOS, medicación, push, IA y demás recorridos no tienen mediciones conectadas. No reutiliza sus cadenas de demostración como pruebas reales. No crea incidentes, umbrales de latencia, alertas ni correos automáticos; la gestión manual y sus avisos conservan el contrato de [incidentes-operativos.md](incidentes-operativos.md).

### Consola y verificación de esta ampliación

La consola identifica el conjunto como «Estado de los servicios medidos». Distingue «Sin mediciones conectadas», «Esperando mediciones» y «Sin datos recientes» con tratamiento neutral. Las tarjetas muestran éxito observado de la última hora, p95, muestras y fechas; explican el alcance de autenticación y separan disponibilidad de 30 días. Los percentiles insuficientes se presentan como «Sin muestras suficientes» y los procesos sin integración conservan una vista vacía explicativa.

El autorefresco ya existente consulta al entrar, cada 60 s después de completar la consulta y al recuperar foco/conexión con la pestaña visible; se pausa en Incidentes para proteger formularios. Conserva filtros, datos y fechas ante errores y descarta respuestas anteriores. Este refresco de la vista es distinto del sondeo de base del worker.

Validación final: **573 pruebas backend aprobadas**, incluidas 22 del monitor; 208 pruebas frontend aprobadas y nueva ejecución de las 8 pruebas operativas, build y lint dirigidos correctos. En PostgreSQL 16 temporal se verificó el paso 0020→0021, 41 observaciones de solicitudes y SELECT 1 reales, conservación del estado anterior, reintentos sin duplicados y permisos runtime (inserción permitida; edición/borrado de auditoría denegados). El contenedor temporal fue retirado. No se acredita aceptación visual nueva ni migración habitual/Neon/producción aplicada.

La comprobación PostgreSQL parte de una base temporal preparada como 0020; no acredita la cadena histórica completa desde cero. Se detectó una limitación previa: 0001 usa los modelos actuales y puede crear tablas app_* que colisionan con el renombrado de 0017 en una instalación vacía. No se modificaron esas migraciones históricas en esta entrega.

La persistencia conserva UUID para reintentos de un commit ambiguo, deduplica el búfer y solo lo confirma tras éxito. Las cancelaciones HTTP se registran como fallos técnicos y se propagan. Las consultas filtran componentes y ventanas en SQL; el resumen carga solo una hora de HTTP, agrega límites de fechas por componente y proyecta los sondeos DB necesarios para cobertura. Índice compuesto por componente, fecha e ID. `successful_sample_count` distingue las duraciones válidas del total observado.

## Entrega histórica de consulta — 26 de octubre de 2026

Las secciones siguientes conservan el contrato y evidencia de aquella entrega. Las afirmaciones de ausencia de recolector y polling corresponden a ese momento y quedan sustituidas por la ampliación y el autorefresco descritos arriba; no describen el comportamiento actual con el monitor habilitado.

26 de octubre de 2026. Módulo de consulta implementado y aprobado visualmente por el usuario el 26 de octubre de 2026 mediante tres capturas; fase 05 cerrada funcionalmente en ese alcance. La conexión a mediciones reales sigue pendiente. No incorpora un recolector de salud, ejecutor sintético ni integración externa nueva.

## Contrato

Prefijo `/api/v1/admin/ops`. GET `/status`, `/latency` y `/critical-processes` requieren `require('ops')`: admin/analyst/support. Editor/moderator reciben 403; sesión ausente o inválida, 401. Los endpoints de incidentes existentes no se ampliaron en este trabajo.

- **status**: `overall` toma el peor estado de los componentes; si no hay filas, overall y checked_at son null. Cada componente conserva key/name/status/uptime_30d/latency_p50_ms/latency_p95_ms/note y agrega checked_at, data_origin y measurement_kind. p50 y p95 ausentes se muestran independientemente como «Sin datos». Disponibilidad sigue siendo fracción 0–1 y la UI la convierte a porcentaje.
- **latency**: `window=1h` por defecto; admite 24h y 7d. Múltiples componentes mediante `components=database&components=push`; si se omiten, conserva los siete síncronos predeterminados. Deduplica claves. Ventana inválida: 422 INVALID_WINDOW; componente desconocido: 422 de validación. Devuelve window, components, computed_at y missing_components. Cada fila conserva p50_ms/p95_ms/sample_count y agrega computed_at/data_origin/measurement_kind. Selección sin filas: fecha null y componentes faltantes explícitos, sin métricas falsas de cero.
- **critical-processes**: conserva cadenas/estado/p95_seconds/success_24h y agrega fecha, origen y tipo a cada proceso. computed_at del conjunto es null si no hay filas. execution_kind=synthetic añade «Comprobación sintética (ejecución de prueba)» a la cadena de salida; no modifica la cadena guardada ni ejecuta el proceso al consultar.

measurement_kind se deriva del componente: push=delivery (entrega extremo a extremo), ai_assistant=generation (generación de respuestas), otros=service. No llamar HTTP a una medición de entrega o generación. Los percentiles proceden del agregado almacenado, no se recalculan en el navegador ni mediante el endpoint de consulta.

## Datos y migración

La migración **0008** añade data_origin a ComponentState, LatencyWindow y CriticalProcessState, y execution_kind a este último. Conserva datos anteriores como unknown. Los ejemplos nuevos de scripts.seed se marcan demo; su cadena se identifica como demostración. El modo seguro --only-empty sigue conservando módulos ocupados. No se deduce el origen del contenido, no se actualizan filas antiguas para que parezcan medidas hoy.

Valores de integración previstos: data_origin=real/demo/unknown; execution_kind=real/synthetic/demo/unknown. Quien publique un estado real debe registrar sus tiempos de medición/cálculo y la procedencia correcta, sin información personal en notas o cadenas. synthetic requiere una ejecución de prueba acreditada; demo no prueba que tal ejecución exista. No se añadió un endpoint de ingesta: ese contrato y el recolector siguen pendientes.

La fecha general representa la última medición recibida; se exponen también fechas por fila. No equivale a un ciclo único compartido por todos los componentes, ya que el modelo no tiene identificador de ciclo. La fase 05 pide frescura, pero no fija umbral de caducidad: se muestran fechas sin heredar las 24 horas de analítica comercial.

El downgrade conserva las columnas deliberadamente para no perder su procedencia. Como 0001 usa metadata actual, 0008 comprueba columnas antes de añadirlas; se verificó tanto instalación como simulación de legado 0007 en PostgreSQL temporal.

## Interfaz

OperativoPage consulta secciones de forma independiente. Actualiza al entrar, cambiar filtros de latencia o pulsar «Actualizar vista», sin polling. Cancelación lógica evita que una respuesta de un filtro anterior reemplace la selección vigente. Fallar incidentes no oculta componentes/latencias/procesos. La selección inicial conserva los siete servicios síncronos; push/IA son seleccionables, aunque puede no haber filas para ellos.

La vista conserva el tema y estilos existentes y no agrega botones de modificación. Supervisar SOS, medicación, IA o sincronización musical no implementa esos procesos de la app móvil. Tampoco se implementan en esta fase umbrales/tres ciclos, incidentes automáticos o notificaciones.

## Verificación y arranque

179 pruebas backend y 46 frontend aprobadas, build correcto y lint operativo sin errores. Test específico backend: tests/test_operational_monitoring.py; frontend: tests/operational.test.cjs. tests/check_operational_postgres.py admite únicamente una base temporal agecare_seed_check_ops_* y simula el esquema previo; nunca debe apuntar a datos de trabajo.

No se migró ni reinició la API habitual durante esta entrega. Para aplicar en desarrollo desde la carpeta del backend: `docker compose up -d --build api`. Conservar volumen y clave MFA; no ejecutar seed sin --only-empty. Los datos antiguos seguirán mostrando origen desconocido hasta poder acreditarlo.
## Ajuste posterior confirmado — 18nov2026

Modo combinado por petición del usuario: api_core/database/auth usan únicamente ops_observations; los demás conservan ComponentState y LatencyWindow, con valores, fechas y procedencia intactos y freshness=stored. El global, sus contadores y fecha solo consideran los tres componentes medidos. Sin registro previo se mantiene not_integrated. Procesos críticos consulta los registros anteriores con su procedencia conservada. Sustituye las menciones siguientes de procesos vacíos y todos los demás componentes neutrales. No se generan ni actualizan datos de ejemplo. No requiere otra migración.36 pruebas backend dirigidas,8 frontend y build aprobados.
