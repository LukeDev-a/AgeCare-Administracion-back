# Configuración operativa: funciones y avisos

## Aceptación y alcance vigente

El 12 de noviembre el usuario confirmó funcionamiento de interruptores y publicación/retirada del aviso en su consola local. Después excluyó definitivamente RF15.10/RF15.11 (alertas/medicación) y autorizó limitar RF15.09 y la propagación de RF15.02 a las funciones editoriales y el aviso descritos aquí. La falta de consumidores de alertas/medicación ya no es un pendiente de esta fase. No se afirma integración de precios/cobros, bajas/cálculos ni umbrales/monitoreo. Las menciones anteriores de revisión visual pendiente y alcance global pendiente quedan sustituidas por esta decisión. El despliegue remoto continúa pendiente; no se aplicaron cambios de código o datos al ajustar estos documentos.

12 de noviembre de 2026. Alcance autorizado: recopilación de noticias, adaptación con Gemini y un aviso general de la consola. No incluye un motor de alertas, planificación de medicación, asistente móvil ni música.

## Parámetros

La migración **0016** añade claves únicamente si no existen. Conserva valores, esquemas y versiones instalados.

| Clave | Campos | Efecto y estado inicial |
|---|---|---|
| feature_flags | news_collection_enabled y news_adaptation_enabled, booleanos obligatorios, sin campos adicionales. | Inicialmente true/true para conservar comportamiento existente. Permiten/impiden solicitudes nuevas de recopilación/adaptación y las automáticas correspondientes. No cambian permisos, cuotas, claves Gemini ni configuración del worker. |
| system_texts | notice_enabled, notice_title hasta120 y notice_body hasta1000 caracteres. | Inicialmente desactivado/textos vacíos. Activar exige título y cuerpo con texto distinto de espacios. Aviso de texto plano en la consola autenticada, no modo mantenimiento ni mensaje móvil. |

Solo admin consulta/modifica `/settings`. Se conservan motivo de5–500, reemplazo completo, JSON Schema, versión, auditoría y conflicto. Ningún formulario crea/elimina claves. Etiquetas y ayudas comprensibles, sin necesidad de editar JSON. No incluir credenciales ni datos personales en avisos; el administrador debe revisar su contenido.

Desactivar recopilación impide POST `/content/collect` y nuevas ejecuciones diarias. Desactivar adaptación impide POST `/content/candidates/{id}/adapt` y nuevas adaptaciones automáticas de los candidatos recopilados. La API rechaza con409 FEATURE_DISABLED incluso una petición directa autorizada. Los trabajos ya aceptados continúan; una recopilación aceptada puede terminar, pero no creará adaptaciones nuevas si están desactivadas. Los datos existentes, edición manual, aprobación, audio y publicación se conservan.

GET `/content/runtime` mantiene su permiso content y añade collection_enabled/adaptation_enabled. La pantalla Preparar noticias deshabilita controles, explica el estado y actualiza disponibilidad al cargar, al actualizar, al recuperar foco y cada60s. La API sigue siendo la autoridad. No se habilitan funciones sin permiso de rol.

GET `/runtime/notice` exige una cuenta de consola activa/autenticada y devuelve solo enabled/title/body/version, sin otros parámetros ni metadatos internos. Al desactivar no devuelve el texto guardado. React renderiza texto escapado, sin HTML ejecutable. SystemNotice aparece sobre el contenido de la consola, consulta cada60s/al recuperar foco y al guardar en esa ventana. Si falla la consulta se retira la copia visible y se informa con un aviso breve; se reintenta automáticamente.

## Caché y consistencia

`app/runtime_settings.py` mantiene por proceso copias de valor/versión de estas dos claves durante60s desde una lectura exitosa. Las lecturas no prolongan TTL, los resultados son copias independientes y se comparte la carga concurrente. Versiones inferiores no reemplazan una copia más nueva. Al fallar una renovación no se sirve el valor vencido; las operaciones dependientes responden503 SETTINGS_UNAVAILABLE y el worker reintenta. No se aplican estas reglas a emergencias o medicación sin política específica.

El worker de cada proceso revisa claves cada5s y renueva las vencidas aunque no haya tráfico. El primer acceso carga desde PostgreSQL. PUT confirma en una transacción valor, versión y auditoría; solo después del commit invalida la copia local. Los otros procesos recargan al siguiente vencimiento/ciclo. No se requiere reiniciar para cambiar valores. La renovación y las consultas de pantalla añaden sus propios tiempos: no prometer aplicación global en60s. GET administrativo sigue leyendo la fuente vigente directamente.

Las instalaciones anteriores sin estas claves conservan el comportamiento previo hasta migrar: aviso oculto y funciones permitidas. En Render la verificación de head obliga a aplicar0016 antes de arrancar el nuevo código. No se afirma que esta caché conecte automáticamente precios, bajas, monitoreo, alertas o medicación; esos consumidores siguen pendientes.

## Aplicación

Local, desde el backend: `docker compose up -d --build api`; luego recargar consola. No nuevas variables, claves ni volúmenes. La migración crea las claves, no se ejecuta seed manual para incorporarlas. Se ajustó `scripts.seed --only-empty` para que la presencia exclusiva de las dos claves nuevas no impida cargar el grupo anterior de configuración en una instalación vacía; conserva ambas y cualquier grupo previamente configurado. No se ejecutó seed contra datos habituales.

En Neon/Render: aplicar migraciones pendientes hasta0016 mediante la conexión propietaria separada. Si0015 todavía no está aplicada, incluirla y otorgar DML de sus dos tablas al rol limitado;0016 solo inserta claves en system_settings, sin tablas ni permisos nuevos. No subir el backend nuevo antes de preparar el esquema. No se aplicaron estas operaciones remotas ni reinicios locales en esta entrega.

## Validación y pendientes

Suite backend completa446 pruebas aprobadas antes de añadir una comprobación adicional de conservación de trabajos aceptados; verificación dirigida final13 pruebas de caché/operación/seed aprobadas. Frontend139 pruebas existentes más3 nuevas dirigidas aprobadas, build/lint dirigidos correctos. Caché con reloj controlado: TTL no deslizante, dos procesos simulados, concurrencia de carga, copia independiente, versión inferior y caída/recuperación de fuente. PostgreSQL16 temporal verificó0016 idempotente, valores/versiones conservados, renovación de dos cachés y edición concurrente con200/409 sin sobrescribir. Contenedor temporal retirado; script reproducible tests/check_runtime_settings_postgres.py con guardas de destino local. Sin proveedores externos, correos reales ni alteración de bases habituales. Revisión visual pendiente.

RF15.12 y RF15.13 implementados en el alcance elegido, por validar manualmente. RF15.09/parcial deRF15.02 cubiertos para estos consumidores, pendientes para los restantes. RF15.10/RF15.11 pendientes: modelos y seed contienen indicadores genéricos de alertas/medicación, pero no tablas de tomas/prescripciones/entregas ni motor/planificador operativo donde aplicar las reglas. No crear controles que aparenten regular esos servicios.
