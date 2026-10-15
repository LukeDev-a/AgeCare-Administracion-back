# Backend — guía para agentes

Lee [docs/CONTEXTO-TECNICO.md](docs/CONTEXTO-TECNICO.md) y [docs/invitaciones-mfa.md](docs/invitaciones-mfa.md). Si tienes el workspace completo, lee también el `AGENTS.md` de su raíz.

## Reglas de implementación

- Mantén routers, schemas, modelos y dependencias de seguridad en sus capas existentes.
- Usa `CurrentAdmin` para autenticación y `require(modulo, write=True)` para modificaciones protegidas. Consulta la matriz `READ`/`WRITE` de `app/enums.py`.
- La dependencia `get_db` hace commit al éxito y rollback ante excepciones. Un commit explícito, como el de intentos fallidos de MFA, debe ser deliberado.
- Añade migraciones Alembic para cambios de esquema. No alteres una base real ni ejecutes el seed como parte de una revisión.
- No regeneres claves de cifrado ni reveles tokens, QR, secretos MFA, contraseñas, códigos de recuperación o payloads SMTP.
- Conserva las comprobaciones de cuenta propia, último admin activo y bloqueo de registros en cambios de cuentas.
- Errores de verificación adicional no deben usar 401 para una sesión válida. La gestión MFA usa 422/423; 401 es para autenticación no válida y 403 para falta de permiso.
- Integra mutaciones de negocio con `app/audit.py`, con campos sensibles protegidos. No restaures captura de clics ni eventos HTTP genéricos.

## Verificación

Para contenido de fase 10 lee [contenido-editorial.md](docs/contenido-editorial.md). Worker apagado por defecto; no habilitar ni consumir Gemini real como efecto lateral de pruebas. Migración 0004 y volumen content_audio conservan datos; no sustituir modelos elegidos ni afirmar gratuidad sin proyecto gratuito. Feed de referencia protegido no debe abrir credenciales admin a pacientes.

Desde esta carpeta, en PowerShell y con dependencias disponibles:

```powershell
$env:ADMIN_ALLOWS_ORIGINS='http://localhost:3000'
$env:PYTHONDONTWRITEBYTECODE='1'
.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short
```

Los tests usan SQLite en memoria y configuración de prueba. No prueban automáticamente migraciones ni concurrencia sobre PostgreSQL de producción. No uses las claves de prueba fuera de los tests.

No es necesario levantar Docker para ejecutar esas pruebas. Para cambios de seguridad prueba permisos, invalidez de tokens, expiración y operaciones rechazadas, además del caso exitoso.
