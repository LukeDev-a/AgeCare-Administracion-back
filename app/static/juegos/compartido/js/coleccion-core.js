(function (root) {
  'use strict';
  const pick = (items, rng) => items[Math.floor(rng() * items.length)];
  function shuffled(items, rng = Math.random) {
    const copy = items.slice();
    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy;
  }
  function sudokuCount(board, limit = 2) {
    const work = board.slice();
    function options(index) {
      const r = Math.floor(index / 4), c = index % 4;
      return [1, 2, 3, 4].filter(n => !work.some((v, j) => v === n &&
        (Math.floor(j / 4) === r || j % 4 === c ||
         Math.floor(j / 8) === Math.floor(r / 2) && Math.floor(j % 4 / 2) === Math.floor(c / 2))));
    }
    function solve() {
      let selected = -1, candidates;
      for (let i = 0; i < 16; i++) if (!work[i]) {
        const values = options(i);
        if (!values.length) return 0;
        if (selected < 0 || values.length < candidates.length) { selected = i; candidates = values; }
      }
      if (selected < 0) return 1;
      let count = 0;
      for (const n of candidates) {
        work[selected] = n; count += solve(); work[selected] = 0;
        if (count >= limit) break;
      }
      return Math.min(count, limit);
    }
    return solve();
  }
  function sudoku(rng = Math.random) {
    const digits = shuffled([1, 2, 3, 4], rng);
    const rows = shuffled([0, 1], rng).flatMap(b => shuffled([b * 2, b * 2 + 1], rng));
    const cols = shuffled([0, 1], rng).flatMap(b => shuffled([b * 2, b * 2 + 1], rng));
    const solution = rows.flatMap(r => cols.map(c => digits[(r * 2 + Math.floor(r / 2) + c) % 4]));
    const board = solution.slice();
    let removed = 0;
    for (const index of shuffled([...board.keys()], rng)) {
      const old = board[index]; board[index] = 0;
      if (sudokuCount(board) !== 1) board[index] = old;
      else removed++;
      if (removed === 8) break;
    }
    return { board, solution };
  }
  function hanoiMoves(pegs) {
    const moves = [];
    pegs.forEach((from, i) => { if (from.length) pegs.forEach((to, j) => {
      if (i !== j && (!to.length || from[from.length - 1] < to[to.length - 1])) moves.push([i, j]);
    }); });
    return moves;
  }
  function hanoiHint(pegs, goal) {
    const count = pegs.flat().length, seen = new Set([JSON.stringify(pegs)]);
    const queue = [{ pegs: pegs.map(p => p.slice()), first: null }];
    for (let i = 0; i < queue.length; i++) {
      const state = queue[i];
      if (state.pegs[goal].length === count) return state.first;
      for (const move of hanoiMoves(state.pegs)) {
        const next = state.pegs.map(p => p.slice()); next[move[1]].push(next[move[0]].pop());
        const key = JSON.stringify(next);
        if (!seen.has(key)) { seen.add(key); queue.push({ pegs: next, first: state.first || move }); }
      }
    }
    return null;
  }
  function balance(rng = Math.random) {
    const weights = shuffled([1, 2, 3, 4, 5, 6, 7, 8, 9], rng).slice(0, 6);
    return { weights, target: weights.slice(0, rng() < .5 ? 2 : 3).reduce((a, b) => a + b, 0) };
  }
  function sequence(length = 3, rng = Math.random) {
    const result = [];
    while (result.length < length) result.push(pick([0, 1, 2, 3].filter(n => n !== result[result.length - 1]), rng));
    return result;
  }
  function pins(rng = Math.random) {
    const offset = Math.round(rng() * 16 - 8), result = [];
    for (let row = 0; row < 4; row++) for (let col = 0; col <= row; col++)
      result.push({ x: 150 + offset + (col - row / 2) * 36, y: 45 + row * 32, down: false });
    return result;
  }
  function bowl(current, aim, force) {
    const x = 150 + aim * 18, radius = [0, 18, 27, 37][force];
    return current.map(p => ({ ...p, down: p.down || Math.abs(p.x - x) <= radius }));
  }
  function runs(line) {
    const result = []; let count = 0;
    for (const cell of [...line, false]) {
      if (cell) count++;
      else if (count) { result.push(count); count = 0; }
    }
    return result.length ? result : [0];
  }
  function clues(board) {
    return {
      rows: Array.from({ length: 5 }, (_, r) => runs(board.slice(r * 5, r * 5 + 5))),
      cols: Array.from({ length: 5 }, (_, c) => runs(Array.from({ length: 5 }, (_, r) => board[r * 5 + c])))
    };
  }
  function nonogramSolutions(info, limit = 2) {
    const choices = Array.from({ length: 32 }, (_, mask) => Array.from({ length: 5 }, (_, i) => Boolean(mask & (1 << i))));
    const rows = info.rows.map(clue => choices.filter(line => String(runs(line)) === String(clue)));
    const cols = info.cols.map(clue => choices.filter(line => String(runs(line)) === String(clue)));
    const selected = []; let total = 0;
    function visit(row) {
      if (row === 5) { total++; return; }
      for (const line of rows[row]) {
        selected.push(line);
        if (cols.every((patterns, c) => patterns.some(pattern => selected.every((r, i) => r[c] === pattern[i])))) visit(row + 1);
        selected.pop();
        if (total >= limit) return;
      }
    }
    visit(0); return total;
  }
  function nonogram(rng = Math.random) {
    for (let i = 0; i < 150; i++) {
      const board = Array.from({ length: 25 }, () => rng() < .55), info = clues(board);
      const filled = board.filter(Boolean).length;
      if (filled >= 8 && filled <= 18 && nonogramSolutions(info) === 1) return { board, ...info };
    }
    const board = Array.from({ length: 25 }, (_, i) => Math.floor(i / 5) === 2 || i % 5 === 2);
    return { board, ...clues(board) };
  }
  function codeScore(secret, guess) {
    let exact = 0, present = 0;
    const remaining = secret.slice();
    guess.forEach((value, i) => { if (value === secret[i]) { exact++; remaining[i] = null; } });
    guess.forEach((value, i) => {
      if (value !== secret[i]) {
        const index = remaining.indexOf(value);
        if (index >= 0) { present++; remaining[index] = null; }
      }
    });
    return { exact, present };
  }
  function distance(a, b, size = 4) { return Math.abs(Math.floor(a / size) - Math.floor(b / size)) + Math.abs(a % size - b % size); }
  function svg(tag, attributes = {}, text) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = text;
    return node;
  }
  const api = { shuffled, sudoku, sudokuCount, hanoiMoves, hanoiHint, balance, sequence, pins, bowl,
    runs, clues, nonogram, nonogramSolutions, codeScore, distance, svg };
  root.AgecareExtra = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
