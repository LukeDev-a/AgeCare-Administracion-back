// Memorama AgeCare — encontrar parejas de cartas iguales
// Sin cronómetro, un solo gesto (tocar), símbolos grandes y simples.

let temaActual = null;
let cartas = [];
let primeraSeleccion = null;
let segundaSeleccion = null;
let bloqueado = false;
let paresEncontrados = 0;
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

function crearSvgCarta(pareja) {
  return `<svg viewBox="0 0 100 100" aria-hidden="true">${pareja.svg}</svg>`;
}

function elegirTemaAlAzar() {
  const temas = window.TEMAS_MEMORAMA || [];
  return temas[Math.floor(Math.random() * temas.length)];
}

function mezclar(arreglo) {
  const copia = [...arreglo];
  for (let i = copia.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copia[i], copia[j]] = [copia[j], copia[i]];
  }
  return copia;
}

function crearTablero() {
  temaActual = elegirTemaAlAzar();
  const mazo = mezclar([...temaActual.pares, ...temaActual.pares]);
  cartas = mazo.map((pareja, indice) => ({
    indice,
    pareja,
    volteada: false,
    encontrada: false,
  }));
  primeraSeleccion = null;
  segundaSeleccion = null;
  bloqueado = false;
  paresEncontrados = 0;
  document.getElementById("celebracion").hidden = true;
  renderizarTablero();
}

function renderizarTablero() {
  const contenedor = document.getElementById("tablero");
  contenedor.innerHTML = "";

  cartas.forEach((carta) => {
    const boton = document.createElement("button");
    boton.className = "carta " + (carta.encontrada ? "encontrada" : carta.volteada ? "volteada" : "tapada");
    boton.setAttribute("aria-label", carta.volteada || carta.encontrada ? carta.pareja.id : "Carta tapada");
    boton.disabled = carta.encontrada;

    if (carta.volteada || carta.encontrada) {
      boton.innerHTML = crearSvgCarta(carta.pareja);
    }

    boton.addEventListener("click", () => manejarToque(carta.indice));
    contenedor.appendChild(boton);
  });
}

function manejarToque(indice) {
  if (bloqueado) return;
  const carta = cartas[indice];
  if (carta.volteada || carta.encontrada) return;

  inicializarAudio();
  reproducirSonido(500, 100);
  carta.volteada = true;

  if (primeraSeleccion === null) {
    primeraSeleccion = indice;
    renderizarTablero();
    return;
  }

  segundaSeleccion = indice;
  bloqueado = true;
  renderizarTablero();

  const primera = cartas[primeraSeleccion];
  const segunda = cartas[segundaSeleccion];

  if (primera.pareja.id === segunda.pareja.id) {
    setTimeout(() => {
      primera.encontrada = true;
      segunda.encontrada = true;
      paresEncontrados += 1;
      reproducirSonido(660, 180);
      primeraSeleccion = null;
      segundaSeleccion = null;
      bloqueado = false;
      renderizarTablero();

      if (paresEncontrados === temaActual.pares.length) {
        setTimeout(() => {
          reproducirSonido(784, 250);
          document.getElementById("celebracion").hidden = false;
        }, 200);
      }
    }, 600);
  } else {
    setTimeout(() => {
      primera.volteada = false;
      segunda.volteada = false;
      primeraSeleccion = null;
      segundaSeleccion = null;
      bloqueado = false;
      renderizarTablero();
    }, 900);
  }
}

document.getElementById("btn-reiniciar").addEventListener("click", crearTablero);

crearTablero();
