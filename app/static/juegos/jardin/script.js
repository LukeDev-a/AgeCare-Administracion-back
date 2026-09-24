// Jardín virtual AgeCare — regar una planta y verla crecer.
// Sin fracaso posible: la planta nunca se marchita, no hay que recordarla ni hay urgencia.

const RIEGOS_POR_ETAPA = 2;

const MACETA_SVG = `
  <rect x="60" y="190" width="80" height="45" rx="6" fill="#993C1D"/>
  <rect x="55" y="182" width="90" height="14" rx="4" fill="#B15A34"/>
`;

const ETAPAS = [
  {
    mensaje: "Acabas de plantar una semilla",
    dibujo: `<circle cx="100" cy="205" r="6" fill="#5F5E5A"/>`,
  },
  {
    mensaje: "¡Ya está brotando!",
    dibujo: `
      <rect x="97" y="165" width="6" height="30" fill="#3B6D11"/>
      <ellipse cx="88" cy="168" rx="12" ry="7" fill="#639922" transform="rotate(-20 88 168)"/>
      <ellipse cx="112" cy="168" rx="12" ry="7" fill="#639922" transform="rotate(20 112 168)"/>
    `,
  },
  {
    mensaje: "Tu planta está creciendo bien",
    dibujo: `
      <rect x="97" y="130" width="6" height="65" fill="#3B6D11"/>
      <ellipse cx="84" cy="150" rx="15" ry="8" fill="#639922" transform="rotate(-25 84 150)"/>
      <ellipse cx="116" cy="150" rx="15" ry="8" fill="#639922" transform="rotate(25 116 150)"/>
      <ellipse cx="86" cy="175" rx="14" ry="7" fill="#639922" transform="rotate(-15 86 175)"/>
      <ellipse cx="114" cy="175" rx="14" ry="7" fill="#639922" transform="rotate(15 114 175)"/>
    `,
  },
  {
    mensaje: "Ya casi tiene su primera flor",
    dibujo: `
      <rect x="97" y="105" width="6" height="90" fill="#3B6D11"/>
      <ellipse cx="82" cy="140" rx="16" ry="8" fill="#639922" transform="rotate(-25 82 140)"/>
      <ellipse cx="118" cy="140" rx="16" ry="8" fill="#639922" transform="rotate(25 118 140)"/>
      <ellipse cx="84" cy="170" rx="14" ry="7" fill="#639922" transform="rotate(-15 84 170)"/>
      <ellipse cx="116" cy="170" rx="14" ry="7" fill="#639922" transform="rotate(15 116 170)"/>
      <circle cx="100" cy="100" r="10" fill="#95C97A"/>
    `,
  },
  {
    mensaje: "¡Mira qué bonita quedó tu planta!",
    dibujo: `
      <rect x="97" y="105" width="6" height="90" fill="#3B6D11"/>
      <ellipse cx="82" cy="150" rx="16" ry="8" fill="#639922" transform="rotate(-25 82 150)"/>
      <ellipse cx="118" cy="150" rx="16" ry="8" fill="#639922" transform="rotate(25 118 150)"/>
      <ellipse cx="84" cy="175" rx="14" ry="7" fill="#639922" transform="rotate(-15 84 175)"/>
      <ellipse cx="116" cy="175" rx="14" ry="7" fill="#639922" transform="rotate(15 116 175)"/>
      <circle cx="100" cy="70" r="13" fill="#D4537E"/>
      <circle cx="82" cy="85" r="10" fill="#D4537E"/>
      <circle cx="118" cy="85" r="10" fill="#D4537E"/>
      <circle cx="100" cy="80" r="9" fill="#FAC775"/>
    `,
  },
];

const MENSAJES_EN_ETAPA_FINAL = [
  "¡Mira qué bonita quedó tu planta!",
  "Tu planta se ve feliz hoy",
  "Gracias por cuidar tu jardín",
  "Tu planta agradece el agua",
];

let riegos = 0;
let etapaActual = 0;
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

function renderizarPlanta() {
  const etapa = ETAPAS[etapaActual];
  document.getElementById("maceta").innerHTML = `
    <svg viewBox="0 0 200 240" aria-label="Tu planta">
      ${etapa.dibujo}
      ${MACETA_SVG}
    </svg>
  `;
}

function elegirMensaje() {
  if (etapaActual < ETAPAS.length - 1) {
    return ETAPAS[etapaActual].mensaje;
  }
  const indiceAlAzar = Math.floor(Math.random() * MENSAJES_EN_ETAPA_FINAL.length);
  return MENSAJES_EN_ETAPA_FINAL[indiceAlAzar];
}

function regarPlanta() {
  inicializarAudio();
  reproducirSonido(550, 150);

  riegos += 1;
  const nuevaEtapa = Math.min(Math.floor(riegos / RIEGOS_POR_ETAPA), ETAPAS.length - 1);

  if (nuevaEtapa !== etapaActual) {
    etapaActual = nuevaEtapa;
    reproducirSonido(700, 200);
  }

  renderizarPlanta();
  document.getElementById("mensaje-estado").textContent = elegirMensaje();
}

function empezarPlantaNueva() {
  riegos = 0;
  etapaActual = 0;
  renderizarPlanta();
  document.getElementById("mensaje-estado").textContent = ETAPAS[0].mensaje;
}

document.getElementById("btn-regar").addEventListener("click", regarPlanta);
document.getElementById("btn-nueva-planta").addEventListener("click", empezarPlantaNueva);

empezarPlantaNueva();
