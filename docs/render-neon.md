# Render + Neon — demostración de AgeCare

30 de octubre de 2026. Usuario eligió el repositorio LukeDev-a/AgeCare-Administracion-back, rama local main, Render Virginia y Neon Virginia. Datos ya copiados y verificados en Neon. Todavía no se ha publicado el servicio ni se han hecho commits/pushes por el agente.

## Preparación realizada

- Dockerfile.render usa python -m scripts.run_render y el puerto PORT de Render. No modifica Dockerfile/Compose local, ni migra, ni ejecuta seed/bootstrap al iniciar.
- app/database_urls.py adapta la URL libpq de Neon a asyncpg, con SSLContext de CA del sistema, hostname y cadena verificados. Alembic y los motores de aplicación/preparación usan el mismo criterio TLS. Se escapa % en ConfigParser de Alembic para contraseñas URL-encoded. La conexión local sigue igual.
- python -m scripts.prepare_render prepara el rol SQL limitado usando la conexión propietaria local NEON_MIGRATION_DATABASE_URL. Guarda una sola vez la contraseña SQL estable, un JWT propio nuevo y la MISMA ADMIN_ENCRYPTION_KEY original en .env.render, ya excluido de Git y de Docker. El propietario nunca se pone en ese archivo de despliegue. No regenerar claves MFA ni solicitar sus valores en el chat.
- La preparación repetida autentica primero la credencial SQL existente y no la rota; no cambia JWT ni claves MFA. Las concesiones de negocio y SELECT/INSERT de auditoría se confirman en una transacción. La variante Compose sin stable_password conserva su comportamiento previo de contraseña aleatoria por inicio.
- run_render comprueba rol sin privilegios elevados/membresías/propiedad/DDL, permisos y trigger de auditoría, revisión Alembic y configuración pública antes de abrir HTTP. Falla cerrado sin imprimir entradas privadas ni SQL.

## Decisión explícita sobre contraseñas

El preparador detectó cuatro cuentas activas con contraseñas conocidas de desarrollo. Usuario indicó: «no quiero modificar las contraseñas de ninguna cuenta». No se cambiaron/desactivaron cuentas ni MFA. Se preparó la excepción explícita ADMIN_RENDER_ALLOW_DEV_CREDENTIALS=true con ADMIN_ENVIRONMENT=dev, únicamente para esta demostración. En staging/prod se rechaza esa excepción. Fuera de ella, run_render rechaza contraseñas públicas de desarrollo. No confundir esta autorización con una recomendación de producción ni con permiso para desactivar MFA.

Para conservar esa decisión al repetir la preparación local:

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_render --allow-dev-credentials
```

Ese comando necesita conexión directa propietaria local y permisos para preparar el rol; no forma parte del arranque Render ni se coloca en su Docker Command. El .env local no se modifica. No mostrar los secretos del archivo generado ni copiarlos a Vercel.

## Crear Web Service en Render

Primero subir a GitHub los cambios revisados del backend, incluidos todos los nuevos módulos que importa app.main y el Dockerfile.render. No se hicieron commits/pushes durante esta preparación.

| Campo | Valor |
|---|---|
| Repositorio | LukeDev-a/AgeCare-Administracion-back |
| Branch | main |
| Name | agecare-api, o nombre disponible |
| Region | Virginia |
| Language/Runtime | Docker |
| Root Directory | Vacío si el repositorio ya comienza con app/, scripts/, requirements.txt y Dockerfile.render |
| Dockerfile Path | ./Dockerfile.render |
| Docker Build Context | . |
| Docker Command | Vacío: usa el CMD del Dockerfile.render |
| Health Check Path | /health |

En Environment, usar Add from .env y pegar el contenido del archivo privado .env.render desde el editor local. No pegarlo en el chat ni subir el archivo a GitHub. Las comillas pertenecen al formato dotenv: usar el importador .env. Docker CLI --env-file tiene otra interpretación; la comprobación local usó dotenv y variables de entorno heredadas sin valores secretos en argumentos.

El archivo contiene una configuración de demostración con bootstrap/seed y workers de correo, Gemini y analítica apagados. End-users demo permanece explícitamente como demo, sin revocación móvil real. No se copiaron audios del volumen local.

Render provee RENDER_EXTERNAL_URL; si ADMIN_GAME_PUBLIC_BASE_URL está vacía, run_render usa esa raíz HTTPS para las direcciones de juegos. Al conocer el dominio definitivo también puede configurarse explícitamente esa variable. No incluir /static/juegos ni /api/v1/admin.

Mientras se publica Vercel, el perfil permite los orígenes locales 5173. Después establecer ADMIN_ALLOWS_ORIGINS con el origen Vercel exacto (sin / final), y ADMIN_FRONTEND_URL con la URL de la consola que implementa invitación/enrolamiento MFA. Actualizar VITE_API_BASE_URL en Vercel con raíz Render + /api/v1/admin y recompilar frontend. No autorizar null ni comodines globales.

## Plan gratuito y correo

Render Free suspende servicios inactivos, no dispone de disco persistente y bloquea salida SMTP por 25/465/587, incluido Gmail STARTTLS. El perfil deja correo apagado; no afirmar que invitaciones se enviarán desde Free. Para mantener Gmail se requiere un servicio que permita ese tráfico; alternativamente integrar un proveedor por HTTPS en trabajo posterior autorizado. La generación de audios necesita almacenamiento persistente antes de habilitarse. Los juegos incluidos en la imagen no requieren subirlos a un disco de datos.

## Validación y límites

- Suite backend completa: 376 pruebas aprobadas antes del último ajuste de excepción demo; 26 seleccionadas de Render/auth/bloqueo aprobadas después. Warnings existentes por JWT corto únicamente en fixtures de tests.
- Preparador ejecutado dos veces sobre Neon: credencial estable autenticada sin rotar, esquema al día, rol limitado y auditoría SELECT/INSERT confirmados; ninguna cuenta ni dato de negocio modificado.
- Imagen Docker construida. Contenedor temporal sin puertos publicados: arranque con Neon y PORT=10000, /health correcto, 11 juegos activos, URLs locales reescritas a HTTPS y HEAD con Origin null devuelve200/ACAO:* para iframe. Confirmada ausencia de .env, .env.render y backups/ en la imagen. Contenedor de prueba detenido y eliminado automáticamente, API local no reiniciada. Esto no acredita acceso público ni CORS contra un dominio Vercel real.
- Quedan publicación GitHub/Render/Vercel, comprobación de login/MFA en el dominio real, política de confianza de proxies para IP de auditoría y decisión de correo/almacenamiento según plan. No habilitar confianza de proxy universal para inventar una IP de cliente.

## Referencias

- https://render.com/docs/docker
- https://render.com/docs/environment-variables
- https://render.com/docs/free
- https://neon.com/docs/manage/database-access
