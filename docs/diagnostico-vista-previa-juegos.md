# Corrección del aviso de conexión en vista previa

Diagnóstico del 28 de octubre de 2026 y corrección posterior autorizada por el usuario para integrar en el repositorio del equipo de backend. **Corrección implementada y comprobada jugando dentro del iframe.** No requiere crear ni compartir un token. El diagnóstico original siguiente describe el comportamiento anterior al arreglo.

## Evidencia

Tras el arranque realizado por el usuario, GET /health respondió correctamente. Memorama activo se abrió desde `/static/juegos/memorama/index.html` de localhost:8000. Una página de prueba temporal, sin credenciales ni acceso a base de datos, incrustó **ese juego real de la API** con el mismo sandbox de GamesPreviewPanel: `allow-scripts allow-forms allow-popups`. Al interactuar, el iframe navegó a `/static/juegos/compartido/no-disponible.html` con el texto «Si perdiste la conexión…». La apertura directa fuera del iframe mostró el juego normalmente. Antes se reprodujo también el mecanismo con un recurso de prueba activo.

Comprobación HTTP HEAD de la misma URL pública:

| Cabecera Origin | Estado | Access-Control-Allow-Origin |
|---|---|---|
| null | 200 | Ausente |
| http://localhost:5173 | 200 | http://localhost:5173 |

No se usaron tokens, credenciales, nuevos logins ni alteraciones de juegos/catálogos para diagnosticarlo. Las cabeceras se consultaron sin Authorization. No es una prueba de todos los juegos externos ni de una WebView móvil.

## Causa

El sandbox sin allow-same-origin asigna un origen opaco al documento incrustado. `disponibilidad.js` hace fetch HEAD con modo CORS normal cada cinco segundos y al recuperar foco. La solicitud del iframe tiene Origin null, que no está autorizado por la política CORS actual. Aunque la API devuelve 200 para el juego activo, el navegador no entrega esa respuesta al script. El catch de check() llama a stop(), que interpreta el bloqueo como fallo de disponibilidad/conexión y redirige al aviso genérico.

Fuentes locales: `src/pages/juegos/GamesPreviewPanel.tsx` del frontend, `app/static/juegos/compartido/disponibilidad.js`, `app/game_static.py` y CORS de `app/main.py` del backend. El endpoint estático valida juego activo/recurso local; no pide JWT. Generar un token no resuelve el origen opaco del iframe.

## Corrección implementada

Se conserva el aislamiento del iframe y la validación de juego activo. `app/game_static.py` añade Access-Control-Allow-Origin: * únicamente a respuestas HEAD de recursos locales de juego protegidos, incluidos los rechazos403. No añade esa autorización al GET ni a los endpoints administrativos. `app/static/juegos/compartido/disponibilidad.js` consulta con credentials: omit, sin cookies/tokens; permite leer el estado público desde el origen opaco del iframe. Cache-Control sigue no-store. No se cambia la política CORS global, no se añade allow-same-origin y no se usa no-cors; se mantiene la distinción entre200 y403.

## Qué integrar

Desde la raíz del backend, incorporar juntos:

1. [app/game_static.py](../app/game_static.py): cabeceras de las comprobaciones públicas HEAD, tanto activas como bloqueadas. Preservar el montaje GameStaticFiles de main.py y la consulta existente de activo/no eliminado/recurso local.
2. [app/static/juegos/compartido/disponibilidad.js](../app/static/juegos/compartido/disponibilidad.js): comprobación sin credenciales. No sustituirla por un fetch opaco que deje de verificar estado.
3. Regresión de [tests/test_game_availability.py](../tests/test_game_availability.py). La comprobación Node del script está en tests/games-management.test.cjs del frontend, sin cambios del componente React ni del sandbox.

No hay nueva ruta, modelo, migración ni variable de entorno para este arreglo. No es necesario copiar cambios de fases ajenas para incorporar estas líneas. No conceder Origin null global a la API ni retirar el sandbox del frontend como alternativa.

Después de integrar, reconstruir el servicio que sirve los juegos. En este proyecto, desde la carpeta de docker-compose.yml:

```powershell
docker compose up -d --build api
```

Recargar la consola y volver a seleccionar el juego para que el iframe cargue el script actualizado. No cambiar claves MFA/JWT ni borrar volúmenes. Durante la corrección no se reconstruyó ni reinició la API habitual: la comprobación de navegador se hizo con el código corregido en una API temporal aislada.

## Validación del arreglo

- 32 pruebas backend seleccionadas aprobadas: disponibilidad, juegos nuevos y auditoría. Caso nuevo Origin null: HEAD403 de inactivo, HEAD200 de activo, HEAD403 tras desactivar/eliminar, cabecera pública y no-store; GET del juego y consultas administrativas no ganan CORS para ese origen; cuenta sin autenticación sigue401.
- 6 pruebas Node de gestión/permisos aprobadas, incluida comprobación credentials omit y distinción activo/inactivo/fallo de red sin modo no-cors.
- Navegador real sobre API temporal con SQLite en memoria, sin leer .env ni usar credenciales/datos reales: Memorama dentro del sandbox original, clic revela carta y partida permanece abierta durante comprobaciones periódicas. Tras desactivar únicamente el juego de esa base de prueba, el mismo iframe abandona la partida y muestra el aviso de indisponibilidad. No se amplió el aislamiento ni se alteraron juegos del catálogo habitual.
- Sin validación adicional de WebView móvil/juegos externos ni reconstrucción de la instalación habitual. Los externos conservan sus límites de desactivación por catálogo.
