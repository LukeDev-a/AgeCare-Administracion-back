// Bingo AgeCare — cartón de 4x4, números cantados en voz alta, sin presión de tiempo
// El adulto mayor controla el ritmo: solo se canta un número nuevo cuando él lo pide.

const RANGO_MAXIMO = 40;
const TAMANO_CARTON = 4;
const TOTAL_CASILLAS = TAMANO_CARTON * TAMANO_CARTON;

let carton = [];
let numerosCantados = new Set();
let numerosDisponibles = [];
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

function decirNumeroEnVozAlta(numero) {
  if (!("speechSynthesis" in window)) return;
  const mensaje = new SpeechSynthesisUtterance(String(numero));
  mensaje.lang = "es-ES";
  mensaje.rate = 0.9;
  window.speechSynthesis.speak(mensaje);
}

function mezclar(arreglo) {
  const copia = [...arreglo];
  for (let i = copia.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copia[i], copia[j]] = [copia[j], copia[i]];
  }
  return copia;
}

function generarCarton() {
  const numerosDisponiblesParaCarton = mezclar(
    Array.from({ length: RANGO_MAXIMO }, (_, i) => i + 1)
  );
  return numerosDisponiblesParaCarton.slice(0, TOTAL_CASILLAS).map((numero) => ({
    numero,
    marcada: false,
  }));
}

function iniciarJuego() {
  carton = generarCarton();
  numerosCantados = new Set();
  numerosDisponibles = Array.from({ length: RANGO_MAXIMO }, (_, i) => i + 1);
  document.getElementById("numero-cantado").textContent = "—";
  document.getElementById("celebracion").hidden = true;
  document.getElementById("btn-cantar").disabled = false;
  renderizarCarton();
}

function renderizarCarton() {
  const contenedor = document.getElementById("carton");
  contenedor.innerHTML = "";

  carton.forEach((casilla, indice) => {
    const boton = document.createElement("button");
    boton.className = "casilla" + (casilla.marcada ? " marcada" : "");
    boton.textContent = casilla.numero;
    boton.disabled = casilla.marcada;
    boton.setAttribute("aria-label", `Número ${casilla.numero}${casilla.marcada ? ", marcado" : ""}`);
    boton.addEventListener("click", () => marcarCasilla(indice));
    contenedor.appendChild(boton);
  });
}

function marcarCasilla(indice) {
  const casilla = carton[indice];
  if (casilla.marcada) return;
  if (!numerosCantados.has(casilla.numero)) return; // aún no se ha cantado ese número

  inicializarAudio();
  casilla.marcada = true;
  reproducirSonido(600, 150);
  renderizarCarton();

  const completo = carton.every((c) => c.marcada);
  if (completo) {
    setTimeout(() => {
      reproducirSonido(784, 300);
      document.getElementById("celebracion").hidden = false;
      document.getElementById("btn-cantar").disabled = true;
    }, 200);
  }
}

function cantarNumero() {
  if (numerosDisponibles.length === 0) return;

  inicializarAudio();
  const indiceAlAzar = Math.floor(Math.random() * numerosDisponibles.length);
  const numero = numerosDisponibles[indiceAlAzar];
  numerosDisponibles.splice(indiceAlAzar, 1);
  numerosCantados.add(numero);

  document.getElementById("numero-cantado").textContent = numero;
  decirNumeroEnVozAlta(numero);

  if (numerosDisponibles.length === 0) {
    document.getElementById("btn-cantar").disabled = true;
  }
}

document.getElementById("btn-cantar").addEventListener("click", cantarNumero);
document.getElementById("btn-reiniciar").addEventListener("click", iniciarJuego);

iniciarJuego();
