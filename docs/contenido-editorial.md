# Contenido editorial — Fase 10

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
