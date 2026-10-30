# Uso por funcionalidad — estados de cálculo

27 de octubre de 2026. El usuario autorizó resolver RF08.04–06, antes diferidos. Rutas existentes bajo `/api/v1/admin/metrics/features`: adoption, top y alerts. Permisos sin cambios: admin/analyst/support; editor/moderator 403 y sesión inválida 401. Sin migración ni nuevas rutas.

## Regla compartida

`app/routers/metrics_features.py::_calculate` utiliza Feature.applicable_roles, FeatureUsageWindow.users y RoleActivityWindow.active_users para el mismo days_window. Devuelve porcentaje y AdoptionCalculation; las tres rutas usan esa función.

| Estado | Motivo | Porcentaje |
|---|---|---|
| not_applicable | not_applicable | null |
| not_calculable | missing_active_users | null |
| not_calculable | no_active_users | null |
| not_calculable | missing_usage | null |
| not_calculable | invalid_data (negativos o uso mayor que activos) | null |
| calculated | null | users / active_users |

No aplica tiene prioridad. Un cero válido requiere fila de uso users=0 y activos positivos conocidos. **Una fuente debe guardar el registro cero explícitamente**: no se interpreta una fila ausente como ausencia de uso. La aplicación no completa ni cambia registros por esta consulta.

La razón y los conteos permiten diagnosticar un valor no calculable sin confundirlo con no aplicabilidad. No representan prueba de cobertura temporal completa ni de sincronización de lotes; no hay identificador de lote/ciclo añadido.

## Payload y compatibilidad

adoption conserva days/roles/features/computed_at y feature_key/name/adoption. Añade calculation_details por feature, alineado con roles y adoption. Cada entrada contiene role, applicable, status, reason, users y active_users. En no aplicable los conteos se omiten mediante null.

Tanto No aplica como No calculable son null en adoption, y **deben interpretarse con calculation_details**. Clientes antiguos que interpreten todo null como No aplica necesitan actualizarse; mantener la forma del campo no preserva esa interpretación antigua incorrecta.

top filtra los no numéricos antes de ordenar y aplicar limit. alerts solo compara porcentajes válidos con rate < threshold. Cero válido se conserva en ranking y genera alerta si está bajo el umbral. expected_low y su orden/contexto siguen iguales.

TopOut y AlertsOut añaden calculable_only=true para acreditar la política aplicada. La consola nueva no presenta resultados antiguos como ranking/alertas validados si ese campo está ausente. En matriz sin metadata muestra advertencia y no atribuye causa a un null.

El porcentaje no se redondea en backend a un cero falso cuando users>0. La UI utiliza <0,1 % para valores positivos inferiores a 0,001 de proporción; no altera el valor del payload. No se limita un porcentaje inconsistente a 100 %: se devuelve invalid_data.

## Interfaz y operación

HeatmapTable distingue No aplica/No calculable/cero, muestra causa no calculable y valida longitud/orden de metadata. FeatureAlertList y ranking conservan cero válido. Leyenda actualizada; retirado el aviso genérico antiguo de cero ambiguo para la API corregida.

Reconstruir la API de desarrollo con `docker compose up -d --build api`. No se requiere migración, borrado de datos ni rotación de clave. El agente no reinició servicios ni modificó datos de trabajo al implementar esta entrega.

Pruebas: `tests/test_feature_metrics_contract.py`, `tests/test_metrics.py`, matriz en `tests/test_role_permissions.py` y frontend `tests/features.test.cjs`. Revisión visual y resultados finales registrados en Requerimientos/fase-08/seguimiento.md del workspace. No cerrar la fase por existencia de pruebas sin aceptación del usuario.
