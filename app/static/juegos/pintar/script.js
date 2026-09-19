// Pintar AgeCare — colorear un dibujo simple tocando regiones
// Sin errores posibles: cualquier color se puede tocar en cualquier momento, sin límite.

const PALETA = [
  { nombre: "Rojo", color: "#E24B4A" },
  { nombre: "Naranjo", color: "#EF9F27" },
  { nombre: "Amarillo", color: "#FAC775" },
  { nombre: "Verde", color: "#639922" },
  { nombre: "Azul", color: "#378ADD" },
  { nombre: "Morado", color: "#7F77DD" },
  { nombre: "Rosado", color: "#D4537E" },
  { nombre: "Café", color: "#993C1D" },
];

let colorSeleccionado = PALETA[0].color;
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
  ganancia.gain.setValueAtTime(0.12, audioContext.currentTime);
  ganancia.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + duracionMs / 1000);
  oscilador.connect(ganancia);
  ganancia.connect(audioContext.destination);
  oscilador.start();
  oscilador.stop(audioContext.currentTime + duracionMs / 1000);
}

function crearPaleta() {
  const contenedor = document.getElementById("paleta");
  contenedor.innerHTML = "";

  PALETA.forEach((item, indice) => {
    const boton = document.createElement("button");
    boton.className = "color-boton" + (indice === 0 ? " seleccionado" : "");
    boton.style.background = item.color;
    boton.setAttribute("aria-label", item.nombre);
    boton.addEventListener("click", () => seleccionarColor(item.color, boton));
    contenedor.appendChild(boton);
  });
}

function seleccionarColor(color, botonElegido) {
  colorSeleccionado = color;
  document.querySelectorAll(".color-boton").forEach((boton) => boton.classList.remove("seleccionado"));
  botonElegido.classList.add("seleccionado");
}

function elegirDisenoAlAzar() {
  const disenos = window.DISENOS_PINTAR || [];
  return disenos[Math.floor(Math.random() * disenos.length)];
}

function crearDibujo() {
  const disenoActual = elegirDisenoAlAzar();
  const contenedor = document.getElementById("dibujo");
  contenedor.innerHTML = disenoActual.svg;

  contenedor.querySelectorAll(".region-pintable").forEach((region) => {
    region.addEventListener("click", () => {
      inicializarAudio();
      region.setAttribute("fill", colorSeleccionado);
      reproducirSonido(520, 90);
    });
  });
}

document.getElementById("btn-limpiar").addEventListener("click", crearDibujo);

crearPaleta();
crearDibujo();
