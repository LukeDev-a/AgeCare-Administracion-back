(function () {
  'use strict';
  const G = AgecareGames;
  let maze, current, visited, hint = -1, sequence = 0;
  const ui = G.boot('Lleva el punto hasta la casa. Toca una casilla vecina por un paso abierto o usa los botones de dirección. Las líneas gruesas son paredes.', round);
  function round() {
    maze = G.maze(4, G.seeded((Math.random() * 4294967295) ^ ++sequence));
    current = maze.start; visited = new Set([current]); hint = -1; ui.say('El camino es nuevo y siempre tiene solución. Puedes retroceder.'); render();
  }
  function move(next) {
    if (current === maze.goal) return;
    if (!maze.cells[current].includes(next)) { ui.say('Por ahí hay una pared o no es una casilla vecina. Busca un paso abierto.'); return; }
    current = next; visited.add(current); hint = -1; render();
    ui.say(current === maze.goal ? '¡Llegaste a casa! Puedes explorar un laberinto nuevo.' : `Estás en fila ${Math.floor(current / 4) + 1}, columna ${current % 4 + 1}.`, current === maze.goal);
  }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    const grid = G.el('div', undefined, 'laberinto'); grid.setAttribute('aria-label', 'Laberinto de cuatro filas y cuatro columnas');
    maze.cells.forEach((neighbors, index) => {
      let label = index === current ? '●' : index === maze.goal ? '⌂' : index === hint ? '★' : visited.has(index) ? '·' : '';
      const b = G.button(label, () => move(index), 'casilla-laberinto');
      const col = index % 4;
      if (!neighbors.includes(index - 4)) b.classList.add('pared-arriba');
      if (!neighbors.includes(index + 4)) b.classList.add('pared-abajo');
      if (col === 0 || !neighbors.includes(index - 1)) b.classList.add('pared-izquierda');
      if (col === 3 || !neighbors.includes(index + 1)) b.classList.add('pared-derecha');
      if (index === current) b.classList.add('persona');
      if (index === maze.goal) b.classList.add('casa');
      if (index === hint) b.classList.add('pista-camino');
      b.setAttribute('aria-label', `Fila ${Math.floor(index / 4) + 1}, columna ${col + 1}${index === current ? ', estás aquí' : index === maze.goal ? ', casa' : index === hint ? ', pista' : ''}`);
      grid.append(b);
    });
    ui.board.append(grid, G.el('p', '● Tu posición · ⌂ Casa · ★ Pista', 'texto-central leyenda'));
    const directions = [['Arriba', -4], ['Abajo', 4], ['Izquierda', -1], ['Derecha', 1]];
    for (const [name, offset] of directions) {
      const b = G.button(name, () => move(current + offset));
      b.disabled = current === maze.goal || !maze.cells[current].includes(current + offset); ui.controls.append(b);
    }
    const clue = G.button('Mostrar un paso', () => {
      const route = G.path(maze.cells, current, maze.goal); hint = route[1] ?? -1; render();
      ui.say(hint < 0 ? 'Ya llegaste a casa.' : `La estrella indica el siguiente paso: fila ${Math.floor(hint / 4) + 1}, columna ${hint % 4 + 1}.`);
    }, 'boton-grande secundario');
    ui.controls.append(clue);
  }
  round();
})();
