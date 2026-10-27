# Analítica comercial — fase 04

Implementación del 26 de octubre de 2026, pendiente de aceptación visual. La unidad facturable de planes sigue sin definir y la integración de fuentes reales se realizará después. No confundir perfiles móviles con roles de la consola.

## Consulta y permisos

Todas las rutas parten de `/api/v1/admin/metrics/commercial`, admiten admin, analyst y support, y rechazan editor/moderator con 403. Sin sesión válida: 401. La consola utiliza su cliente de sesión habitual.

| GET | Uso |
|---|---|
| `/summary?period=current_month` | Totales del período, variaciones, corte de activos/pago/MRR y fechas |
| `/registrations?period=current_month` | Período, granularidad, buckets y arrays alineados de altas/bajas |
| `/plans` | Último snapshot histórico, precios conservados, cantidades y totales |
| `/funnel` | Cohorte completa más reciente; alternativa provisional si no hay completa |
| `/funnel?cohort_month=2026-09` | Cohorte mensual histórica o provisional, sin meses futuros |

`period` es obligatorio: today, current_week, last_7_days, current_month, last_30_days, ytd o last_12_months. Valor desconocido: 422 INVALID_PERIOD. Cohorte inválida/futura: 422 INVALID_COHORT; mes válido sin cuentas observables: 404 NOT_FOUND.

Todos incluyen `data_origin` y `freshness`. El origen puede ser demo, real, unknown (legado sin acreditar) o mixed (agregados de diferentes orígenes). Mostrar fechas reales de cálculo y corte, sin sustituirlas por la hora de consulta. La UI muestra avisos si el cálculo o una fuente tiene más de 24 h.

## Resumen, series y planes

Los agregados de PostgreSQL siguen siendo la fuente del resumen/series/planes. No se derivan ingresos o cancelaciones desde las tres etapas del embudo. Un total de período requiere todos sus días y origen comparable; falta de datos devuelve null. Las variaciones requieren denominador positivo y origen coincidente. Los cortes de activos/pago/MRR se muestran explícitamente incluso si el último dato es antiguo.

Los intervalos horarios se consultan en America/Santiago, desde medianoche inclusive hasta la siguiente medianoche exclusiva. Cada fila conserva `bucket_minutes`; el legado era de 180 minutos y las nuevas filas tienen 60 por defecto. Los buckets diarios/semanales/mensuales con días ausentes devuelven null. El frontend no rellena huecos, no cambia la granularidad y rechaza series desalineadas.

Planes consulta el máximo `as_of`, conserva los precios del snapshot y representa un precio cero como $0. Una cuota con población cero es null. RF04.03 permanece parcial: no existe unidad facturable acordada ni campo nuevo para inventarla. La interfaz dice «Cantidad registrada» y avisa de esa definición pendiente.

## Cohortes

`app/analytics_models.py` contiene cinco modelos registrados desde `app/models.py`: cuentas analíticas, acciones, pagos, frescura de fuentes y cachés mensuales. No contienen contraseñas, correos, mensajes, diagnósticos ni prescripciones. Los identificadores externos deben ser técnicos; la integración no debe introducir contenido personal en ellos.

Una cuenta pertenece al mes calendario de su creación en Santiago. Su ventana es `[created_at, created_at + 30 días)`: el instante exacto del día 30 queda fuera. Se cuenta una sola vez por etapa. El corte común es el mínimo entre ahora y `available_through` de las fuentes necesarias. Nunca se proyectan eventos posteriores al corte.

1. Cuentas creadas.
2. Cuentas con al menos una acción válida de su perfil dentro de la ventana.
3. Cuentas activas cuyo uso válido precede estrictamente al primer cobro exitoso mayor que cero, con suscripción activa al cobro, dentro de la ventana. Una prueba gratuita, fallo o cargo cero no es pago. No se sustituye un primer cobro anterior al uso por uno posterior.

Acciones técnicas del contrato local:

| Perfil | Acciones |
|---|---|
| elder | message_sent, mood_recorded, game_started, entertainment_played |
| family | elder_status_viewed, alert_detail_viewed, care_coordination_recorded |
| caregiver | observation_recorded, medication_confirmed, care_task_updated |
| doctor | patient_health_viewed, medication_plan_saved |

La correspondencia con eventos móviles reales aún no está entregada. Estos nombres son el contrato interno preparado, no prueba de integración móvil. Se prefiere origen real cuando existen cuentas reales; nunca se completa una cohorte real con cuentas demo. Acciones/pagos de un origen incompatible o perfiles desconocidos anulan la etapa afectada como `not_comparable`. Fuente necesaria ausente: `missing_source`. Denominador cero: tasas null; numerador cero sobre población válida positiva: 0. La primera etapa no tiene tasa contra etapa anterior.

La respuesta incluye mes, corte, cuentas, ventanas completas, estado provisional, opciones históricas y dos tasas por etapa. Descargas se presentan acumuladas en un bloque independiente, con origen/corte/cálculo propios, sin conversión hacia cuentas.

## Actualización y futura inyección

`AnalyticsSource` registra `(name, data_origin)`, `available_through`, `updated_at` y `revision`. Nombres: accounts, activity, payments, daily, hourly y plans. La marca de cobertura debe indicar hasta cuándo la fuente es completa, incluso si no hubo eventos. No equivale al último evento recibido. La integración debe validar fechas/orígenes y actualizar datos y fuente en la misma transacción, incrementando revision al modificar observaciones. Identificadores externos únicos por origen evitan duplicados en cuentas/acciones/pagos.

No se creó un endpoint de ingesta: transporte, autenticación y mapeo de fuentes reales siguen pendientes. No cargar manualmente datos reales con el seed.

`ADMIN_COMMERCIAL_WORKER_ENABLED=true` por defecto activa un proceso local que revisa las cohortes cada minuto y recalcula una vez por día de negocio, o cuando cambia la firma de fuentes. También existe cálculo bajo demanda al consultar. Las cachés se guardan en PostgreSQL; un bloqueo transaccional evita duplicarlas entre procesos. No llama a proveedores ni altera fechas de fuentes. El resumen, series y planes esperan sus agregados externos: este worker no inventa una actualización diaria de esos datos.

## Migración, demo y validación

La migración 0007 agrega tablas/columnas sin borrar registros. Agregados anteriores quedan unknown. Su downgrade conserva las observaciones deliberadamente: no es una reversión destructiva del esquema. El arranque habitual de Compose aplica `alembic upgrade head`.

El modo de desarrollo `scripts.seed --only-empty` puede añadir cohortes demo si su conjunto de tablas/fuentes está vacío; conserva cualquier dato existente. La demo contiene tres meses, perfiles móviles, uso y pagos coherentes. No se refresca artificialmente en cada arranque: con el tiempo mostrará aviso de fuente antigua. Para revisar este código en Docker, ejecutar desde la carpeta del backend `docker compose up -d --build api`; no se necesita borrar volúmenes. Esta entrega se verificó en una base temporal; no se actualizó ni reinició la API habitual del usuario.

Pruebas: reglas de actividad/pagos/ventanas/corte, frescura, cachés diarias, orígenes, límites horarios, vacíos y permisos; servicios y renderizado frontend; migración 0006→0007 y caché concurrente en PostgreSQL temporal (`tests/check_commercial_postgres.py`, estrictamente limitado a bases `agecare_seed_check_*`). La integración móvil/pagos y la aprobación visual del usuario quedan pendientes.
