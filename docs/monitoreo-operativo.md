# Monitoreo operativo — fase 05

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
