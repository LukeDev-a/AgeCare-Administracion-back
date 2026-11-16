# Datos para probar moderación

El usuario autorizó el15 de noviembre de2026 cargar ejemplos en local y Neon, primero local. Se añadieron60 registros exclusivamente a moderation_queue. Los dos registros anteriores se conservaron. Verificación final de solo lectura en ambos destinos:36 pendientes,13 aprobados y13 rechazados; cero ejemplos faltantes.

## Casos disponibles

-36 pendientes:15 reseñas,15 perfiles de cuidadoras,3 fotos y3 mensajes. Permiten probar paginación de25 y filtros por tipo.
-12 aprobados y12 rechazados adicionales para consultar historial, responsable mostrado, fecha y los cinco motivos de rechazo.
-Prioridad de seguridad y distintas fechas de recepción para comprobar el orden.
-Textos y personas ficticias. Ningún autor es una cuenta móvil canónica; author_user_id y decided_by son null. Los nombres y fechas de decisiones históricas son ejemplos, no evidencia de decisiones reales ni actividad de un administrador.
-Fotos/mensajes sin contenido privado ni archivos asociados. Su lectura temporal sigue pendiente y las decisiones permanecen bloqueadas.

Los ejemplos se muestran con los textos habituales de la consola, conforme la preferencia del usuario; su carácter ficticio se documenta aquí. Aprobar/rechazar desde la consola sí crea el evento normal de auditoría. No se envían correos ni se modifican reseñas o perfiles en sistemas externos.

## Carga segura y explícita

Script `scripts.seed_moderation_demo`, desde la raíz del backend y usando el entorno Python del proyecto:

```powershell
# Solo consulta totales y faltantes; no cambia datos.
.\venv\Scripts\python.exe -m scripts.seed_moderation_demo --target local

# Añade únicamente los ejemplos faltantes, cuando el usuario autorice una carga.
.\venv\Scripts\python.exe -m scripts.seed_moderation_demo --target local --apply

# Neon: usa la conexión limitada del perfil privado existente, sin mostrarla.
.\venv\Scripts\python.exe -m scripts.seed_moderation_demo --target neon
.\venv\Scripts\python.exe -m scripts.seed_moderation_demo --target neon --apply
```

Requiere entorno dev y, para Neon, host neon.tech/usuario limitado agecare_api_. No usa el seed general, no se ejecuta al arrancar, no crea tablas ni cambia cuentas o credenciales. IDs UUID5 estables con prefijo interno agecare-moderation-practice-v1: repetir la carga no duplica ni restablece decisiones, notas o fechas. No tiene opción de borrado/restablecimiento.

## Comprobación en consola

Entrar como admin o moderator. Abrir Moderación, revisar Pendientes y la segunda página; filtrar Reseñas/Perfiles/Fotos/Mensajes. Revisar un texto y confirmar aprobación o rechazo; Otro motivo exige nota. Consultar la decisión en Aprobados/Rechazados y su auditoría. El histórico precargado no sustituye esta ejecución manual ni sus capturas.

Para ver los datos basta actualizar la cola, también en Vercel: ya se cargaron en Neon y no dependen de push. Para ver la interfaz renovada públicamente el usuario debe subir el frontend. Sin migración ni reinicio de API.

## Validación técnica

159 pruebas frontend completas y17 backend dirigidas (contrato/moderación y carga aditiva) aprobadas. La prueba de carga usa transacción SQLite en memoria con rollback para no contaminar otras pruebas; conserva una decisión cambiada al volver a cargar. Build/lint aprobados. Navegador aislado con API ficticia revisó cola/detalle, aprobación/rechazo, errores, notas preservadas, privacidad, histórico, temas y ancho390. Evidencias en outputs/moderacion-ui-review. No se tomaron decisiones reales sobre los62 registros en ninguno de los destinos.
