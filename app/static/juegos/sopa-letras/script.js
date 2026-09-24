// Sopa de letras AgeCare — tocar la primera y la última letra de una palabra
// (en la misma fila o columna) para intentar encontrarla. Sin penalización por error.

const TAMANO = 6;
const LETRAS_RELLENO = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

let grid = [];
let celdasEncontradas = new Set();
let primeraSeleccion = null;
let palabrasConjuntoActual = [];
let palabrasPendientes = [];
let audioContext = null;

function inicializarAudio() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
  }
}

function reproducirSonido(frecuencia, duracionMs) {
  if (!audioContext) return;
  const oscilador = audioContext.createOscillator();
  const ganancia = audioContext.createGain();
  oscilador.frequency.value = frecuencia;
  oscilador.type = "sine";
  ganancia.gain.setValueAtTime(0.13, audioContext.currentTime);
  ganancia.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + duracionMs / 1000);
  oscilador.connect(ganancia);
  ganancia.connect(audioContext.destination);
  oscilador.start();
  oscilador.stop(audioContext.currentTime + duracionMs / 1000);
}

function elegirConjuntoAlAzar() {
  const conjuntos = window.CONJUNTOS_SOPA || [];
  return conjuntos[Math.floor(Math.random() * conjuntos.length)];
}

function construirGrid(conjunto) {
  const nuevaGrid = Array.from({ length: TAMANO }, () => Array(TAMANO).fill(null));

  conjunto.palabras.forEach((item) => {
    item.celdas.forEach((coordenada, indice) => {
      const [fila, columna] = coordenada;
      nuevaGrid[fila][columna] = item.palabra[indice];
    });
  });

  for (let fila = 0; fila < TAMANO; fila++) {
    for (let columna = 0; columna < TAMANO; columna++) {
      if (!nuevaGrid[fila][columna]) {
        nuevaGrid[fila][columna] = LETRAS_RELLENO[Math.floor(Math.random() * LETRAS_RELLENO.length)];
      }
    }
  }

  return nuevaGrid;
}

function iniciarJuego() {
  const conjunto = elegirConjuntoAlAzar();
  palabrasConjuntoActual = conjunto.palabras;
  palabrasPendientes = [...palabrasConjuntoActual];
  grid = construirGrid(conjunto);
  celdasEncontradas = new Set();
  primeraSeleccion = null;

  document.getElementById("celebracion").hidden = true;
  renderizarGrid();
  renderizarListaPalabras();
}

function renderizarGrid() {
  const contenedor = document.getElementById("grilla");
  contenedor.innerHTML = "";

  for (let fila = 0; fila < TAMANO; fila++) {
    for (let columna = 0; columna < TAMANO; columna++) {
      const clave = `${fila}-${columna}`;
      const boton = document.createElement("button");
      boton.className = "celda";
      if (celdasEncontradas.has(clave)) boton.classList.add("encontrada");
      if (primeraSeleccion && primeraSeleccion.fila === fila && primeraSeleccion.columna === columna) {
        boton.classList.add("seleccionada");
      }
      boton.textContent = grid[fila][columna];
      boton.setAttribute("aria-label", `Letra ${grid[fila][columna]}`);
      boton.addEventListener("click", () => manejarToque(fila, columna));
      contenedor.appendChild(boton);
    }
  }
}

function renderizarListaPalabras() {
  const contenedor = document.getElementById("lista-palabras");
  contenedor.innerHTML = "";

  palabrasConjuntoActual.forEach((item) => {
    const etiqueta = document.createElement("span");
    const yaEncontrada = !palabrasPendientes.includes(item);
    etiqueta.className = "palabra-etiqueta" + (yaEncontrada ? " encontrada" : "");
    etiqueta.textContent = item.palabra;
    contenedor.appendChild(etiqueta);
  });
}

function obtenerCeldasEnLinea(inicio, fin) {
  if (inicio.fila === fin.fila) {
    const [desde, hasta] = [inicio.columna, fin.columna].sort((a, b) => a - b);
    const celdas = [];
    for (let columna = desde; columna <= hasta; columna++) {
      celdas.push({ fila: inicio.fila, columna });
    }
    return celdas;
  }
  if (inicio.columna === fin.columna) {
    const [desde, hasta] = [inicio.fila, fin.fila].sort((a, b) => a - b);
    const celdas = [];
    for (let fila = desde; fila <= hasta; fila++) {
      celdas.push({ fila, columna: inicio.columna });
    }
    return celdas;
  }
  return null; // no están en la misma fila ni columna
}

function manejarToque(fila, columna) {
  const clave = `${fila}-${columna}`;
  if (celdasEncontradas.has(clave)) return;

  inicializarAudio();

  if (primeraSeleccion === null) {
    primeraSeleccion = { fila, columna };
    renderizarGrid();
    return;
  }

  if (primeraSeleccion.fila === fila && primeraSeleccion.columna === columna) {
    primeraSeleccion = null;
    renderizarGrid();
    return;
  }

  const celdasEnLinea = obtenerCeldasEnLinea(primeraSeleccion, { fila, columna });
  primeraSeleccion = null;

  if (!celdasEnLinea) {
    renderizarGrid();
    return;
  }

  const textoDirecto = celdasEnLinea.map((c) => grid[c.fila][c.columna]).join("");
  const textoInverso = [...textoDirecto].reverse().join("");

  const palabraEncontrada = palabrasPendientes.find(
    (item) => item.palabra.length === celdasEnLinea.length && (item.palabra === textoDirecto || item.palabra === textoInverso)
  );

  if (palabraEncontrada) {
    celdasEnLinea.forEach((c) => celdasEncontradas.add(`${c.fila}-${c.columna}`));
    palabrasPendientes = palabrasPendientes.filter((item) => item !== palabraEncontrada);
    reproducirSonido(660, 180);
    renderizarGrid();
    renderizarListaPalabras();

    if (palabrasPendientes.length === 0) {
      setTimeout(() => {
        reproducirSonido(784, 250);
        document.getElementById("celebracion").hidden = false;
      }, 200);
    }
  } else {
    reproducirSonido(330, 150);
    marcarIntentoFallido(celdasEnLinea);
  }
}

function marcarIntentoFallido(celdas) {
  const botones = document.querySelectorAll(".celda");
  celdas.forEach((c) => {
    const indice = c.fila * TAMANO + c.columna;
    botones[indice].classList.add("incorrecta");
  });
  setTimeout(renderizarGrid, 500);
}

document.getElementById("btn-reiniciar").addEventListener("click", iniciarJuego);

iniciarJuego();
