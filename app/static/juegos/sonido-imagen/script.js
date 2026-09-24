// Emparejar sonido-imagen AgeCare — escuchar un sonido y tocar la imagen correcta
// Sin cronómetro, se puede volver a escuchar el sonido las veces que quiera.

const RONDAS_POR_PARTIDA = 5;
const OPCIONES_POR_RONDA = 3;

let ronda = [];
let indiceActual = 0;
let objetivoActual = null;
let audioContext = null;

function obtenerAudioContext() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
  }
  return audioContext;
}

function tono(frecuencia, inicioSeg, duracionSeg, tipoOnda = "sine", volumen = 0.15) {
  const ctx = obtenerAudioContext();
  const oscilador = ctx.createOscillator();
  const ganancia = ctx.createGain();
  oscilador.type = tipoOnda;
  oscilador.frequency.value = frecuencia;
  const inicio = ctx.currentTime + inicioSeg;
  ganancia.gain.setValueAtTime(volumen, inicio);
  ganancia.gain.exponentialRampToValueAtTime(0.001, inicio + duracionSeg);
  oscilador.connect(ganancia);
  ganancia.connect(ctx.destination);
  oscilador.start(inicio);
  oscilador.stop(inicio + duracionSeg);
}

function ruidoBlanco(inicioSeg, duracionSeg, volumen = 0.08) {
  const ctx = obtenerAudioContext();
  const tamano = ctx.sampleRate * duracionSeg;
  const buffer = ctx.createBuffer(1, tamano, ctx.sampleRate);
  const datos = buffer.getChannelData(0);
  for (let i = 0; i < tamano; i++) {
    datos[i] = (Math.random() * 2 - 1) * volumen;
  }
  const fuente = ctx.createBufferSource();
  fuente.buffer = buffer;
  fuente.connect(ctx.destination);
  fuente.start(ctx.currentTime + inicioSeg);
}

// Cada función dibuja un patrón de sonido distinto para que sean fáciles de diferenciar.
const REPRODUCTORES = {
  campana: () => tono(880, 0, 1.2, "triangle", 0.18),
  reloj: () => {
    tono(700, 0, 0.15, "square", 0.1);
    tono(500, 0.4, 0.15, "square", 0.1);
  },
  tambor: () => {
    tono(110, 0, 0.2, "square", 0.2);
    tono(110, 0.3, 0.2, "square", 0.2);
  },
  pajaro: () => {
    tono(1400, 0, 0.1, "sine", 0.15);
    tono(1600, 0.15, 0.1, "sine", 0.15);
    tono(1500, 0.3, 0.1, "sine", 0.15);
  },
  telefono: () => {
    tono(950, 0, 0.35, "sine", 0.15);
    tono(1400, 0, 0.35, "sine", 0.1);
    tono(950, 0.55, 0.35, "sine", 0.15);
    tono(1400, 0.55, 0.35, "sine", 0.1);
  },
  lluvia: () => ruidoBlanco(0, 1.5, 0.06),
};

function reproducirSonidoDeObjetivo(id) {
  const reproductor = REPRODUCTORES[id];
  if (reproductor) reproductor();
}

function reproducirEfecto(frecuencia, duracionMs) {
  tono(frecuencia, 0, duracionMs / 1000, "sine", 0.13);
}

function mezclar(arreglo) {
  const copia = [...arreglo];
  for (let i = copia.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copia[i], copia[j]] = [copia[j], copia[i]];
  }
  return copia;
}

function prepararRonda() {
  const banco = mezclar(window.BANCO_SONIDOS || []);
  ronda = banco.slice(0, RONDAS_POR_PARTIDA);
  indiceActual = 0;
  document.getElementById("numero-total").textContent = ronda.length;
  document.getElementById("celebracion").hidden = true;
  mostrarRonda();
}

function mostrarRonda() {
  document.getElementById("siguiente-contenedor").hidden = true;
  document.getElementById("numero-actual").textContent = indiceActual + 1;

  objetivoActual = ronda[indiceActual];

  const resto = (window.BANCO_SONIDOS || []).filter((item) => item.id !== objetivoActual.id);
  const distractores = mezclar(resto).slice(0, OPCIONES_POR_RONDA - 1);
  const opciones = mezclar([objetivoActual, ...distractores]);

  const contenedor = document.getElementById("opciones");
  contenedor.innerHTML = "";

  opciones.forEach((item) => {
    const boton = document.createElement("button");
    boton.className = "opcion-imagen";
    boton.innerHTML = `<svg viewBox="0 0 100 100" aria-hidden="true">${item.svg}</svg><span>${item.nombre}</span>`;
    boton.addEventListener("click", () => elegirOpcion(item, boton));
    contenedor.appendChild(boton);
  });

  // Reproduce el sonido automáticamente al mostrar la ronda
  setTimeout(() => reproducirSonidoDeObjetivo(objetivoActual.id), 300);
}

function elegirOpcion(itemElegido, botonElegido) {
  if (itemElegido.id === objetivoActual.id) {
    botonElegido.classList.add("correcta");
    reproducirEfecto(660, 180);
    document.getElementById("siguiente-contenedor").hidden = false;
    document.querySelectorAll(".opcion-imagen").forEach((boton) => (boton.disabled = true));
  } else {
    botonElegido.classList.add("incorrecta");
    reproducirEfecto(330, 150);
    setTimeout(() => botonElegido.classList.remove("incorrecta"), 500);
  }
}

function irASiguienteRonda() {
  indiceActual += 1;
  if (indiceActual < ronda.length) {
    mostrarRonda();
  } else {
    reproducirEfecto(784, 250);
    document.getElementById("celebracion").hidden = false;
  }
}

document.getElementById("btn-escuchar").addEventListener("click", () => {
  if (objetivoActual) reproducirSonidoDeObjetivo(objetivoActual.id);
});
document.getElementById("btn-siguiente").addEventListener("click", irASiguienteRonda);
document.getElementById("btn-reiniciar").addEventListener("click", prepararRonda);

prepararRonda();
