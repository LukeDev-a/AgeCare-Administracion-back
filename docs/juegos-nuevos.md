# Diez juegos nuevos — entrega del 14 de octubre de 2026

Se añaden diez juegos HTML/CSS/JavaScript para personas mayores, conservando los diez originales. No requieren Gemini, conexión a proveedores ni cuentas para ejecutar sus archivos. El catálogo administrativo sigue utilizando los mismos endpoints y permisos: admin/editor modifica, los cinco roles internos consultan y `/games-apps/active` es público.

## Archivos y variedad

En `app/static/juegos`, cada carpeta nueva tiene `index.html`, `estilo.css`, `script.js` y `juego.json`:

| Carpeta | Juego y variación |
|---|---|
| domino | Dominó tranquilo: cadena inicial y seis fichas diferentes por ronda. Las manos generadas tienen solución; una elección del jugador puede dejarlo sin movimientos, con opción de empezar otra ronda. |
| lista-compras | Mi lista de compras: tres productos entre quince y cinco distractores. Consultar otra vez la lista conserva los aciertos. |
| palabras-silabas | Palabras por sílabas: banco de dieciocho palabras, sílabas mezcladas, deshacer y pistas. |
| cada-cosa | Cada cosa en su lugar: selección de categorías y objetos, clasificación por pulsaciones. |
| camino-casa | Camino a casa: laberinto nuevo de 4×4, inicio en una esquina aleatoria y casa en una casilla de distancia máxima. |
| continua-patron | Continúa el patrón: seis reglas y símbolos cambiantes con opciones y pista. |
| reloj | Pon el reloj en hora: veinticuatro objetivos en horas y medias horas; controles por botones y lectura digital. |
| cuenta-elige | Cuenta y elige: cantidades de tres a nueve, objetos variables y marcas opcionales para contar. |
| tres-raya | Tres en raya: rival local de movimientos aleatorios o dos personas; alterna quién comienza. No usa IA externa. |
| mi-paisaje | Mi paisaje: parque, playa o campo; colocar, reemplazar, borrar y deshacer objetos libremente. |

El núcleo `compartido/js/nuevos-core.js` centraliza barajado, mazos, dominó, comprobación de tres en raya y generación de laberintos. El laberinto usa búsqueda en profundidad aleatoria para formar un árbol conectado; una búsqueda por anchura elige la salida y permite dar pistas. No depende de un conjunto de tableros fijos. Los bancos finitos se recorren barajados y pueden repetirse después de agotarse; el azar no garantiza diseños únicos para siempre.

Todos reutilizan `compartido/css/accesibilidad.css` y la extensión `compartido/css/nuevos.css`: controles grandes, texto descriptivo, foco visible, avisos accesibles y adaptación a pantallas estrechas. No hay límite obligatorio de tiempo ni penalización por errores. Los emojis dependen de las fuentes del dispositivo; faltan pruebas visuales y de accesibilidad con usuarios/dispositivos reales. No se atribuyen resultados terapéuticos a estos juegos.

## Registro y prueba en la instalación

Actualización del 15 de octubre: 0006 retira del catálogo las tres URLs de imágenes, sort_order y accessibility, que no tenían consumo funcional. Se conserva target_url y el resto de los campos. Los recursos CSS y controles accesibles no se retiran. 0005 refleja la tabla y admite esquemas anteriores y nuevos. Validación posterior: 91 pruebas backend aprobadas (incluida migración SQLite con conservación de fichas y demás datos), y build frontend aprobado. No se ejecutó migración sobre la base real; PostgreSQL pendiente. Downgrade restaura estructura, no los valores retirados.

La migración Alembic `0005_new_games` depende de `0004`. Inserta solo los slugs ausentes, con estado **inactivo**, plan gratuito y rutas `/static/juegos/<slug>/index.html`. No sobrescribe fichas existentes. El downgrade conserva los datos deliberadamente para no eliminar fichas que hayan sido editadas o activadas.

Desde la carpeta backend, actualizar la API con el procedimiento habitual:

```powershell
docker compose up -d --build api
```

El arranque aplica las migraciones pendientes. Esta entrega no ejecutó esa actualización sobre la instalación ni modificó cuentas/datos reales. No usar seed ni eliminar volúmenes.

Abrir `http://localhost:8000/static/juegos/nuevos.html` para revisar los diez juegos. `nuevos.json` describe esta galería; no reemplaza la base de datos. La galería y los HTML son públicos aunque sus fichas estén inactivas. Para incorporarlos al catálogo activo, revisarlos y activarlos desde la consola con admin/editor.

El router `games_apps.py` convierte las URLs que empiezan con una sola `/` a URLs absolutas en sus respuestas, sin modificar el dato guardado. Usa `ADMIN_GAME_PUBLIC_BASE_URL` si se configura; de lo contrario, `request.base_url`. Mantiene intactas las URLs absolutas anteriores. En un proxy, configurar la base pública correcta y verificar que el teléfono pueda alcanzarla. La variable aparece en `.env.example`; el `.env` real no fue leído ni modificado.

## Validación realizada

Limpieza del 15 de octubre: 91 pruebas backend y 29 pruebas frontend aprobadas; build aprobado. Tras ajustar el tipo JSONB del downgrade, las tres pruebas de catálogo/migración se repitieron y aprobaron. Lint completo del frontend pendiente de corregir: 11 errores de set-state-in-effect y una advertencia de Fast Refresh en código existente; esta limpieza solo retira propiedades de tipos/formulario y no cambia efectos. No se amplió el alcance a esas correcciones.

- `node --test tests/new-games.test.cjs`: **9 pruebas aprobadas**. Comprueba 300 laberintos conectados/resolubles con variedad, 100 manos de dominó con solución, arranque/reinicio de los diez juegos, referencias locales y recorridos de interacción mediante un DOM simulado.
- Suite completa `pytest -q -p no:cacheprovider --tb=short`: **90 pruebas aprobadas**, incluyendo registro idempotente de las diez fichas y conversión de URLs. Usa los entornos aislados de prueba; no valida PostgreSQL de producción. Persisten advertencias previas de Pydantic y longitud de la clave JWT de pruebas.
- No hubo navegador disponible en esta sesión: **revisión visual, teclado/lector de pantalla y Android/iOS/WebView pendientes**. El DOM simulado no acredita renderizado, medidas táctiles reales ni funcionamiento en teléfonos.

No se incorporan puntuaciones, seguimiento personal, persistencia central de partidas, telemetría ni caché offline. Las interacciones dentro de los juegos no generan auditoría; las modificaciones administrativas de sus fichas conservan la auditoría existente. Para integrar, copiar toda la carpeta `juegos`, incluidos los recursos compartidos, y seguir el README de entrega del workspace.
