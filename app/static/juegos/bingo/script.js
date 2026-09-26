// Bingo AgeCare — cartón de 4x4, números cantados en voz alta
const RANGO_MAXIMO = 40;
const TAMANO_CARTON = 4;
const TOTAL_CASILLAS = TAMANO_CARTON * TAMANO_CARTON;

let carton = [];
let numerosCantados = new Set();
let numerosDisponibles = [];
let audioContext = null;
let catalogoVoces = [];

function cargarVoces() {
  if ("speechSynthesis" in window) {
    catalogoVoces = window.speechSynthesis.getVoices();
  }
}

cargarVoces();
if ("speechSynthesis" in window) {
  window.speechSynthesis.onvoiceschanged = cargarVoces;
}

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

function obtenerVoz(esIngles) {
  if (catalogoVoces.length === 0) {
    cargarVoces();
  }

  if (esIngles) {
    // 1. Buscar voz nativa en inglés (Chrome Google US, Microsoft Zira/David, Apple Samantha)
    return catalogoVoces.find((v) => 
      (v.lang === "en-US" || v.lang === "en-GB") && 
      (v.name.includes("Google") || v.name.includes("Natural") || v.name.includes("Microsoft") || v.name.includes("Samantha"))
    ) || catalogoVoces.find((v) => v.lang.startsWith("en"));
  } else {
    // 2. Buscar voz nativa en español
    return catalogoVoces.find((v) => 
      v.lang.startsWith("es") && 
      (v.name.includes("Google") || v.name.includes("Natural") || v.name.includes("Microsoft"))
    ) || catalogoVoces.find((v) => v.lang.startsWith("es"));
  }
}

function decirNumeroEnVozAlta(numero) {
  if (!("speechSynthesis" in window)) return;

  window.speechSynthesis.cancel();

  const selectEl = document.getElementById("select-idioma");
  const esIngles = selectEl ? selectEl.value === "en" : false;

  // Intl.NumberFormat convierte automáticamente el número a su palabra en inglés (ej: 2 -> "two")
  let textoParaLeer = String(numero);
  if (esIngles) {
    try {
      const formateador = new Intl.NumberFormat("en-US", { numberingSystem: "latn" });
      // Si el motor soporta conversión cardinal:
      const generadorPalabras = new Intl.DisplayNames(["en"], { type: "language" });
    } catch (e) {}
  }

  // Traducción fonética automática con Intl o sustitución léxica directa
  if (esIngles) {
    // Convierte el número (ej: 25 -> "twenty five") utilizando el conversor nativo de palabras
    const unidades = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", 
                      "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];
    const decenas = ["", "", "twenty", "thirty", "forty"];
    
    if (numero < 20) {
      textoParaLeer = unidades[numero];
    } else {
      const d = Math.floor(numero / 10);
      const u = numero % 10;
      textoParaLeer = u === 0 ? decenas[d] : `${decenas[d]} ${unidades[u]}`;
    }
  }

  const mensaje = new SpeechSynthesisUtterance(textoParaLeer);
  mensaje.lang = esIngles ? "en-US" : "es-ES";
  mensaje.rate = 0.85;

  const voz = obtenerVoz(esIngles);
  if (voz) {
    mensaje.voice = voz;
  }

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
  if (!numerosCantados.has(casilla.numero)) return;

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