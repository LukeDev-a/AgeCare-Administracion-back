# Datos de demostración comercial

## Carga en Neon completada — 10 de noviembre de 2026

Usuario autorizó llevar a la consola pública la demostración preparada en local. Se cotejaron los 426 días históricos de Neon con las cifras locales, idénticas, y se respaldaron siete tablas analíticas antes de escribir en `backups/commercial-demo-20261110T213637Z`, excluido de Git/Docker, con huella SHA-256. Datos y secretos del respaldo no se publican.

Ejecutado `scripts.seed_commercial_demo --apply --target neon --complete-legacy-history` mediante la credencial limitada existente. Confirmados 125 días, 19.569 cuentas analíticas, 15.604 actividades, 2.850 pagos, 28 snapshots de planes y 18 horas completas. Los 426 días históricos quedaron clasificados como demo conservando sus cifras. Se aplicaron las protecciones de conflicto y transacción del script. No se copió la base completa ni se ejecutó scripts.seed destructivo.

Verificados con funciones de los routers sobre Neon los períodos mes actual, últimos 30 días, año en curso y últimos 12 meses. Mes actual con 3.405 descargas, 1.585 altas y 149 bajas. Cohorte septiembre con 3.921 cuentas, 3.124 activas y 413 activas que pasan a pago, seguimiento completo. Descargas acumuladas 57.610 y planes al corte 10 de noviembre con 27.972 usuarios. Sin inicio de sesión público del agente, revisión visual a cargo del usuario. Los registros futuros de diciembre siguen excluidos de resultados observados hasta su fecha. No requiere reinicio de Render.

La carga de `scripts.seed_commercial_demo` prepara datos del 29 de agosto al 31 de diciembre de 2026. Incluye el enlace entre el último dato legado de agosto y los meses solicitados de septiembre, octubre, noviembre y diciembre. El rango es fijo y los identificadores son reproducibles.

Solo se ejecuta con entorno `dev`. Comprueba conflictos en registros diarios, horarios y planes, y revierte si encuentra orígenes diferentes de demo en el rango afectado. Las inserciones y las fuentes demo se confirman en una transacción. Los reintentos conservan registros existentes y evitan duplicados. La carga añade cuentas analíticas sin correos, credenciales ni información personal. Los identificadores empiezan por `commercial-demo-2026-v1-`.

Desde la carpeta del backend se puede consultar el tamaño antes de cargar.

```powershell
.\venv\Scripts\python.exe -m scripts.seed_commercial_demo
```

Para PostgreSQL local de Compose en localhost, puerto 5432, base agecare_admin.

```powershell
.\venv\Scripts\python.exe -m scripts.seed_commercial_demo --apply --target local
```

Para llevar la misma demostración a Neon más adelante, usar la conexión limitada existente guardada en `.env.render`. Este paso escribe en la base publicada y requiere autorización para ese destino.

```powershell
.\venv\Scripts\python.exe -m scripts.seed_commercial_demo --apply --target neon
```

El despliegue del código conserva la carga como operación manual. En Render el arranque continúa sin ejecutar seed. No se requiere migración nueva.

La demostración contiene 125 días, 19.569 cuentas analíticas, 15.604 acciones y 2.850 pagos, incluidos eventos futuros de prueba. El cálculo de cohortes utiliza el instante actual como límite. Las opciones futuras no aparecen, los pagos y usos futuros quedan fuera del resultado observado y los snapshots de planes se generan solamente hasta la fecha de carga. El 10 de noviembre se añadieron 28 filas de planes y 15 intervalos horarios completos del día. Los conteos futuros son simulaciones preparadas y no actividad real.

Para revisar la consola, actualizar Uso comercial y comparar Mes en curso, Últimos 7 días y Últimos 30 días. En Últimos 12 meses se ven los bloques de septiembre, octubre y noviembre. En el embudo se pueden seleccionar septiembre completo y octubre/noviembre provisionales. La selección actual del resumen no ofrece un rango arbitrario para visualizar diciembre por adelantado.

Los agregados anuales que incluyan filas antiguas `unknown` siguen sin ser comparables. La carga conserva esos registros, por lo que no elimina todos los avisos de información faltante del historial. Las fuentes de demostración pueden volver a mostrar antigüedad al pasar 24 horas.

Para regularizar los registros diarios del seed antiguo de enero al 28 de agosto de 2026, el usuario autorizó su clasificación como demo para probar Año en curso. La opción explícita `--complete-legacy-year` conserva cifras y computed_at, exige cobertura diaria completa y rechaza orígenes diferentes de unknown/demo. Usarla solo tras confirmar que esas filas son de prueba. Se puede combinar con el destino local o con Neon cuando se autorice allí.

```powershell
.\venv\Scripts\python.exe -m scripts.seed_commercial_demo --apply --target local --complete-legacy-year
```

Este ajuste cubre el año 2026. Los meses de 2025 que puedan aparecer en Últimos 12 meses conservan su clasificación anterior.

Para incluir el historial anterior de prueba en Descargas acumuladas y Últimos12meses, usar la opción explícita `--complete-legacy-history`. Regulariza el origen desde la primera fila diaria del seed hasta el 28 de agosto de 2026, exige continuidad y rechaza registros reales. Conserva las cifras y las fechas de cálculo. Este modo incluye el año en curso.

```powershell
.\venv\Scripts\python.exe -m scripts.seed_commercial_demo --apply --target local --complete-legacy-history
```

Prueba automatizada aislada aprobada con reejecución sin duplicados, rechazo de registros reales y exclusión de cohortes futuras. Verificación local del 10 de noviembre con las funciones de los routers y el motor de cohortes.
