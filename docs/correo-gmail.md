# Invitaciones mediante Gmail

Proveedor elegido por el usuario el 10 de octubre de 2026 para envíos puntuales de cuentas internas. SMTP ya está implementado; falta configurar la cuenta remitente y comprobar entrega real. No se leyó/modificó `.env`, no se cambiaron claves y no se reiniciaron servicios al escribir esta guía.

## 1. Preparar la cuenta remitente

Activar la verificación en dos pasos de Google y generar una contraseña de aplicación denominada AgeCare. Usar esa contraseña para SMTP, no la contraseña normal de Google ni el código temporal del autenticador. Guardarla solamente en el `.env` del servidor. No enviarla por chat ni subirla al repositorio.

- [Ayuda oficial de contraseñas de aplicación](https://support.google.com/accounts/answer/185833?hl=es).
- [Generar contraseña de aplicación](https://myaccount.google.com/apppasswords).

Algunas cuentas no ofrecen contraseñas de aplicación por restricciones de organización, Protección Avanzada o configuración de verificación. Si no está disponible, comprobar la política de la cuenta antes de intentar usar su contraseña normal.

## 2. Configurar el .env existente

Editar estas variables, sustituyendo marcadores localmente y evitando entradas duplicadas:

```dotenv
ADMIN_SMTP_HOST=smtp.gmail.com
ADMIN_SMTP_PORT=587
ADMIN_SMTP_SECURITY=starttls
ADMIN_SMTP_USERNAME=TU_CUENTA@gmail.com
ADMIN_SMTP_PASSWORD=TU_CONTRASENA_DE_APLICACION
ADMIN_MAIL_FROM=TU_CUENTA@gmail.com
ADMIN_MAIL_WORKER_ENABLED=true
```

Usar inicialmente la misma cuenta como usuario y remitente. No reemplazar ADMIN_ENCRYPTION_KEY ni ADMIN_JWT_SECRET. El remitente Gmail no obliga a permitir destinatarios gmail.com: ADMIN_ALLOWED_EMAIL_DOMAINS controla quién puede ser invitado, independientemente del proveedor de envío. Conservar lista restringida; si se necesita una cuenta Gmail de prueba, admitir gmail.com es una decisión separada sobre dominios, no parte automática de SMTP.

ADMIN_FRONTEND_URL debe ser la URL de la consola accesible al destinatario. localhost solo funciona si el enlace se abre en el mismo PC donde corre la consola. Desde teléfono/u otro PC debe usarse una URL accesible; en producción HTTPS. No confundir esta URL con la dirección de la API.

Fuente de servidor/STARTTLS: [documentación oficial Gmail](https://support.google.com/mail/answer/7104828?hl=es).

## 3. Aplicar y comprobar con Docker

Desde la carpeta del backend, cuando las variables estén completas:

```powershell
docker compose up -d --build api
docker compose exec api python -m scripts.check_mail
```

El primer comando incorpora el código actual y recarga variables recreando API si corresponde; no borra pgdata ni ejecuta seed. No hace falta borrar imágenes. El segundo conecta/autentica sin enviar mensajes y sin imprimir credenciales. No usar docker compose config para compartir diagnóstico, porque puede mostrar secretos resueltos.

## 4. Prueba de entrega

Resultado confirmado por el usuario el 10 de octubre de 2026: conexión SMTP correcta en Docker, correo recibido, invitación aceptada y cuenta nueva autenticada en consola. Configuración realizada localmente por el usuario sin compartir secretos. El enlace de prueba usa localhost:5173; no acredita acceso desde otros dispositivos ni despliegue público.

Crear desde consola una invitación a cuenta de prueba autorizada. Revisar estado de envío, bandeja de entrada/spam y enlace. sent significa aceptado por SMTP, no entrega final garantizada. Aceptar enlace, definir contraseña, configurar MFA obligatorio y comprobar login. Usar cuenta nueva o pendiente, no enviar invitación a la cuenta existente del administrador.

Si una invitación agotó reintentos antes de configurar Gmail, reenviarla desde consola (rota enlace). Una conexión correcta no acredita este flujo completo. La fase 2 sigue por validar hasta prueba real autorizada.
