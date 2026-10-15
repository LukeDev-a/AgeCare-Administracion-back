/* Utilidades de los nuevos juegos. Sin red, seguimiento, cronómetros ni dependencias. */
(function (root) {
  'use strict';
  function shuffle(values, rng = Math.random) {
    const copy = values.slice();
    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy;
  }
  function deck(values) {
    let pending = [], last;
    return () => {
      if (!pending.length) {
        pending = shuffle(values);
        if (pending.length > 1 && pending[0] === last) [pending[0], pending[1]] = [pending[1], pending[0]];
      }
      last = pending.shift();
      return last;
    };
  }
  function seeded(seed) {
    return () => {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function maze(size = 4, rng = Math.random) {
    const cells = Array.from({ length: size * size }, () => []);
    const start = [0, size - 1, size * (size - 1), size * size - 1][Math.floor(rng() * 4)];
    const seen = new Set([start]), stack = [start];
    while (stack.length) {
      const cell = stack[stack.length - 1], row = Math.floor(cell / size), col = cell % size;
      const neighbors = [row > 0 ? cell - size : -1, row < size - 1 ? cell + size : -1,
        col > 0 ? cell - 1 : -1, col < size - 1 ? cell + 1 : -1].filter(n => n >= 0 && !seen.has(n));
      if (!neighbors.length) { stack.pop(); continue; }
      const next = shuffle(neighbors, rng)[0];
      cells[cell].push(next); cells[next].push(cell); seen.add(next); stack.push(next);
    }
    const distances = Array(size * size).fill(-1), queue = [start]; distances[start] = 0;
    for (let i = 0; i < queue.length; i++) for (const next of cells[queue[i]]) {
      if (distances[next] < 0) { distances[next] = distances[queue[i]] + 1; queue.push(next); }
    }
    return { size, cells, start, goal: distances.indexOf(Math.max(...distances)) };
  }
  function path(cells, start, goal) {
    const queue = [[start]], seen = new Set([start]);
    for (let i = 0; i < queue.length; i++) {
      const route = queue[i], last = route[route.length - 1];
      if (last === goal) return route;
      for (const next of cells[last]) if (!seen.has(next)) { seen.add(next); queue.push([...route, next]); }
    }
    return [];
  }
  function domino(rng = Math.random) {
    const sequence = [Math.floor(rng() * 7)], used = new Set();
    while (sequence.length < 8) {
      const last = sequence[sequence.length - 1];
      const choices = shuffle([0, 1, 2, 3, 4, 5, 6], rng).filter(n => !used.has([last, n].sort().join('-')));
      const next = choices[0]; used.add([last, next].sort().join('-')); sequence.push(next);
    }
    return { initial: sequence.slice(0, 2), hand: shuffle(sequence.slice(1, -1).map((n, i) =>
      rng() < 0.5 ? [n, sequence[i + 2]] : [sequence[i + 2], n]), rng) };
  }
  function attach(chain, tile, side) {
    const end = side === 'left' ? chain[0] : chain[chain.length - 1];
    if (!tile.includes(end)) return null;
    const next = tile[0] === end ? tile[1] : tile[0];
    return side === 'left' ? [next, ...chain] : [...chain, next];
  }
  const lines = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
  function winner(board) {
    for (const line of lines) if (board[line[0]] && line.every(i => board[i] === board[line[0]])) return { player: board[line[0]], line };
    return null;
  }
  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function button(text, action, className = 'boton-grande') {
    const node = el('button', text, className); node.type = 'button'; node.addEventListener('click', action); return node;
  }
  function boot(instruction, reset) {
    const board = document.getElementById('tablero'), controls = document.getElementById('controles');
    const message = document.getElementById('mensaje');
    document.getElementById('instruccion').textContent = instruction;
    const say = (text, success = false) => {
      message.textContent = text; message.className = success ? 'aviso acierto' : 'aviso';
    };
    document.getElementById('nueva').addEventListener('click', () => { say(''); reset(); });
    return { board, controls, say, clear: () => { board.replaceChildren(); controls.replaceChildren(); say(''); } };
  }
  root.AgecareGames = { shuffle, deck, seeded, maze, path, domino, attach, winner, el, button, boot };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.AgecareGames;
})(globalThis);
