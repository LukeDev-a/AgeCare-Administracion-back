// Buscar diferencias AgeCare — encontrar los detalles que cambian entre dos escenas
// Sin penalización por tocar en el lugar equivocado, sin cronómetro.

// Cada zona usa las mismas coordenadas en ambas imágenes (el layout es igual),
// solo cambia el color o la presencia de un elemento en ese punto.
const ZONAS = [
  { id: "sol", x: 250, y: 50, radio: 35 },
  { id: "puerta", x: 137, y: 212, radio: 35 },
  { id: "pajaro", x: 70, y: 60, radio: 35 },
  { id: "ventana", x: 165, y: 175, radio: 35 },
];

const escenaBase = `
  <rect width="300" height="300" fill="#B5D4F4"/>
  <rect y="230" width="300" height="70" fill="#97C459"/>
  <rect x="90" y="150" width="90" height="80" fill="#D4C0A1"/>
  <polygon points="80,150 135,110 190,150" fill="#993C1D"/>
  <rect x="100" y="165" width="20" height="20" fill="#E6F1FB"/>
  <rect x="210" y="190" width="12" height="40" fill="#5F5E5A"/>
  <circle cx="216" cy="175" r="28" fill="#3B6D11"/>
`;

const imagenASVG = `
  ${escenaBase}
  <circle cx="250" cy="50" r="30" fill="#FAC775"/>
  <rect x="125" y="195" width="25" height="35" fill="#993C1D"/>
`;

const imagenBSVG = `
  ${escenaBase}
  <circle cx="250" cy="50" r="30" fill="#F0997B"/>
  <rect x="125" y="195" width="25" height="35" fill="#378ADD"/>
  <rect x="150" y="165" width="20" height="20" fill="#E6F1FB"/>
  <path d="M55 60 Q70 45 85 60 Q70 50 55 60" fill="#2C2C2A"/>
`;

let encontradas = new Set();
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

function crearEscena(idContenedor, contenidoSvg) {
  const contenedor = document.getElementById(idContenedor);
  contenedor.innerHTML = `<svg viewBox="0 0 300 300" aria-hidden="true">${contenidoSvg}</svg>`;

  ZONAS.forEach((zona) => {
    const boton = document.createElement("button");
    boton.className = "zona-diferencia";
    boton.dataset.id = zona.id;
    boton.style.left = (zona.x / 300) * 100 + "%";
    boton.style.top = (zona.y / 300) * 100 + "%";
    boton.style.width = ((zona.radio * 2) / 300) * 100 + "%";
    boton.style.height = ((zona.radio * 2) / 300) * 100 + "%";
    boton.setAttribute("aria-label", "Posible diferencia");
    boton.addEventListener("click", () => marcarEncontrada(zona.id));
    contenedor.appendChild(boton);
  });
}

function marcarEncontrada(id) {
  inicializarAudio();
  if (encontradas.has(id)) return;

  encontradas.add(id);
  reproducirSonido(600, 150);

  document.querySelectorAll(`.zona-diferencia[data-id="${id}"]`).forEach((boton) => {
    boton.classList.add("encontrada");
  });

  document.getElementById("contador").textContent = encontradas.size;

  if (encontradas.size === ZONAS.length) {
    setTimeout(() => {
      reproducirSonido(784, 250);
      document.getElementById("celebracion").hidden = false;
    }, 300);
  }
}

function iniciarJuego() {
  encontradas = new Set();
  document.getElementById("contador").textContent = "0";
  document.getElementById("total").textContent = ZONAS.length;
  document.getElementById("celebracion").hidden = true;
  crearEscena("imagenA", imagenASVG);
  crearEscena("imagenB", imagenBSVG);
}

document.getElementById("btn-reiniciar").addEventListener("click", iniciarJuego);

iniciarJuego();
