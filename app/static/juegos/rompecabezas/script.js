// Rompecabezas AgeCare — mecánica de "tocar dos piezas para intercambiar"
// Pensado para adultos mayores: sin arrastrar, sin límite de tiempo, sin posibilidad de "perder".

const TAMANO = 3; // tablero de 3x3 = 9 piezas
const TOTAL_PIEZAS = TAMANO * TAMANO;
const PIXELES_POR_PIEZA = 110;

// Imagen de la escena, dibujada como SVG embebido (no depende de internet)
const escenaSVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 330 330">
  <rect width="330" height="330" fill="#B5D4F4"/>
  <circle cx="270" cy="60" r="34" fill="#FAC775"/>
  <rect x="0" y="230" width="330" height="100" fill="#97C459"/>
  <rect x="70" y="150" width="120" height="90" fill="#D4C0A1"/>
  <polygon points="60,150 130,90 200,150" fill="#993C1D"/>
  <rect x="110" y="190" width="30" height="50" fill="#5F5E5A"/>
  <rect x="150" y="170" width="25" height="25" fill="#E6F1FB"/>
  <rect x="240" y="180" width="14" height="60" fill="#5F5E5A"/>
  <circle cx="247" cy="160" r="32" fill="#3B6D11"/>
</svg>`;

const urlImagen = `url("data:image/svg+xml,${encodeURIComponent(escenaSVG)}")`;

let tablero = []; // tablero[posicion] = idPiezaCorrecta
let seleccionada = null; // índice de la primera pieza tocada
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
  ganancia.gain.setValueAtTime(0.15, audioContext.currentTime);
  ganancia.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + duracionMs / 1000);
  oscilador.connect(ganancia);
  ganancia.connect(audioContext.destination);
  oscilador.start();
  oscilador.stop(audioContext.currentTime + duracionMs / 1000);
}

function mezclar(arreglo) {
  const copia = [...arreglo];
  // Mezcla simple, repite si por casualidad queda ya resuelto
  do {
    for (let i = copia.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [copia[i], copia[j]] = [copia[j], copia[i]];
    }
  } while (estaResuelto(copia));
  return copia;
}

function estaResuelto(arreglo) {
  return arreglo.every((valor, indice) => valor === indice);
}

function crearTablero() {
  const idsOrdenados = Array.from({ length: TOTAL_PIEZAS }, (_, i) => i);
  tablero = mezclar(idsOrdenados);
  seleccionada = null;
  document.getElementById("celebracion").hidden = true;
  renderizarTablero();
}

function renderizarTablero() {
  const contenedor = document.getElementById("tablero");
  contenedor.innerHTML = "";

  tablero.forEach((idPieza, posicion) => {
    const fila = Math.floor(idPieza / TAMANO);
    const columna = idPieza % TAMANO;

    const boton = document.createElement("button");
    boton.className = "pieza";
    boton.setAttribute("aria-label", `Pieza en posición ${posicion + 1}`);
    boton.style.backgroundImage = urlImagen;
    boton.style.backgroundPosition = `-${columna * PIXELES_POR_PIEZA}px -${fila * PIXELES_POR_PIEZA}px`;

    if (idPieza === posicion) {
      boton.classList.add("correcta");
    }
    if (seleccionada === posicion) {
      boton.classList.add("seleccionada");
    }

    boton.addEventListener("click", () => manejarToque(posicion));
    contenedor.appendChild(boton);
  });
}

function manejarToque(posicion) {
  inicializarAudio();

  if (seleccionada === null) {
    seleccionada = posicion;
    renderizarTablero();
    return;
  }

  if (seleccionada === posicion) {
    // Tocar la misma pieza dos veces la deselecciona
    seleccionada = null;
    renderizarTablero();
    return;
  }

  // Intercambiar las dos piezas seleccionadas
  [tablero[seleccionada], tablero[posicion]] = [tablero[posicion], tablero[seleccionada]];
  seleccionada = null;
  reproducirSonido(440, 120);
  renderizarTablero();

  if (estaResuelto(tablero)) {
    setTimeout(() => {
      reproducirSonido(660, 200);
      document.getElementById("celebracion").hidden = false;
    }, 200);
  }
}

document.getElementById("btn-reiniciar").addEventListener("click", crearTablero);

crearTablero();
