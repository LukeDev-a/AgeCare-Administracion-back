(function () {
  'use strict';
  const G = AgecareGames;
  let board, turn, mode = 'computer', finished, hint = -1, starter = 'O';
  const ui = G.boot('Toca una casilla libre para colocar tu símbolo. Forma una línea de tres. Puedes jugar con la computadora o con otra persona.', round);
  function computer() {
    const free = board.map((value, index) => value ? -1 : index).filter(index => index >= 0);
    if (free.length) board[G.shuffle(free)[0]] = 'O';
  }
  function round() {
    board = Array(9).fill(''); hint = -1; finished = false;
    starter = starter === 'X' ? 'O' : 'X'; turn = starter;
    if (mode === 'computer') { if (starter === 'O') computer(); turn = 'X'; }
    ui.say(''); render();
  }
  function play(index) {
    if (finished || board[index]) return;
    board[index] = turn; hint = -1;
    if (!G.winner(board) && board.some(value => !value)) {
      if (mode === 'computer') computer();
      else turn = turn === 'X' ? 'O' : 'X';
    }
    const win = G.winner(board); finished = !!win || board.every(Boolean); render();
    ui.say(win ? `${win.player === 'O' && mode === 'computer' ? 'La computadora' : 'El jugador ' + win.player} completó una línea. ¡Gracias por jugar!` : finished ? 'Empate: llenaron el tablero. Puedes comenzar otra partida.' : `Turno de ${turn}.`, !!win || finished);
  }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    const label = G.el('label', 'Modo de juego: ', 'texto-central modo');
    const select = G.el('select'); select.setAttribute('aria-label', 'Modo de juego');
    for (const [value, text] of [['computer','Con la computadora'],['people','Dos personas']]) {
      const option = G.el('option', text); option.value = value; select.append(option);
    }
    select.value = mode; select.addEventListener('change', () => { mode = select.value; round(); }); label.append(select); ui.board.append(label);
    ui.board.append(G.el('p', finished ? 'Partida terminada' : mode === 'computer' ? 'Tú juegas con X. La computadora usa O.' : `Turno del jugador ${turn}`, 'texto-central'));
    const grid = G.el('div', undefined, 'tres-tablero'); const win = G.winner(board);
    board.forEach((symbol, index) => {
      const b = G.button(symbol || (hint === index ? '★' : ''), () => play(index), 'tarjeta casilla-tres');
      b.disabled = finished || !!symbol;
      b.setAttribute('aria-label', `Fila ${Math.floor(index / 3) + 1}, columna ${index % 3 + 1}: ${symbol || (hint === index ? 'pista' : 'libre')}`);
      if (win && win.line.includes(index)) b.classList.add('marcada'); grid.append(b);
    }); ui.board.append(grid);
    const clue = G.button('Sugerir una casilla', () => {
      const free = board.map((value, index) => value ? -1 : index).filter(i => i >= 0);
      hint = free.find(i => { const copy = board.slice(); copy[i] = turn; return !!G.winner(copy); }) ?? (free.includes(4) ? 4 : free[0]);
      render(); ui.say(`Puedes probar la estrella: fila ${Math.floor(hint / 3) + 1}, columna ${hint % 3 + 1}.`);
    }, 'boton-grande secundario'); clue.disabled = finished; ui.controls.append(clue);
  }
  round();
})();
