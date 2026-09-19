// Temas del memorama — cada tema define 6 parejas.
// Cada pareja es solo una forma dibujada con SVG básico (sin imágenes externas, sin IA).
// Para agregar un tema nuevo: copiar un bloque, cambiarle el id y las 6 parejas.

window.TEMAS_MEMORAMA = [
  {
    id: "naturaleza",
    nombre: "Naturaleza",
    pares: [
      { id: "sol", svg: `<circle cx="50" cy="50" r="34" fill="#FAC775"/>` },
      { id: "arbol", svg: `<polygon points="50,14 86,80 14,80" fill="#3B6D11"/>` },
      { id: "nube", svg: `<ellipse cx="35" cy="55" rx="20" ry="16" fill="#B5D4F4"/><ellipse cx="60" cy="50" rx="24" ry="20" fill="#B5D4F4"/>` },
      { id: "flor", svg: `<circle cx="50" cy="30" r="14" fill="#D4537E"/><circle cx="50" cy="70" r="14" fill="#D4537E"/><circle cx="30" cy="50" r="14" fill="#D4537E"/><circle cx="70" cy="50" r="14" fill="#D4537E"/><circle cx="50" cy="50" r="12" fill="#FAC775"/>` },
      { id: "luna", svg: `<path d="M60 15 A35 35 0 1 0 60 85 A28 28 0 1 1 60 15" fill="#888780"/>` },
      { id: "montana", svg: `<polygon points="20,80 45,30 60,55 75,25 90,80" fill="#5F5E5A"/>` },
    ],
  },
  {
    id: "animales",
    nombre: "Animales",
    pares: [
      { id: "pez", svg: `<ellipse cx="45" cy="50" rx="28" ry="18" fill="#378ADD"/><polygon points="73,50 92,35 92,65" fill="#378ADD"/>` },
      { id: "pajaro", svg: `<ellipse cx="50" cy="55" rx="26" ry="18" fill="#D85A30"/><polygon points="76,50 94,44 82,60" fill="#D85A30"/><circle cx="34" cy="45" r="6" fill="white"/>` },
      { id: "gato", svg: `<circle cx="50" cy="55" r="28" fill="#888780"/><polygon points="28,35 38,15 44,40" fill="#888780"/><polygon points="72,35 62,15 56,40" fill="#888780"/><circle cx="40" cy="55" r="3" fill="#2C2C2A"/><circle cx="60" cy="55" r="3" fill="#2C2C2A"/>` },
      { id: "mariposa", svg: `<ellipse cx="30" cy="35" rx="18" ry="14" fill="#D4537E"/><ellipse cx="30" cy="65" rx="18" ry="14" fill="#D4537E"/><ellipse cx="70" cy="35" rx="18" ry="14" fill="#D4537E"/><ellipse cx="70" cy="65" rx="18" ry="14" fill="#D4537E"/><rect x="47" y="25" width="6" height="50" rx="3" fill="#5F5E5A"/>` },
      { id: "tortuga", svg: `<ellipse cx="50" cy="55" rx="30" ry="22" fill="#3B6D11"/><circle cx="82" cy="50" r="10" fill="#3B6D11"/><rect x="30" y="72" width="10" height="14" fill="#3B6D11"/><rect x="60" y="72" width="10" height="14" fill="#3B6D11"/>` },
      { id: "conejo", svg: `<ellipse cx="50" cy="60" rx="24" ry="20" fill="#D3D1C7"/><ellipse cx="38" cy="20" rx="7" ry="22" fill="#D3D1C7"/><ellipse cx="58" cy="20" rx="7" ry="22" fill="#D3D1C7"/>` },
    ],
  },
  {
    id: "casa",
    nombre: "Objetos de casa",
    pares: [
      { id: "taza", svg: `<rect x="25" y="35" width="40" height="35" rx="4" fill="#993C1D"/><path d="M65 42 h12 a10 10 0 0 1 0 20 h-12" fill="none" stroke="#993C1D" stroke-width="6"/>` },
      { id: "silla", svg: `<rect x="30" y="20" width="8" height="60" fill="#5F5E5A"/><rect x="30" y="45" width="40" height="8" fill="#5F5E5A"/><rect x="30" y="45" width="40" height="8" fill="#5F5E5A" transform="rotate(90 30 45)" opacity="0"/><rect x="25" y="45" width="50" height="8" fill="#5F5E5A"/><rect x="62" y="45" width="8" height="35" fill="#5F5E5A"/>` },
      { id: "puerta", svg: `<rect x="30" y="15" width="40" height="70" rx="4" fill="#993C1D"/><circle cx="62" cy="52" r="4" fill="#FAC775"/>` },
      { id: "reloj", svg: `<circle cx="50" cy="50" r="32" fill="#F1EFE8" stroke="#2C2C2A" stroke-width="4"/><line x1="50" y1="50" x2="50" y2="28" stroke="#2C2C2A" stroke-width="4"/><line x1="50" y1="50" x2="66" y2="58" stroke="#2C2C2A" stroke-width="4"/>` },
      { id: "llave", svg: `<circle cx="30" cy="50" r="14" fill="none" stroke="#5F5E5A" stroke-width="7"/><rect x="42" y="46" width="42" height="8" fill="#5F5E5A"/><rect x="68" y="54" width="8" height="12" fill="#5F5E5A"/><rect x="78" y="54" width="8" height="16" fill="#5F5E5A"/>` },
      { id: "libro", svg: `<rect x="20" y="25" width="60" height="50" rx="4" fill="#185FA5"/><line x1="50" y1="25" x2="50" y2="75" stroke="white" stroke-width="3"/>` },
    ],
  },
];
