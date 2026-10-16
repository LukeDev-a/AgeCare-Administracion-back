# Cuentas iniciales para desarrollo

Para una instalación local nueva se pueden crear cuatro cuentas sin ejecutar `scripts.seed`. Este procedimiento solo añade cuentas si **admin_users está completamente vacía**; no carga datos de demostración del resto de módulos.

## Activar y arrancar

En el `.env` del backend (junto a `docker-compose.yml`), configurar:

```dotenv
ADMIN_ENVIRONMENT=dev
ADMIN_BOOTSTRAP_DEV_ACCOUNTS=true
```

Conservar una `ADMIN_ENCRYPTION_KEY` Fernet válida en ese entorno para configurar MFA. No regenerarla si ya existen datos cifrados. Esta guía no cambia la configuración SMTP ni la política de roles con MFA obligatorio.

Después de recibir estos cambios, desde la carpeta backend:

```powershell
docker compose up -d --build api
docker compose logs --tail=50 api
```

Compose ejecuta migraciones, `python -m scripts.bootstrap_dev_accounts` y después inicia la API. Si todo está preparado, el log informa que se crearon cuatro cuentas, sin imprimir contraseñas. Con el flag desactivado no crea cuentas. Fuera del entorno `dev` rechaza la carga si se intenta habilitarla.

## Acceso inicial

Estas son credenciales públicas de **desarrollo local**, solicitadas por el usuario. No habilitar este mecanismo ni utilizar estas cuentas en producción.

| Correo | Contraseña inicial | Rol interno |
|---|---|---|
| admin@wellq.co.uk | Admin123! | admin |
| soporte@wellq.co.uk | Soporte123! | support |
| analista@wellq.co.uk | Analista123! | analyst |
| editora@wellq.co.uk | Editora123! | editor |

Las contraseñas se guardan mediante Argon2, nunca como texto legible en la base. Las cuentas se crean activas, con `mfa_enabled=false`, sin secreto TOTP ni códigos de recuperación. Admin tiene `mfa_required=true`: al entrar con su contraseña debe configurar su propio autenticador y guardar los códigos de recuperación **antes de acceder a la consola**. Para los demás roles se respeta `ADMIN_MFA_REQUIRED_ROLES`: si los exige, también deben configurar MFA al entrar. No se desactiva MFA de cuentas existentes.

Una vez creada la instalación, puede desactivarse la carga:

```dotenv
ADMIN_BOOTSTRAP_DEV_ACCOUNTS=false
```

Aplicar el cambio con `docker compose up -d --force-recreate api`.

## Qué conserva

Si ya existe cualquier cuenta, el proceso no crea ninguna: no rellena roles faltantes, no restablece contraseñas, no cambia roles/estados, no elimina MFA y no vuelve a crear una cuenta borrada mientras existan otras. No es un mecanismo de recuperación de acceso. En PostgreSQL bloquea brevemente la tabla dentro de la transacción para serializar cargas simultáneas. No borra datos ni reinicia volúmenes, y no envía invitaciones.

Para comprobar sin mostrar datos sensibles:

```powershell
docker compose exec db psql -U agecare -d agecare_admin -c "SELECT email, role, is_active, mfa_enabled FROM admin_users;"
```

## Evidencia de validación

Suite completa backend del 15 de octubre de 2026: **94 pruebas aprobadas**, incluidas las tres pruebas nuevas de carga inicial, sobre SQLite aislado. Persisten advertencias previas de Pydantic y de la clave JWT de tests.

Las pruebas aisladas verifican cuentas y hashes, MFA pendiente con obligatoriedad del admin, repetición sin sobrescritura, conservación de una cuenta existente con MFA y rechazo fuera de dev. No ejecutar este script sobre la base personal del usuario solo para verificarlo. La ejecución Docker/PostgreSQL de la instalación del colega debe comprobarse por separado.
