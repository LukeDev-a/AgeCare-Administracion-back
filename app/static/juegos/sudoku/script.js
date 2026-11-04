(function () {
  'use strict';
  const G = AgecareGames, X = AgecareExtra;
  let puzzle, values, selected, done;
  const ui = G.boot('Completa los números del 1 al 4. No se repiten en una fila, columna ni bloque de 2 por 2. Toca una casilla vacía y elige su número.', round);
  function round() { puzzle = X.sudoku(); values = puzzle.board.slice(); selected = values.indexOf(0); done = false; render(); ui.say('Los números sobre fondo gris son las pistas y no se cambian.'); }
  function put(number) {
    if (done || selected < 0) return;
    if (puzzle.solution[selected] !== number) { ui.say('Ese número no completa esta casilla. Revisa la fila, la columna y el bloque, o pide una pista.'); return; }
    values[selected] = number; selected = values.indexOf(0); done = selected < 0; render();
    ui.say(done ? '¡Completaste el sudoku!' : 'Bien. Continúa con otra casilla vacía.', done);
  }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    const grid = G.el('div', undefined, 'cuadricula-cuatro sudoku-cuatro');
    values.forEach((value, index) => {
      const b = G.button(value ? String(value) : '·', () => { selected = index; render(); ui.say(`Elige el número de la fila ${Math.floor(index / 4) + 1}, columna ${index % 4 + 1}.`); }, 'casilla-extra' + (puzzle.board[index] ? ' fija' : ''));
      b.setAttribute('aria-label', `Fila ${Math.floor(index / 4) + 1}, columna ${index % 4 + 1}: ${value || 'vacía'}${puzzle.board[index] ? ', pista fija' : ''}`);
      b.setAttribute('aria-pressed', String(selected === index)); b.disabled = Boolean(value); grid.append(b);
    });
    ui.board.append(grid, G.el('p', `${values.filter(Boolean).length} de 16 casillas completas`, 'resumen-extra'));
    for (const n of [1, 2, 3, 4]) { const b = G.button(String(n), () => put(n)); b.disabled = done; ui.controls.append(b); }
    const hint = G.button('Completar una casilla', () => { if (selected >= 0) put(puzzle.solution[selected]); }, 'boton-grande secundario');
    hint.disabled = done; ui.controls.append(hint);
  }
  round();
})();
