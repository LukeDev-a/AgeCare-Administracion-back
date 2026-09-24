// Banco de sonidos e imágenes. Cada item tiene un id (usado para reproducir su sonido
// en script.js), un nombre visible, y un ícono SVG simple.
// Para agregar uno nuevo: agregar aquí el ícono y su reproductor de sonido en script.js.

window.BANCO_SONIDOS = [
  {
    id: "campana",
    nombre: "Campana",
    svg: `<circle cx="50" cy="55" r="30" fill="#FAC775"/><rect x="40" y="85" width="20" height="8" rx="3" fill="#993C1D"/><circle cx="50" cy="30" r="6" fill="#993C1D"/>`,
  },
  {
    id: "reloj",
    nombre: "Reloj",
    svg: `<circle cx="50" cy="50" r="34" fill="#F1EFE8" stroke="#2C2C2A" stroke-width="4"/><line x1="50" y1="50" x2="50" y2="26" stroke="#2C2C2A" stroke-width="4"/><line x1="50" y1="50" x2="68" y2="58" stroke="#2C2C2A" stroke-width="4"/>`,
  },
  {
    id: "tambor",
    nombre: "Tambor",
    svg: `<ellipse cx="50" cy="35" rx="32" ry="14" fill="#D4537E"/><rect x="18" y="35" width="64" height="35" fill="#D4537E"/><ellipse cx="50" cy="70" rx="32" ry="14" fill="#993C1D"/>`,
  },
  {
    id: "pajaro",
    nombre: "Pájaro",
    svg: `<ellipse cx="50" cy="55" rx="26" ry="18" fill="#378ADD"/><polygon points="76,50 94,44 82,60" fill="#378ADD"/><circle cx="34" cy="45" r="6" fill="white"/>`,
  },
  {
    id: "telefono",
    nombre: "Teléfono",
    svg: `<rect x="30" y="20" width="40" height="60" rx="8" fill="#639922"/><circle cx="50" cy="70" r="5" fill="white"/><rect x="38" y="30" width="24" height="14" rx="2" fill="white"/>`,
  },
  {
    id: "lluvia",
    nombre: "Lluvia",
    svg: `<ellipse cx="35" cy="35" rx="20" ry="16" fill="#B5D4F4"/><ellipse cx="60" cy="30" rx="24" ry="20" fill="#B5D4F4"/><line x1="30" y1="60" x2="24" y2="80" stroke="#378ADD" stroke-width="4" stroke-linecap="round"/><line x1="50" y1="60" x2="44" y2="82" stroke="#378ADD" stroke-width="4" stroke-linecap="round"/><line x1="70" y1="60" x2="64" y2="80" stroke="#378ADD" stroke-width="4" stroke-linecap="round"/>`,
  },
];
