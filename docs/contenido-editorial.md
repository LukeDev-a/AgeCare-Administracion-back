# Contenido editorial — Fase 10

## Diagnóstico de fallos de audio — 16 de noviembre de 2026

Refuerzo posterior: usa el canal uvicorn.error, como los mensajes del servidor. Al arrancar emite AGECARE_EDITORIAL con reason=diagnostics_ready,revision=2,enabled=true/false; comprobar primero esta marca tras el despliegue. job_result informa intento/estado después del commit y unexpected_worker_error informa fallos inesperados sin detalles externos.37 pruebas dirigidas aprobadas. Si la marca no aparece, verificar versión/despliegue y filtros de logs antes de solicitar más audios.

Los fallos del proveedor generan una línea WARNING con prefijo AGECARE_EDITORIAL. Tras subir el backend y esperar el despliegue, reintentar una vez desde la consola y buscar ese prefijo en los logs de Render. reason distingue timeout, connection_error, invalid_json, http_error, response_too_large, missing_audio_part, invalid_audio_metadata o invalid_audio_bytes. HTTP incluye solo código; la respuesta TTS incluye finish_reason/block_reason de listas permitidas, duración, longitud y contadores. No se registran claves, URLs, texto, audio ni respuestas completas. Se conservan errores públicos y reintentos; la cola puede mostrar el error previo mientras espera otro intento.

36 pruebas dirigidas aprobadas sin llamadas reales. El fallo observado en producción aún necesita reproducirse con este diagnóstico desplegado: no se ha confirmado relación con longitud, cuotas ni nivel gratuito. Sin migración, cambios de modelo o nueva configuración.

## Importación manual de noticias — 15 de noviembre de 2026

La fuente responde actualmente con desafío Cloudflare a consultas automáticas probadas, aunque el navegador del usuario abre JSON. Consulta de solo lectura a PostgreSQL local confirmó25 candidatos, último creado11nov y tres recopilaciones15nov fallidas: el aumento observado no acreditaba éxito reciente. No se cambió la protección del medio ni se copian cookies del navegador.

Alternativa autorizada: Preparar noticias → Importar archivo JSON. Abrir en navegador `https://www.cuentamealgobueno.com/wp-json/wp/v2/posts?per_page=20&_embed=author`, guardar la respuesta mediante Ctrl+S como noticias.json e importar. El archivo debe ser JSON real, no HTML del visor o un desafío. El modal explica límites, revisión de procedencia y continuación manual hacia Gemini/borrador. No se solicita IA automáticamente ni se publica.

Nuevo POST `/api/v1/admin/content/candidates/import`: cuerpo JSON raíz array de1–100 posts WordPress, máximo2MiB, validado completamente antes de escribir. Requiere admin/editor y news_collection_enabled; no requiere worker ni clave Gemini para importar. Valida identificador positivo, título/contenido rendered, fechas opcionales y enlaces HTTPS al host exacto www.cuentamealgobueno.com. Extrae texto plano y autor si viene embebido; no accede a URLs del archivo. Errores422 INVALID_NEWS_IMPORT o413 IMPORT_TOO_LARGE con mensajes sin contenido del archivo.

Devuelve candidates/duplicates/changed; changed es subconjunto de duplicates. Deduplica por fuente e ID, URL canónica o hash. Una noticia nueva queda pending/origen uncertain; un original cambiado fuerza nueva revisión de procedencia y descarta la adaptación anterior; no reemplaza el texto editorial ya creado y anula su aprobación si está vinculado. Archivo repetido idéntico no reinicia la revisión. Comparte bloqueo collection con recopilador, pero no avanza cursor automático ni cuotas. No se guardan archivos subidos ni se añaden trabajos IA. Auditoría content.news_import con actor/fecha/fuente/cantidades, sin volcar noticias.

Sin migración ni nuevas variables. Subir backend a Render y frontend a Vercel para uso público. Local requiere reconstruir API con `docker compose up -d --build api`; no seed manual ni borrar volúmenes.36 pruebas backend dirigidas de contenido/importación/configuración/auditoría y151 frontend completas aprobadas; build/lint frontend correctos. Pruebas solo con SQLite en memoria y archivos ficticios; ninguna importación en bases habituales ni llamadas Gemini. Revisión visual e importación del usuario pendientes.

## Audio al editar — 15 de noviembre de 2026

PATCH de título/cuerpo invalida aprobación y audio, conserva programación y deja audio_status=pending; ya no llama queue_audio antes de aprobar. POST approve solicita el audio de la versión revisada. No cambia esquema ni reescribe trabajos previos; la UI prioriza aprobación incluso ante colas legadas.12 pruebas del módulo en SQLite en memoria con proveedor simulado aprobadas, incluida ausencia de trabajo para la nueva versión antes de aprobar y queued después de aprobar. Sin datos reales ni llamadas Gemini. Requiere despliegue del backend; no migración.

## Regla de programación confirmada — 11 de noviembre de 2026

Guardar borrador y programar son acciones separadas. POST /items permite crear trabajo incompleto sin publish_at; si se envía una fecha futura al crear, rechaza REVIEW_REQUIRED sin crear registro. Para programar, PATCH /items/{id} con publish_at futuro exige draft, aprobación/procedencia vigentes y audio actual realmente existente. Rechaza REVIEW_REQUIRED o TTS_PENDING antes de modificar datos; si el mismo PATCH cambia título/cuerpo, exige primero guardar y aprobar esos cambios. Continúa SCHEDULE_REQUIRES_DRAFT para publicados/archivados y PUBLISH_AT_PAST para fechas pasadas. PATCH publish_at:null cancela sin exigir audio ni borrar el contenido.

Editar título/cuerpo sin enviar publish_at conserva una fecha previamente confirmada, invalida aprobación/audio y deja la publicación pendiente. El trabajador sigue comprobando preparación al llegar la fecha; no publica versiones incompletas. La UI muestra esa espera. No se exige nueva migración ni se reescriben programaciones ya existentes. Doce pruebas del módulo aprobadas, con proveedores simulados y SQLite en memoria; no se generó contenido ni se modificaron bases reales. Reconstruir API habitual para activar la regla.

## Verificación local del 2 de noviembre de 2026

El usuario eligió Docker local y confirmó proyecto gratuito sin facturación.
Después de guardar su clave, la consulta autenticada de modelos confirmó acceso
a los dos identificadores configurados. Una adaptación de texto ficticio fue
recibida y validada. Dos solicitudes TTS devolvieron audio, inicialmente rechazado
por una diferencia de mayúsculas del MIME (`audio/l16`). Corregido el lector para
tipos MIME sin distinción de mayúsculas, frecuencia declarada y validación de
canal/codec. La respuesta real capturada se convirtió y verificó sin otra llamada:
WAV mono, 24000 Hz, 5,52 segundos. No se publicó contenido ni se guardó en la base.

Consulta real de un post WordPress: texto y autor disponibles; esto no aprueba
automáticamente derechos ni veracidad. 25 pruebas específicas aprobadas con
proveedores simulados. PostgreSQL temporal: migración 0004 desde esquema previo,
cuotas concurrentes y dos trabajadores sin audio duplicado aprobados; contenedor
retirado. Corrección del script de prueba para resolver imports al ejecutarlo.

El trabajador automático sigue sin activarse desde esta revisión. Para el uso
local, después de la confirmación gratuita y con clave guardada, configurar
`ADMIN_GEMINI_FREE_TIER_CONFIRMED=true` y `ADMIN_CONTENT_WORKER_ENABLED=true` en
el entorno del backend y reconstruir la API. La activación inicia la recopilación
programada y procesa trabajos guardados, sujetos a los límites configurados.
Pendiente aceptación del recorrido en consola y del feed móvil; no cerrar fase
por la prueba directa de proveedores. Las afirmaciones de ausencia de llamadas
externas de las secciones siguientes corresponden a la implementación inicial.

Implementación del 14 de octubre de 2026. No se leyó `.env`, consumió Gemini, publicó contenido real, migró la base habitual ni reinició Docker durante el desarrollo. El trabajador externo está desactivado por defecto. Esta guía describe código; aceptación y servicios reales siguen por validar.

## Flujo

1. Recopilar hasta 20 noticias de la fuente fija WordPress de Cuéntame algo bueno. Ejecución diaria desde las 08:00 America/Santiago (si API estaba apagada, al volver ese día), o solicitud manual admin/editor.
2. Conservar todos los candidatos con texto original sin imágenes/HTML ejecutable, autor disponible, enlace, fechas y huella. Dedupe por fuente/ID; enlace normalizado y huella como apoyo. Consulta inicial toma las recientes; luego consulta modificaciones incrementalmente, con solapamiento y un máximo de cinco páginas por ejecución. No importa todo el archivo histórico inicialmente.
3. Encolar hasta cinco candidatos nuevos para adaptación por ejecución; el resto queda visible para revisar, adaptar manualmente o solicitar Gemini. Cinco no es máximo diario fijo. Los trabajos no borran candidatos al agotar cuota.
4. Comparar propuesta y fuente. IA ayuda a clasificar temas; no demuestra veracidad ni titularidad. Revisar origen y registrar motivo. Material incierto/de terceros/descartado no se aprueba. Confirmar texto propio solo tras comprobar procedencia; la firma WordPress no basta.
5. Crear un borrador con el texto elegido, manual o asistido. No se publica automáticamente por ingesta/IA. Aprobar explícitamente la versión editorial. La aprobación añade créditos, enlace/licencia y adaptación a noticias de fuente verificada.
6. Generar audio de título/cuerpo aprobados con voz Kore en español, ritmo pausado. Cambiar título o cuerpo incrementa text_version e invalida aprobación/audio. Jobs antiguos se cancelan; audio_file/audio_version deben corresponder a la versión vigente y existir en disco para indicar disponible.
7. Publicar manualmente o programar borrador futuro. Scheduler solo publica con aprobación y audio vigentes. Si falta audio, conserva borrador/programación e informa la espera. Retirar pasa a archived; borrar solo admin, lógicamente y después de retirar si publicado.

Una edición de texto publicado requiere nueva aprobación; queda fuera del feed de referencia mientras no esté aprobado. Tras aprobación, audio antiguo sigue inaccesible hasta regenerarse. Las actualizaciones del original no sobrescriben texto editorial: señalan source_changed, invalidan aprobación y requieren revisar. La adaptación conserva instantánea del original con el que se preparó.

## Gemini, cuotas y activación

Modelos configurables, sin fallback ni alta de facturación:

- Texto: `gemini-3.5-flash-lite`.
- Audio: `gemini-3.1-flash-tts-preview`, modelo legacy preview elegido por usuario. Si deja de estar disponible, mostrar error y conservar texto; no sustituir por otro modelo automáticamente.
- Clave solo servidor: ADMIN_GEMINI_API_KEY.
- Habilitar ADMIN_GEMINI_FREE_TIER_CONFIRMED=true únicamente tras comprobar en AI Studio que el proyecto de esa clave es gratuito y tiene acceso/cuotas de esos modelos. Esta declaración local NO cambia ni consulta el nivel de facturación de Google. Si se usa una clave de proyecto facturable, el código no puede garantizar coste cero; usar proyecto gratuito. No se usan grounding, batch o servicios adicionales de pago.
- ADMIN_CONTENT_WORKER_ENABLED=true habilita recopilación, jobs y scheduler en lifespan de API. Por defecto false: la interfaz lo indica y las solicitudes permanecen guardadas.
- Límites locales iniciales, aportados por usuario: texto 15 RPM/500 RPD, presupuesto conservador de entrada 250000 TPM; audio 3 RPM/10 RPD. Se reservan intentos persistentemente antes de llamar, incluidos fallos; presupuesto de tokens estimado conservador por bytes, no tokenizador oficial. No mide consumo de otros clientes del proyecto. Google puede aplicar límites menores y devolver 429.
- Hasta cinco solicitudes nuevas de audio al día; margen restante para reintentos solicitados explícitamente. Un intento no garantiza audio exitoso. Trabajos programados tienen prioridad; los duplicados con audio ya vigente no hacen otra llamada.
- Al agotar límite diario o recibir 429, conservar trabajo esperando próximo periodo. Por prudencia 429 pausa ese tipo de generación hasta siguiente día del proveedor, aunque su causa fuera un límite por minuto. Reset según America/Los_Angeles, no medianoche de Chile. RPM espera 65 segundos. Otros fallos recuperables: hasta tres intentos con espera creciente; configuración inválida requiere corregir y solicitar otro intento.

Variables completas en `.env.example`. Conservar todas las claves/configuraciones existentes; no copiar el ejemplo encima del `.env`. Tras revisar parámetros, usuario aplica `docker compose up -d --build api`. Compose ejecuta migraciones; no seed. No requiere borrar imágenes ni volúmenes.

## Persistencia, migración y límites

Migración `0004_content_pipeline.py`: añade campos editoriales/audio sin eliminar textos/estados existentes y crea news_candidates, content_jobs y content_control. Marcadores legacy tts_ready sin archivo se invalidan: no eran audio real. Contenido anterior requerirá aprobación/generación para aparecer en el feed de referencia; no se aprueban textos automáticamente.

WAV privados en ADMIN_CONTENT_AUDIO_DIR (`content_audio` por defecto). Compose monta volumen `content_audio` en `/srv/app/content_audio`; no se exponen como estáticos públicos. Respaldar base y volumen juntos. Mantener este directorio fuera de Git/imagen. No hay recolección automática de archivos obsoletos/huérfanos: una caída entre escritura y commit puede dejar un archivo no referenciado, sin hacerlo accesible desde endpoints. Definir retención antes de operación prolongada.

PostgreSQL usa locks de jobs y objetos; SKIP LOCKED y versiones evitan procesamiento duplicado normal y publicación repetida. Una caída tras respuesta del proveedor antes de commit puede repetir generación; reserva de cuota permanece contada, no se garantiza exactamente una llamada. Commit antes de respuesta de mutaciones evita confirmar trabajo que no persistió. SQLite de pruebas no demuestra bloqueo concurrente PostgreSQL.

## Contrato para consola y equipo móvil

Todas las rutas siguientes usan `/api/v1/admin/content`. Consulta/escritura admin/editor; DELETE solo admin. No son rutas públicas para pacientes ni se deben entregar credenciales administrativas al móvil. El equipo móvil incorporará las reglas a su API con autorización de pacientes propia; su validación queda conjunta y separada.

| Método / ruta | Función |
|---|---|
| GET /items | Filtros type/status/q, page/page_size. Campos de programación, revisión, audio y procedencia. |
| POST /items | Crear draft, type/title/body/tags/publish_at opcional. |
| PATCH /items/{id} | Editar campos enviados; publish_at=null quita fecha; otros null rechazados. |
| POST /items/{id}/approve | Body `{ "version": 1 }` coincide con text_version revisada. Conflicto si cambió. Confirma procedencia de candidato antes de aprobar. |
| POST /items/{id}/publish | Exige aprobación y audio actual. ALREADY_PUBLISHED, REVIEW_REQUIRED o TTS_PENDING. |
| POST /items/{id}/unpublish | Solo published a archived. |
| DELETE /items/{id} | Soft delete draft/archived; editor 403, publicado 409. |
| POST /items/{id}/audio/retry | Reintento tras aprobación; respeta presupuesto/cuotas. |
| GET /items/{id}/audio | WAV autenticado vigente; no-store. Nunca sirve versión anterior. |
| GET /candidates | Lista paginada con fuente/original/propuesta/estado/derechos. Filtros status/q. |
| POST /collect | Encolar consulta, 202; no consulta externa durante petición. |
| POST /candidates/{id}/adapt | Encolar adaptación; no duplica trabajos activos. |
| POST /candidates/{id}/review | action own/third_party/uncertain/discard/keep, note 5–2000 y source_hash leído. Conflicto si fuente cambió. Revoca aprobación de borrador vinculado al revisar. |
| POST /candidates/{id}/draft | title/body/tags; un solo borrador por candidato. |
| GET /jobs | Últimos 50 trabajos: estados, intentos, inicio/fin, resultados y errores sin secretos. |
| GET /runtime | Estado de habilitación sin secretos. |
| GET /feed | Proyección protegida de referencia: published, no eliminados y aprobados. El equipo móvil debe adaptar permisos y contrato, incluyendo créditos/audio vigente y retiro. |

Estados de contenido se mantienen draft/published/archived; la programación es una fecha, no otro enum. Estados técnicos separados pending/queued/waiting_quota/failed/ready; candidatos además adapted/needs_review/discarded/drafted. Cuando la publicación espera falta de aprobación, la UI muestra texto por aprobar; cuando espera audio, muestra condición explícita.

## Fuentes consultadas

- [Modelo de texto](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [TTS seleccionado y condición legacy](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-tts-preview), [API generateContent TTS](https://ai.google.dev/gemini-api/docs/generate-content/speech-generation).
- [Precios gratuitos/modelos](https://ai.google.dev/gemini-api/docs/pricing), [cuotas por proyecto y reinicio Pacific](https://ai.google.dev/gemini-api/docs/rate-limits). No se consultó cuota privada de la cuenta del usuario.
- [Licencia del medio](https://www.cuentamealgobueno.com/licencia-de-cuentamealgobueno/): BY-SA para material propio; agencias/terceros excluidos. Guardar créditos no verifica automáticamente que un artículo concreto esté cubierto.

No se probó la API de noticias en ejecución real ni se consumió Gemini. Adaptadores externos probados con fixtures/transporte simulado. El primer ensayo con proveedor real debe revisar respuestas y cuotas, no certificar integración con mocks. Fuente de chistes sigue pendiente; edición manual de chistes disponible.
## Regla vigente: programación con audio opcional autorizado — 17 de noviembre de 2026

Tras aprobar y probar la excepción inmediata, el usuario pide también programarla. Nueva acción `POST /items/{id}/schedule-without-audio`: mismo permiso admin/editor, versión, motivo5–500 y revisión explícita; añade `publish_at` futuro. Requiere borrador, aprobación/procedencia válidas y fallo de audio. Una autorización previa vigente puede reprogramarse con nueva confirmación aunque esté reintentando el audio. La programación habitual sigue exigiendo audio y no autoriza la excepción de forma implícita.

Migración **0018_scheduled_text_only.py**, hija de0017: columna JSONB nullable `content_items.schedule_audio_exception`, sin actualizar los contenidos existentes. Guarda versión, fecha UTC, instante de aprobación editorial, revisión confirmada, motivo, fallo inicial y responsable/fecha de autorización. Se valida al consultar y ejecutar: editar texto, renovar aprobación o cancelar/cambiar la fecha invalida la autorización. Cancelar o elegir programación habitual elimina el permiso; editar conserva la fecha, pero vuelve a exigir aprobación/audio o nueva excepción. No requiere estado nuevo en el enum.

El scheduler recupera la autorización del registro persistido, también tras reinicio. Al llegar la fecha incluye audio vigente si existe; si no, publica el texto y registra `content.publish_without_audio`, con `scheduled=true` y el responsable que autorizó la excepción. Sin autorización válida sigue esperando. El evento `content.schedule_without_audio` registra la decisión inicial. La autorización se elimina al publicar; su historial queda en auditoría. El feed y el acceso de audio mantienen los contratos anteriores.

UI: fecha habilitada tras fallo, botón Programar sin audio, confirmación dentro del Modal con fecha/motivo/revisión, aviso de audio opcional y cancelación. Fallo conserva formulario; éxito guarda respuesta canónica y muestra la programación. Listado indica «Se publicará con o sin audio». Si el audio llega antes, se incluye sin pedir otra decisión.

Validación:533 pruebas backend completas y188 frontend, build/lint dirigido aprobados, sin Gemini real ni publicaciones del usuario. Incluye persistencia entre sesiones, fecha futura, permisos/motivo/confirmación, publicación con y sin audio, reintento en curso, invalidación/cancelación y migración idempotente con conservación. Docker local migró0017→0018 conservando8 contenidos, todos sin autorización añadida; /health200. No Neon, push o despliegue remoto. **Aplicar0018 a Neon antes del futuro despliegue de este backend**, siguiendo el flujo de migraciones separado; la aprobación actual del usuario solo cubrió Docker. Revisión visual de la programación pendiente.

## Publicación manual sin audio — paso anterior, 17 de noviembre de 2026

La ampliación de programación descrita arriba sustituye la restricción a publicación inmediata de este registro histórico.

El usuario amplía la condición de audio obligatorio con una excepción manual, sin modificar la programación automática. `POST /items/{id}/publish-without-audio` exige permisos de contenido de escritura (admin/editor), `version` vigente, `reason` de5–500 caracteres y `review_confirmed: true` booleano estricto. Conserva comprobación de aprobación/procedencia. Solo se permite tras `audio_status=failed` con error registrado y sin audio actual; pendiente, cola o espera de cuota no habilitan la excepción. Si ya hay audio disponible se utiliza publicación normal. Un bloqueo del proveedor no se ignora automáticamente: la persona debe revisar y confirmar explícitamente el texto antes de asumir la excepción.

La acción publica inmediatamente, cancela programación, conserva el fallo y no crea un audio ficticio. Auditoría registra `content.publish_without_audio`, actor/fecha y versión, motivo, error y confirmación. Listado/detalle muestran «Publicado sin audio» mientras esté publicado sin archivo vigente. Se puede solicitar audio después; al terminar pasa a mostrar disponibilidad, sin republicar. Feed protegido de referencia puede devolver el texto con `audio_available=false` y `audio_url=null`; integración móvil sigue fuera del alcance.

No cambia enum ni esquema persistente: no requiere Alembic. El scheduler y la programación siguen exigiendo audio vigente y nunca aplican esta excepción por sí mismos. La confirmación de la interfaz se vincula a la versión del texto; una revisión anterior no vale para una nueva versión. El formulario conserva motivo ante error, confirma retirada de programación y vuelve al listado tras publicación exitosa.

Validación:522 pruebas backend completas,186 frontend, build y lint dirigido aprobados; incluye publicación/auditoría, motivo/revisión/versiones inválidos, permisos, procedencia, programación bloqueada y generación posterior al publicar. Proveedores simulados, sin llamadas Gemini ni publicaciones del usuario durante esta ampliación. Docker API local reconstruido; revisión visual del usuario pendiente. No Neon, commit/push ni despliegue remoto. Requisito de entrega10.6 corresponde aRF10.07 en la tabla histórica de fase10, con publicación manualRF10.04; no sustituir RF10.06 interno, que describe eliminación.

## Respaldos TTS por modelo — 17 de noviembre de 2026

Por petición explícita del usuario se añadieron los dos modelos que muestra su proyecto gratuito: `gemini-3.8-flash-lite-tts` y `gemini-3.8-flash-tts`. Se conserva `ADMIN_GEMINI_TTS_MODEL` como principal (local: `gemini-3.1-flash-tts-preview`). Nueva opción `ADMIN_GEMINI_TTS_FALLBACK_MODELS`, CSV ordenado, predeterminado `gemini-3.8-flash-lite-tts,gemini-3.8-flash-tts`; vacío desactiva respaldos. Solo se admiten estos tres modelos, se deduplican y sigue siendo obligatorio confirmar el proyecto gratuito. Sin cambios de clave, facturación o voz Kore.

Cada tramo consulta los modelos configurados en orden, priorizando el que ya produjo el tramo anterior de ese trabajo. Una cuota local agotada omite ese modelo; un429 bloquea solo su contador hasta el siguiente día del proveedor. Fallo temporal,404 del modelo TTS o audio inválido/incompleto permiten intentar el mismo tramo con el siguiente modelo. Si todos esperan cuota, conserva avance y espera la disponibilidad más próxima. Si todos fallan temporalmente se conserva el reintento acotado existente. SAFETY y equivalentes detienen el trabajo, sin cambio de modelo; configuración/credenciales inválidas tampoco se eluden con respaldos.

**No comienza de cero:** conserva los WAV de tramos confirmados en el volumen privado y reintenta únicamente el pendiente, completo desde su inicio. Solo une/publica como audio disponible cuando están todos los tramos. El mismo nombre de voz puede presentar variaciones entre modelos: la escucha editorial sigue siendo necesaria. Si falta un parcial guardado se informa error de almacenamiento, sin presentar una grabación incompleta como vigente. Una edición sigue cancelando el trabajo de la versión anterior.

Cuotas en `content_control`: `quota_tts_<id-modelo>` guarda conteo diario/RPM/bloqueo independiente. El contador legado `quota_tts` conserva el límite global de artículos nuevos y fija `legacy_model`; su consumo previo se hereda una sola vez por ese modelo, sin reiniciarlo ni transferirlo a los respaldos. Su `count` antiguo es histórico, no el total activo. Cada llamada consume una reserva, pero pasar a un respaldo no cuenta como otro artículo nuevo; los tramos/reintentos continúan el mismo artículo. Se mantienen10 llamadas/día y3/min por modelo y5 artículos nuevos/día globales. Son protecciones de esta base, no una lectura en vivo del consumo de Google ni una promesa de30 llamadas utilizables: otras instancias pueden consumir el mismo proyecto. No requiere Alembic.

Contrato3.8 verificado contra [guía oficial de TTS](https://ai.google.dev/gemini-api/docs/generate-content/speech-generation) y [migración de Flash Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-lite-tts): texto literal en `parts.text`, estilo en `speech_metadata`, voz en `voiceConfig.voice` y salida WAV. El lector valida WAV PCM mono16bit y lo normaliza a WAV compatible; conserva soporte PCM de3.1. No añade al audio las instrucciones de lectura de la API antigua.

Validación local: ambos3.8 generaron lecturas breves reales con STOP/WAV. Con3.1 en su límite local, una noticia sintética de3709 caracteres produjo3 tramos en Flash Lite y el cuarto pasó automáticamente a Flash TTS por el límite por minuto. Los4 terminaron STOP y se unieron en272,68s. Evidencia: `outputs/audio-models-review` del workspace.506 pruebas backend completas aprobadas: contadores independientes, herencia del consumo, límite global, bloqueo por proveedor, reintento de tramo, cancelación y conservación de audio anterior. Pruebas de cola/API usan proveedores simulados; la prueba de respaldo del diagnóstico utiliza Gemini real y cuotas locales. Sin noticias del usuario publicadas, cambios en Neon, commit/push o despliegue Render.

Diagnóstico explícito: `python -m scripts.diagnose_audio_local --mode inspect` solo consulta. `--mode short --fallback` o `--mode long --fallback` prueba la cadena real; `--model <id>` prueba uno concreto. Todos exigen dev/host local y reservan cuota, incluidos fallos. No ejecutar estas pruebas de proveedor como parte de tests automáticos ni en producción.

## Lectura extensa por tramos — 17 de noviembre de 2026

Comprobación real en Docker local, con proyecto gratuito confirmado y sin Neon: una lectura corta produjo WAV válido; una petición de3936 caracteres agotó el timeout anterior de60s. Al ampliarlo, otra petición extensa devolvió SAFETY. Son fallos distintos; no se ha probado que el plan gratuito sea la causa ni que todo SAFETY implique texto inapropiado. Un archivo PCM válido tampoco garantiza que se haya leído todo: una prueba con párrafos repetidos omitió repeticiones.

La cola ahora divide título+cuerpo en tramos de hasta1200 caracteres, priorizando párrafos y espacios, sin resumir el contenido. Solicita un tramo por ejecución y guarda el avance confirmado en ContentJob.result y WAV parciales privados del volumen de audio. Cada llamada reserva cuota; solo el primer tramo cuenta como nuevo audio. Al esperar por cuota conserva el avance y, al reanudar, no vuelve a pedir tramos confirmados. Una edición invalida la versión y cancela el trabajo anterior. Solo tras unir todos los PCM compatibles se marca audio vigente; nunca se publica un parcial. Los archivos parciales permanecen en el almacenamiento privado y requieren la misma persistencia que los audios finales. No se añadió migración.

ADMIN_GEMINI_TTS_TIMEOUT_SECONDS es opcional:300s por petición de audio, rango60–600; adaptación y recopilación conservan60s. La instrucción de lectura se simplificó; modelo y voz permanecen iguales. No se modificaron filtros, claves, límites de cuota ni facturación. SAFETY/BLOCKLIST/PROHIBITED_CONTENT/SPII/RECITATION generan AUDIO_CONTENT_BLOCKED, detienen reintentos automáticos y conservan borrador/aprobación. MAX_TOKENS/OTHER y otros finales explícitos incompletos no se aceptan aunque contengan bytes. La consola explica el bloqueo y permite revisión/reintento manual; no garantiza que cambiar filtros resuelva el problema.

Validación: noticia sintética sin repeticiones de3709 caracteres,4 tramos con STOP, WAV mono de266,6s. Transcripción offline confirmó inicio y última frase; evidencia local outputs/audio-local-review en la raíz del workspace.489 pruebas backend completas aprobadas, incluidas reanudación por cuota, cancelación por edición y rechazo de parciales/bloqueos.183 pruebas frontend y build aprobados. API Docker reconstruida y /health200, base conservada. No se aprobaron/publicaron artículos del usuario ni se hizo push/despliegue. La prueba del proveedor es real; el flujo cola/API se verificó con proveedores simulados. A la salida del diagnóstico, contador local9/10 solicitudes diarias: una noticia larga nueva puede quedar esperando cuota tras el primer tramo.
