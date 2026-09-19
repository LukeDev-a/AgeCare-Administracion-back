// Conjuntos de palabras para la sopa de letras — cada uno define dónde va cada palabra
// en una grilla de 6x6 (fila, columna, empezando en 0). Solo se usan líneas rectas,
// de izquierda a derecha o de arriba hacia abajo, para que sea fácil de encontrar.
// Para agregar un conjunto nuevo: copiar un bloque y definir nuevas palabras sin que
// sus casillas se crucen con letras distintas.

window.CONJUNTOS_SOPA = [
  {
    id: "casa-flor-amor-sol",
    palabras: [
      { palabra: "CASA", celdas: [[1, 0], [1, 1], [1, 2], [1, 3]] },
      { palabra: "FLOR", celdas: [[0, 5], [1, 5], [2, 5], [3, 5]] },
      { palabra: "AMOR", celdas: [[4, 1], [4, 2], [4, 3], [4, 4]] },
      { palabra: "SOL", celdas: [[3, 0], [4, 0], [5, 0]] },
    ],
  },
  {
    id: "gato-luna-agua-pan",
    palabras: [
      { palabra: "GATO", celdas: [[1, 0], [1, 1], [1, 2], [1, 3]] },
      { palabra: "LUNA", celdas: [[0, 5], [1, 5], [2, 5], [3, 5]] },
      { palabra: "AGUA", celdas: [[4, 1], [4, 2], [4, 3], [4, 4]] },
      { palabra: "PAN", celdas: [[3, 0], [4, 0], [5, 0]] },
    ],
  },
];
