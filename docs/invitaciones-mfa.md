# Invitaciones y MFA de la consola

## Recuperación de contraseña por correo — 10 de noviembre de 2026

Desde «¿Olvidaste tu contraseña?» del login, la persona introduce su correo. POST `/api/v1/admin/auth/password-reset/request` devuelve siempre el mismo mensaje 202 para correos válidos, incluidos inexistentes, inactivos, invitaciones pendientes o solicitudes limitadas. Solo cuentas activas con contraseña generan correo. Se eligieron 30 minutos de vigencia, un minuto entre solicitudes aceptadas y máximo tres por cuenta en una hora. Una solicitud aceptada invalida enlaces anteriores. Solicitar el enlace conserva la contraseña y las sesiones actuales.

El token aleatorio de 48 bytes se guarda como hash SHA-256. El enlace usa el fragmento `/recuperar-contrasena#token=…`, generado desde ADMIN_FRONTEND_URL. La pantalla retira el fragmento del historial al abrir y envía token/contraseña en el cuerpo de POST `/auth/password-reset/confirm`, con Cache-Control no-store. Usa contraseña de 8–128 caracteres y confirmación en pantalla, conforme política existente. Nunca envía la contraseña por correo ni inicia sesión automáticamente.

Al confirmar se bloquean la cuenta y la recuperación, se valida uso/vencimiento/revocación/versión y el correo original. El nuevo hash Argon2id, uso del enlace, revocación de sesiones/refresh, incremento de auth_version y auditoría se guardan juntos. Se cierran enrolamientos MFA pendientes para que credenciales anteriores no permitan terminarlos. MFA ya configurado y códigos de recuperación se conservan. Para acceder se vuelve al login y se verifica el segundo factor habitual. Este flujo recupera la contraseña, y la recuperación de un autenticador perdido sigue siendo un proceso independiente.

Migración **0014** añade `admin_password_resets` con estado de token y cola cifrada. El correo se envía después del commit mediante el mismo proveedor SMTP/Brevo y ADMIN_MAIL_WORKER_ENABLED. Se validan nuevamente estado de cuenta, correo, versión y vigencia antes de enviar. Cinco intentos con espera creciente. Tras enviar el enlace se elimina el token de la copia cifrada y se conserva solo el destino cifrado mientras se valida la recuperación. Al cambiar la contraseña se encola un aviso de confirmación sin credenciales. La cola puede repetir un correo si hay caída después de aceptación y antes del commit, como las invitaciones. No hay garantía de entrega al buzón por el estado sent.

Para probar en Docker local, conservar la clave de cifrado y Brevo ya configurados, usar `ADMIN_FRONTEND_URL=http://localhost:5173` y ejecutar `docker compose up -d --build api` desde el backend. Compose aplica 0014 y prepara permisos del rol limitado. Luego probar desde el login con una cuenta propia activa y correo accesible. Cambia la contraseña de esa cuenta y cierra sus sesiones. En Render se debe aplicar 0014 por el procedimiento separado de migraciones y conceder DML de la tabla al rol limitado antes del nuevo despliegue. No copiar la conexión propietaria a Render.

Pruebas aisladas de tokens, límites, MFA, sesiones y envío simulado aprobadas. Migración y carreras de confirmación/solicitud verificadas en PostgreSQL temporal, retirado al terminar. Sin migración local/Neon, reinicios de la API habitual ni restablecimientos de cuentas reales realizados por el agente. Entrega real y revisión visual pendientes del usuario. Diseño contrastado con la [guía de recuperación de OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

## Brevo por HTTPS — 10 de noviembre de 2026

El transporte compartido admite Brevo para invitaciones y avisos internos de incidentes. Para seleccionarlo, añadir al `.env` del backend junto a `docker-compose.yml` estos valores, conservando las claves existentes.

```ini
ADMIN_MAIL_PROVIDER=brevo
ADMIN_BREVO_API_KEY=CLAVE_PRIVADA_GUARDADA_LOCALMENTE
ADMIN_MAIL_FROM=CORREO_REMITENTE_VERIFICADO_EN_BREVO
ADMIN_MAIL_WORKER_ENABLED=true
```

La clave API necesita acceso a emails transaccionales. El remitente debe estar registrado y verificado en Brevo. Con este proveedor las credenciales SMTP no intervienen. `ADMIN_FRONTEND_URL` debe apuntar a la consola local al probar invitaciones locales. Los nuevos incidentes avisan automáticamente a cuentas activas admin/support con contraseña configurada. La antigua variable `ADMIN_INCIDENT_MAIL_RECIPIENTS` quedó retirada y se ignora si permanece en el entorno. Antes de enviar se vuelve a comprobar cuenta, correo y rol. Cambiar destinatarios no reenvía incidentes antiguos.

`python -m scripts.check_mail` comprueba HTTPS/autenticación mediante GET de estadísticas transaccionales, sin enviar mensajes. Su resultado no certifica aprobación del remitente ni llegada a la bandeja de entrada. La prueba real se realiza con un nuevo incidente o una invitación autorizada al destinatario indicado. Aplicar cambios de código/configuración mediante reconstrucción local autorizada. Los trabajadores pueden procesar correos ya encolados al arrancar.

Se conserva la cola cifrada, el envío posterior al commit y los cinco intentos existentes. Brevo acepta el correo mediante POST `/v3/smtp/email`; `sent` indica aceptación del proveedor, no entrega confirmada. Caída tras aceptación y antes del commit puede producir duplicados en el reintento. Clave y cuerpos del proveedor excluidos de logs/errores públicos. SMTP sigue disponible mediante `ADMIN_MAIL_PROVIDER=smtp`, valor predeterminado.

Validación local de esta entrega, 47 pruebas con transportes simulados aprobadas. Consulta real de solo lectura con la clave local confirmó acceso HTTPS a Brevo. Remitente y entrega pendientes de confirmación del usuario. No se enviaron correos ni se reinició Docker durante estas comprobaciones. No hay cambios de esquema ni migraciones.

Referencias oficiales de [envío transaccional](https://developers.brevo.com/reference/send-transac-email) y [claves API](https://help.brevo.com/hc/en-us/articles/40159485019794-Create-and-manage-your-API-keys).

## Configuración

1. Instala `pip install -r requirements.txt` en el entorno virtual del backend.
2. Agrega a tu `.env` los parámetros de `.env.example`. No reemplaces tu configuración existente de base de datos ni JWT.
3. Genera una clave **una sola vez**: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Guárdala como `ADMIN_ENCRYPTION_KEY`. Consérvala y respáldala: perderla impide descifrar los autenticadores y correos pendientes. Nunca la subas a GitHub. Cambiarla requiere una migración explícita de secretos.
4. Configura `ADMIN_SMTP_HOST`, `ADMIN_SMTP_PORT`, `ADMIN_SMTP_SECURITY`, `ADMIN_SMTP_USERNAME`, `ADMIN_SMTP_PASSWORD` y `ADMIN_MAIL_FROM` con los datos de tu proveedor. STARTTLS suele usar puerto 587 y SSL puerto 465; confirma los parámetros de tu proveedor. `none` se admite solo en desarrollo para un servidor de pruebas local.
5. Define `ADMIN_FRONTEND_URL` con la dirección de Agecare-administracion. En producción debe ser HTTPS. El hosting debe resolver las rutas del frontend a `index.html`.
6. Aplica `alembic upgrade head` en el backend y reinicia ambos servicios. La migración agrega tablas/columnas; no borra cuentas existentes. Se probó sobre SQLite nuevo y una estructura anterior; valida la migración sobre una copia de tu PostgreSQL antes del despliegue.

No se configuraron credenciales SMTP reales ni se aplicó la migración a tu base de datos durante el desarrollo.

## Política

Excepción explícita para pruebas (4 de noviembre de 2026): en `ADMIN_ENVIRONMENT=dev`, `ADMIN_MFA_TEST_EXEMPT_ACCOUNT_IDS` admite UUID separados por comas de cuentas sin obligación individual (`mfa_required=false`). Omite solamente la obligación por rol para esos UUID; una cuenta con MFA habilitado sigue verificando su código. No aplica en staging/prod ni elimina obligación individual. Vacío por defecto. Para retirar la excepción, quitar el UUID y redesplegar: accesos/refresh siguientes vuelven a comprobar la política. No desactivar roles globales para una sola cuenta de prueba.

- `ADMIN_MFA_REQUIRED_ROLES=admin` exige MFA a administradores. Para exigirlo a todos: `admin,analyst,support,editor,moderator`.
- Una invitación puede exigir MFA adicionalmente, aunque su rol sea opcional. Esta exigencia queda guardada en la cuenta.
- Las cuentas activas existentes que todavía no tengan MFA obtienen un token de configuración de diez minutos tras verificar su contraseña. Ese token no permite acceder a la API administrativa.
- Para iniciar sesión con MFA se envía `otp_code` **o** `recovery_code`, además de la contraseña. Se rechaza la reutilización del código TOTP durante su intervalo. Los diez códigos de recuperación se guardan como hashes y se consumen una sola vez.
- Activar/desactivar MFA invalida access y refresh tokens anteriores. Renovar los códigos de recuperación invalida la lista anterior. No se permite desactivar MFA obligatorio.
- Perder el autenticador y todos los códigos requiere una recuperación de identidad fuera de este flujo. No existe un bypass de MFA ni un restablecimiento de MFA por correo.

## Invitaciones

POST `/users` sin contraseña crea la cuenta pendiente, un token aleatorio de un solo uso (solo se guarda su hash) y un correo cifrado en una cola persistente. El enlace vence a las 24 horas por defecto (`ADMIN_INVITATION_HOURS`). El token va en el fragmento del enlace y los endpoints públicos lo reciben en el cuerpo, para que no aparezca en URLs de peticiones HTTP.

El proceso de la API envía los correos de la cola después del commit. Reintenta errores SMTP hasta cinco veces con espera creciente; informa en la cuenta si el envío falló. SMTP no garantiza exactamente un envío si el proceso cae después de que el proveedor acepta el mensaje, pero antes del commit: el mismo enlace puede llegar repetido y continúa siendo de un solo uso. La copia cifrada del correo se elimina al enviarse o cancelarse.

Reenviar invalida todos los enlaces anteriores y permite recuperar una invitación vencida o cancelada. Hay un intervalo mínimo de un minuto entre envíos. Cancelar invalida el token sin activar/desactivar cuentas ya configuradas. Las cuentas pendientes no pueden cambiar de correo ni activarse mediante PATCH. Si una cuenta fue desactivada o eliminada, un enlace anterior nunca puede reactivarla.

## Endpoints

Todos usan el prefijo `/api/v1/admin`. Los endpoints públicos no requieren una sesión administrativa.

| Endpoint | Acceso | Función |
|---|---|---|
| GET `/users/policy` | Admin | Dominios, roles con MFA obligatorio y vencimiento de invitaciones |
| POST `/users/{id}/invitation/resend` | Admin | Reenviar y rotar token |
| POST `/users/{id}/invitation/cancel` | Admin | Cancelar invitación |
| POST `/auth/invitations/inspect` | Token de invitación | Ver identidad, vencimiento y política |
| POST `/auth/invitations/setup` | Token de invitación | Obtener QR y clave manual del autenticador |
| POST `/auth/invitations/accept` | Token de invitación | Guardar contraseña, verificar MFA y activar cuenta |
| POST `/auth/mfa/setup` | Sesión y contraseña | Iniciar MFA opcional en cuenta existente |
| POST `/auth/mfa/enrollment/setup` | Token de configuración | Obtener QR y clave manual |
| POST `/auth/mfa/enrollment/confirm` | Token y TOTP | Confirmar MFA y entregar códigos de recuperación |
| POST `/auth/mfa/recovery-codes` | Sesión, contraseña y segundo factor | Renovar códigos |
| POST `/auth/mfa/disable` | Sesión, contraseña y segundo factor | Desactivar solo cuando sea opcional |

Los tokens y secretos no se devuelven en el listado de cuentas ni se registran en auditoría. La aceptación, el reenvío, la cancelación y los cambios confirmados de MFA sí generan eventos de negocio. Los endpoints que devuelven QR, claves y códigos usan `Cache-Control: no-store`. Los intentos fallidos de confirmación se limitan a diez por token; las pruebas fallidas de contraseña/segundo factor bloquean temporalmente la cuenta.

## Validación

### Preparación de correo del 10 de octubre de 2026

Se restauró `.env.example` sin secretos y se añadió `scripts/check_mail.py`. El proveedor real está pendiente de indicar por el usuario. No se leyó ni modificó el `.env` existente, no se regeneraron claves ni se enviaron mensajes. El diagnóstico tiene dos pruebas aprobadas con transporte simulado.

Completar solo las variables SMTP y remitente necesarias en el `.env` existente con parámetros del proveedor; no copiar los campos JWT/Fernet vacíos del ejemplo sobre claves reales. Para probar conexión sin enviar mensajes:

```powershell
# Backend ejecutado localmente, desde su carpeta:
.\venv\Scripts\python.exe -m scripts.check_mail
# Backend Docker: después de incorporar código/env en un despliegue autorizado:
docker compose exec api python -m scripts.check_mail
```

El comprobador conecta, negocia TLS y autentica cuando existe usuario; no imprime respuestas SMTP ni credenciales y no envía correos. Ejecutarlo implica una conexión al proveedor y debe ser una prueba explícita. Su éxito no acredita entrega, validación del remitente ni ausencia de spam.

Cambiar `.env` requiere recrear el servicio para que Compose lo cargue; un restart no basta. Incorporar código nuevo requiere reconstrucción: `docker compose up -d --build api`. No se ejecutó ese comando en esta preparación. En Docker, `localhost` de la API se refiere a su contenedor, no al PC ni a otro servicio. El enlace necesita un `ADMIN_FRONTEND_URL` accesible desde el dispositivo del destinatario; localhost solo sirve en el mismo equipo.

Después de confirmar proveedor y configuración, validar con una cuenta de prueba autorizada y dominio permitido: crear invitación desde consola, revisar envío, recepción y apertura/aceptación de enlace. No confundir estado sent con entrega final: significa aceptación SMTP. Si una invitación agotó reintentos, reenviarla desde consola tras corregir configuración. No introducir una ruta pública para leer tokens ni mensajes de la cola.

`pytest -q` usa SQLite en memoria y correo simulado, sin enviar mensajes a destinatarios reales. `npm test` y `npm run build` validan el frontend. Para verificar entrega real, completa SMTP y la URL pública y envía una invitación a una cuenta de prueba autorizada desde la consola.

Se usan [PyOTP](https://pyauth.github.io/pyotp/) para TOTP, [Fernet](https://cryptography.io/en/latest/fernet/) para cifrado autenticado y [smtplib](https://docs.python.org/3/library/smtplib.html) para SMTP.
