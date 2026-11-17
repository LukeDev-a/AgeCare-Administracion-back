# Suscripciones y cobros persistidos

17nov2026. Usuario autoriza persistencia del módulo visual de pagos. Sigue siendo una simulación para presentación, sin pasarela, tarjetas, dinero real, correo ni efectos sobre acceso móvil. No implica integración de facturación externa. Identidades del directorio ficticio autorizado, tarifas ilustrativas independientes de plan_prices.

## Almacenamiento y permisos

Migración0019 posterior a0018 añade payment_subscriptions (11 columnas) y payment_charges (9), PK UUID, códigos únicos, FK al directorio/suscripción, versión, origen demo e historial JSON. Restricciones de importes/estados/versiones. FK sin borrado en cascada; no hay endpoint de eliminación. Modelos y DBML actualizados:43 tablas/432 columnas/18 FK.

Rutas bajo /api/v1/admin/payments, solo admin a través de require(staff) READ/WRITE. Exige la misma habilitación dev+end_users_demo_enabled del directorio. No funciona como servicio real al cambiar entorno. Mantener data_origin demo y no añadir secretos financieros. Runtime limitado obtiene permisos mediante scripts.run_api; no retirar protecciones de auditoría.

- GET vacío devuelve listas vacías; no genera datos.
- POST /initialize crea una suscripción y dos cobros por cuenta solo si ambas tablas están completamente vacías. Advisory lock PostgreSQL y transacción evitan cargas competidoras. Conserva instalaciones con registros, UUID, fechas, versiones y movimientos; no rellena automáticamente nuevas cuentas ni huecos. Un fallo revierte toda la carga. Se generan precios ilustrativos3990/6990/9990, no se consumen tarifas configuradas.
- POST /{subscriptions|charges}/{UUID}/operate recibe action, version, reason5–500, confirmed booleano estricto y days1–90 entero estricto solo en extend. Actor real de sesión. SELECT FOR UPDATE y versión impiden cambios concurrentes silenciosos. Respuestas completas del estado canónico; commit/rollback de get_db.
- Cancelar detiene renovación conservando fin/cuenta/cobros. Extender suma días sin cobrar/resolver mora, solo no canceladas. Reembolso completo solo aprobado, una vez; conserva suscripción. Nunca actuar sobre registros de origen distinto de demo.

Consulta une nombre/correo/estado actual de app_accounts; homónimos se distinguen por UUID. Los roles por vínculo siguen siendo del directorio y no se convierten en tipos de suscripción. GET registra payments.read sin copiar nombres/correos; initialize/cancel/extend/refund auditan cambios y motivo. Historial persistido guarda actor/fecha/operación/motivo. Nada se envía a direcciones de ejemplo.

## Validación y despliegue

546 pruebas backend y204 frontend aprobadas; nuevas pruebas cubren persistencia entre consultas, idempotencia, conservación de cuentas, versiones, permisos, validación, reembolso repetido, rollback ante fallo de auditoría y migración sobre SQLite. Build/lint frontend dirigidos aprobados. No acreditar pruebas de concurrencia real con estos tests SQLite; la serialización de runtime usa locks PostgreSQL.

Docker local reconstruido sin tocar volúmenes:0018→0019,32 cuentas conservadas,0 suscripciones/0 cobros antes de la primera visita, health200 y GET protegido401 sin sesión. Verificado runtime con SELECT/INSERT/UPDATE en tablas nuevas y sin UPDATE de audit_log. Respaldo de directorio y versión (no base completa) en backups/payment-storage-local-20261117/before.sql, ignorado por Git/Docker, SHA2561864B7A7022097C49B73F97AB2F454C83B9A76CED1584EE97D0A60C47C7DF58E.

No se ejecutó en Neon ni se hizo push/deploy. Antes del próximo despliegue hay que aplicar migraciones pendientes hasta0019 con propietario y preparar permisos del rol runtime en las tablas nuevas. Conservar la clave de cifrado y las restricciones de auditoría. Las operaciones antiguas solo en memoria no se pueden recuperar tras haberse perdido al salir.
