// Trivia nostálgica AgeCare — preguntas de opción múltiple, sin cronómetro ni puntaje punitivo
// Cada partida elige 5 preguntas al azar del banco, y mezcla el orden de las opciones.

const CANTIDAD_PREGUNTAS_POR_RONDA = 5;

let ronda = [];
let indiceActual = 0;
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
  for (let i = copia.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copia[i], copia[j]] = [copia[j], copia[i]];
  }
  return copia;
}

function prepararRonda() {
  const bancoMezclado = mezclar(window.BANCO_PREGUNTAS || []);
  ronda = bancoMezclado.slice(0, CANTIDAD_PREGUNTAS_POR_RONDA).map((item) => {
    const opcionesConMarca = item.opciones.map((texto, indice) => ({
      texto,
      esCorrecta: indice === item.correcta,
    }));
    return {
      pregunta: item.pregunta,
      opciones: mezclar(opcionesConMarca),
    };
  });

  indiceActual = 0;
  document.getElementById("numero-total").textContent = ronda.length;
  document.getElementById("celebracion").hidden = true;
  mostrarPregunta();
}

function mostrarPregunta() {
  document.getElementById("siguiente-contenedor").hidden = true;
  document.getElementById("numero-actual").textContent = indiceActual + 1;

  const actual = ronda[indiceActual];
  document.getElementById("texto-pregunta").textContent = actual.pregunta;

  const contenedor = document.getElementById("opciones");
  contenedor.innerHTML = "";

  actual.opciones.forEach((opcion) => {
    const boton = document.createElement("button");
    boton.className = "opcion-boton";
    boton.textContent = opcion.texto;
    boton.addEventListener("click", () => responder(opcion, boton));
    contenedor.appendChild(boton);
  });
}

function responder(opcionElegida, botonElegido) {
  inicializarAudio();

  const actual = ronda[indiceActual];
  const botones = document.querySelectorAll(".opcion-boton");

  botones.forEach((boton, indice) => {
    boton.disabled = true;
    if (actual.opciones[indice].esCorrecta) {
      boton.classList.add("correcta");
    }
  });

  if (opcionElegida.esCorrecta) {
    reproducirSonido(660, 180);
  } else {
    botonElegido.classList.add("incorrecta");
    reproducirSonido(330, 150);
  }

  document.getElementById("siguiente-contenedor").hidden = false;
}

function irASiguientePregunta() {
  indiceActual += 1;
  if (indiceActual < ronda.length) {
    mostrarPregunta();
  } else {
    document.getElementById("siguiente-contenedor").hidden = true;
    reproducirSonido(784, 250);
    document.getElementById("celebracion").hidden = false;
  }
}

document.getElementById("btn-siguiente").addEventListener("click", irASiguientePregunta);
document.getElementById("btn-reiniciar").addEventListener("click", prepararRonda);

prepararRonda();
