# Invitaciones y MFA de la consola

## Configuración

1. Instala `pip install -r requirements.txt` en el entorno virtual del backend.
2. Agrega a tu `.env` los parámetros de `.env.example`. No reemplaces tu configuración existente de base de datos ni JWT.
3. Genera una clave **una sola vez**: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Guárdala como `ADMIN_ENCRYPTION_KEY`. Consérvala y respáldala: perderla impide descifrar los autenticadores y correos pendientes. Nunca la subas a GitHub. Cambiarla requiere una migración explícita de secretos.
4. Configura `ADMIN_SMTP_HOST`, `ADMIN_SMTP_PORT`, `ADMIN_SMTP_SECURITY`, `ADMIN_SMTP_USERNAME`, `ADMIN_SMTP_PASSWORD` y `ADMIN_MAIL_FROM` con los datos de tu proveedor. STARTTLS suele usar puerto 587 y SSL puerto 465; confirma los parámetros de tu proveedor. `none` se admite solo en desarrollo para un servidor de pruebas local.
5. Define `ADMIN_FRONTEND_URL` con la dirección de Agecare-administracion. En producción debe ser HTTPS. El hosting debe resolver las rutas del frontend a `index.html`.
6. Aplica `alembic upgrade head` en el backend y reinicia ambos servicios. La migración agrega tablas/columnas; no borra cuentas existentes. Se probó sobre SQLite nuevo y una estructura anterior; valida la migración sobre una copia de tu PostgreSQL antes del despliegue.

No se configuraron credenciales SMTP reales ni se aplicó la migración a tu base de datos durante el desarrollo.

## Política

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

`pytest -q` usa SQLite en memoria y correo simulado, sin enviar mensajes a destinatarios reales. `npm test` y `npm run build` validan el frontend. Para verificar entrega real, completa SMTP y la URL pública y envía una invitación a una cuenta de prueba autorizada desde la consola.

Se usan [PyOTP](https://pyauth.github.io/pyotp/) para TOTP, [Fernet](https://cryptography.io/en/latest/fernet/) para cifrado autenticado y [smtplib](https://docs.python.org/3/library/smtplib.html) para SMTP.
