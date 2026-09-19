// Diseños del juego de pintar — cada uno es un dibujo completo con sus regiones.
// Para agregar un diseño nuevo: copiar un bloque, cambiarle el id, el nombre y el svg,
// asegurando que cada región tenga class="region-pintable" y un data-id único dentro del diseño.

window.DISENOS_PINTAR = [
  {
    id: "flor",
    nombre: "Flor",
    svg: `<svg viewBox="0 0 300 300" aria-label="Flor para pintar">
      <rect x="144" y="178" width="12" height="90" rx="4" class="region-pintable" data-id="tallo" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="115" cy="225" rx="28" ry="14" transform="rotate(-30 115 225)" class="region-pintable" data-id="hoja1" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="185" cy="245" rx="28" ry="14" transform="rotate(30 185 245)" class="region-pintable" data-id="hoja2" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="150" cy="95" rx="26" ry="45" transform="rotate(0 150 150)" class="region-pintable" data-id="petalo1" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="150" cy="95" rx="26" ry="45" transform="rotate(60 150 150)" class="region-pintable" data-id="petalo2" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="150" cy="95" rx="26" ry="45" transform="rotate(120 150 150)" class="region-pintable" data-id="petalo3" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="150" cy="95" rx="26" ry="45" transform="rotate(180 150 150)" class="region-pintable" data-id="petalo4" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="150" cy="95" rx="26" ry="45" transform="rotate(240 150 150)" class="region-pintable" data-id="petalo5" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="150" cy="95" rx="26" ry="45" transform="rotate(300 150 150)" class="region-pintable" data-id="petalo6" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <circle cx="150" cy="150" r="28" class="region-pintable" data-id="centro" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
    </svg>`,
  },
  {
    id: "casa",
    nombre: "Casa",
    svg: `<svg viewBox="0 0 300 300" aria-label="Casa para pintar">
      <rect x="0" y="0" width="300" height="230" class="region-pintable" data-id="cielo" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <rect x="0" y="230" width="300" height="70" class="region-pintable" data-id="pasto" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <circle cx="240" cy="55" r="28" class="region-pintable" data-id="sol" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <polygon points="70,150 150,95 230,150" class="region-pintable" data-id="techo" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <rect x="80" y="150" width="140" height="90" class="region-pintable" data-id="pared" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <rect x="130" y="190" width="40" height="50" class="region-pintable" data-id="puerta" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <rect x="90" y="165" width="30" height="30" class="region-pintable" data-id="ventana" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <rect x="245" y="200" width="14" height="40" class="region-pintable" data-id="tronco" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <circle cx="252" cy="180" r="30" class="region-pintable" data-id="copa" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
    </svg>`,
  },
  {
    id: "pez",
    nombre: "Pez",
    svg: `<svg viewBox="0 0 300 300" aria-label="Pez para pintar">
      <rect x="0" y="0" width="300" height="300" class="region-pintable" data-id="agua" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="140" cy="150" rx="80" ry="55" class="region-pintable" data-id="cuerpo" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <polygon points="215,150 270,110 270,190" class="region-pintable" data-id="cola" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <polygon points="120,100 150,60 170,105" class="region-pintable" data-id="aleta_superior" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <polygon points="120,200 150,240 170,195" class="region-pintable" data-id="aleta_inferior" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <circle cx="180" cy="60" r="8" class="region-pintable" data-id="burbuja1" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <circle cx="200" cy="40" r="5" class="region-pintable" data-id="burbuja2" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
    </svg>`,
  },
  {
    id: "mariposa",
    nombre: "Mariposa",
    svg: `<svg viewBox="0 0 300 300" aria-label="Mariposa para pintar">
      <rect x="145" y="90" width="10" height="120" rx="4" class="region-pintable" data-id="cuerpo" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="95" cy="120" rx="60" ry="45" class="region-pintable" data-id="ala_sup_izq" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="205" cy="120" rx="60" ry="45" class="region-pintable" data-id="ala_sup_der" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="105" cy="200" rx="45" ry="35" class="region-pintable" data-id="ala_inf_izq" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
      <ellipse cx="195" cy="200" rx="45" ry="35" class="region-pintable" data-id="ala_inf_der" fill="#FFFFFF" stroke="#2C2C2A" stroke-width="3"/>
    </svg>`,
  },
];
