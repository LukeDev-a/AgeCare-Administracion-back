// Ordenar secuencias AgeCare — ordenar los pasos de una actividad cotidiana
// Misma mecánica que el rompecabezas: tocar dos para intercambiar, sin arrastrar.

let secuenciaActual = null;
let tablero = []; // tablero[posicion] = índice del paso correcto que está ahí
let seleccionada = null;
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

function mezclar(arreglo) {
  const copia = [...arreglo];
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

function iniciarJuego() {
  const secuencias = window.SECUENCIAS || [];
  secuenciaActual = secuencias[Math.floor(Math.random() * secuencias.length)];

  const indicesOrdenados = secuenciaActual.pasos.map((_, i) => i);
  tablero = mezclar(indicesOrdenados);
  seleccionada = null;

  document.getElementById("nombre-secuencia").textContent = secuenciaActual.nombre;
  document.getElementById("celebracion").hidden = true;
  renderizarPasos();
}

function renderizarPasos() {
  const contenedor = document.getElementById("pasos");
  contenedor.innerHTML = "";

  tablero.forEach((indicePaso, posicion) => {
    const tarjeta = document.createElement("button");
    tarjeta.className = "paso-tarjeta";
    if (indicePaso === posicion) tarjeta.classList.add("correcta");
    if (seleccionada === posicion) tarjeta.classList.add("seleccionada");

    tarjeta.innerHTML = `
      <span class="paso-numero">${posicion + 1}</span>
      <span class="paso-texto">${secuenciaActual.pasos[indicePaso]}</span>
    `;
    tarjeta.addEventListener("click", () => manejarToque(posicion));
    contenedor.appendChild(tarjeta);
  });
}

function manejarToque(posicion) {
  inicializarAudio();

  if (seleccionada === null) {
    seleccionada = posicion;
    renderizarPasos();
    return;
  }

  if (seleccionada === posicion) {
    seleccionada = null;
    renderizarPasos();
    return;
  }

  [tablero[seleccionada], tablero[posicion]] = [tablero[posicion], tablero[seleccionada]];
  seleccionada = null;
  reproducirSonido(440, 120);
  renderizarPasos();

  if (estaResuelto(tablero)) {
    setTimeout(() => {
      reproducirSonido(784, 250);
      document.getElementById("celebracion").hidden = false;
    }, 200);
  }
}

document.getElementById("btn-reiniciar").addEventListener("click", iniciarJuego);

iniciarJuego();
