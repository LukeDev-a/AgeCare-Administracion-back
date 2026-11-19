# Actividad y adopción con fuente compartida — 19nov2026

## Estado remoto tras migración — 19nov2026

Neon ya está en0022; aplicada por autorización del usuario con scripts.migrate_neon_0022. Las dos tablas analíticas nuevas están vacías y el conjunto compartido no está preparado en remoto. No se tocaron sus agregados existentes ni se creó marker. Los resultados de preparación descritos aquí corresponden solo a local. Siguiente paso técnico separado: preparar el conjunto remoto con preservación de datos según alcance autorizado; el script local debe seguir rechazando Neon. Push/despliegue backend/frontend pendientes del usuario; ver render-neon.md.

## Alcance acordado

El usuario autoriza actualizar diariamente Actividad por perfil y Uso por funcionalidad hasta **24dic2026**. Después retira de este trabajo la unificación de Pagos con Uso comercial: **no ampliar el directorio ni cambiar suscripciones, cobros o el proceso comercial existente**. Las cifras de esos otros módulos siguen siendo conjuntos separados.

Los valores de actividad/adopción dejan de ser constantes independientes: se calculan desde sesiones sintéticas asociadas a cuentas analíticas. No son telemetría móvil real ni crean cuentas de acceso, pacientes, vínculos, credenciales, correos o llamadas a proveedores.

## Fuente y cálculos

Migración0022 tras0021 crea únicamente `analytics_usage_accounts` (id, perfil, fecha de creación, origen) y `analytics_usage_sessions` (id, cuenta, fecha, duración, funciones, origen), con FK/índices/restricción de duración positiva. Las identidades son exclusivamente analíticas y no forman parte del directorio administrativo. `app/usage_demo.py` usa IDs deterministas, catálogo `features` existente y origen demo.

Historial de preparación desde1may2026: permite las26semanas del gráfico y ventanas7/30/90. Cada día crea12–20cuentas distribuidas entre perfiles, actividad recurrente con cuentas sin uso o que dejan de volver, sesiones de distinta duración y funciones aplicables. No se guardan sesiones posteriores al cierre procesado. SOS mantiene baja frecuencia en la generación; no se ejecuta ningún motor de alertas.

- Activos: cuentas distintas con sesión en los últimos7/30/90días completos.
- Sesiones por semana: sesiones de la ventana ×7/días ÷cuentas activas del perfil.
- Duración: promedio de segundos de esas sesiones.
- Retención30d: de las cuentas activas en los30días anteriores a la ventana reciente, proporción que volvió en los últimos30días. No es baja de cuenta ni eliminación; mantiene ventana fija al cambiar selector. Si no existe base se almacena0 con el contrato heredado; en las fechas de presentación hay base para los cuatro perfiles.
- Crecimiento8semanas: activos de los últimos7días respecto de los7días de ocho semanas antes. Mantiene comparación fija al cambiar selector. Sin denominador se conserva0 según contrato heredado.
- Actividad semanal: cuentas distintas por semana ISO, hasta26semanas; última semana parcial al corte.
- Adopción: cuentas distintas que usaron cada función en las mismas sesiones/ventana ÷activos del mismo perfil. Una persona puede usar varias funciones. Ausencia de activos sigue siendo no calculable mediante las reglas existentes; no se confunde con cero calculado.

Los endpoints actuales y sus permisos se conservan. Se añade `data_through` nullable a resumen/semanas/matriz/ranking/avisos. La UI distingue **Actividad hasta el…** de la fecha real del cálculo. La comparación/retención tienen explicación acorde a las ventanas.

Lecturas PostgreSQL toman el advisory lock compartido del cierre durante la transacción HTTP; el worker toma el exclusivo. Así una misma respuesta no mezcla usos de ayer con activos del nuevo cierre si la actualización coincide entre consultas. Distintas pantallas consultadas antes/después del commit pueden mostrar diferentes cierres hasta el próximo autorefresco; data_through permite identificarlos.34 pruebas dirigidas repetidas tras este último ajuste; API local reconstruida.

## Actualización y fecha límite

`ADMIN_USAGE_DEMO_REFRESH_ENABLED=false` por defecto fuera de Compose. Compose dev lo habilita, pero el worker no carga nada hasta la preparación explícita. Requiere entorno dev. Worker al inicio y cada60s con proceso activo; transacción única y advisory lock compartido con preparador evitan cargas simultáneas. Cuenta/sesión/ventanas/marcador se confirman juntos.

Se cierra **el día anterior**, sin inventar la actividad restante del día actual. Una suspensión recupera todos los días pendientes una vez. Marcador `analytics_sources` con nombre `usage_demo_refresh`, origen demo y corte exclusivo a medianoche de Santiago; repetir el mismo cierre no modifica filas ni fechas. Nunca toca fuentes comerciales. Los trabajos de preparación y el worker usan la misma función.

El último día observable es24dic2026. Se completa al activarse el proceso desde25dic; después queda congelado, sin generar sesiones ni rejuvenecer la fecha. No se usan pingers ni servicios programados externos. Render suspendido no ejecuta trabajos.

## Operación local autorizada

1. Construir imagen y aplicar Alembic hasta0022 conservando volumen.
2. `python -m scripts.prepare_usage_demo` solo informa si está preparado; `--apply` respalda filas anteriores de los tres agregados y otras fuentes en archivo cifrado con la clave existente, prepara la fuente y verifica huellas de los módulos ajenos antes de commit. Solo admite PostgreSQL local dev, no Neon. No ejecuta seed ni rota claves.
3. En Compose montar backups del host en `/srv/app/backups` al ejecutar el preparador para conservar la evidencia.
4. Iniciar API habitual; seed --only-empty conserva los grupos ya cargados. Refrescar consola.
5. `python -m scripts.check_usage_demo` verifica con consultas de solo lectura cuentas activas/adopción contra sesiones, límites y ausencia de eventos futuros. Solo destino local.

Preparación local19nov2026: **3.222cuentas analíticas/86.214sesiones**, corte18nov. Respaldo ignorado `backups/usage-demo-20261119T042440628099Z/before.enc` contiene las filas de los agregados anteriores y huellas de tablas ajenas; report.json confirma commit y conservación de41tablas ajenas, pagos/directorio/Uso comercial incluidos. No es respaldo completo de toda la base. Verificación PostgreSQL confirmó12ventanas de perfiles y117ventanas de funciones, misma fuente y ausencia de actividad futura. Local migrado0021→0022; no Neon, push o despliegue remoto.

## Despliegue pendiente

Validación final:579pruebasbackend completas aprobadas;6nuevas pruebas de uso repetidas tras el ajuste final de fecha de corte.25pruebasfrontenddirigidas/build/lint correctos. APIlocal respondehealth200 y aplicación preparada en PostgreSQL local con comprobación independiente de los12/117agregados frente a sesiones. Sin nueva revisión visual acreditada.

Neon permanece0021. No ejecutar el preparador local contra Neon. Para remoto habrá que preparar una operación específica con respaldo y verificación antes de activar el flag; no basta cambiar la variable. Backend Render nuevo exigirá0022 antes de arrancar. No subirlo antes de planificar esa migración. Preservar precios/pagos/operaciones existentes y la clave de cifrado.
