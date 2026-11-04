(function () {
  'use strict';
  const G = AgecareGames, X = AgecareExtra;
  let pegs, goal, selected, done, history, count = 3, previousStart = -1;
  const ui = G.boot('Toca una torre para tomar su disco superior y otra para dejarlo. Un disco grande nunca va sobre uno pequeño. Lleva todos a la torre indicada.', round);
  function round() {
    const start = X.shuffled([0, 1, 2].filter(n => n !== previousStart))[0]; previousStart = start;
    goal = X.shuffled([0, 1, 2].filter(n => n !== start))[0];
    pegs = [[], [], []]; pegs[start] = Array.from({ length: count }, (_, i) => count - i);
    selected = -1; done = false; history = []; render(); ui.say('Toca la torre que tiene los discos para comenzar.');
  }
  function choose(index) {
    if (done) return;
    if (selected < 0) { if (!pegs[index].length) { ui.say('Esa torre está vacía. Elige una que tenga discos.'); return; } selected = index; render(); ui.say(`Ahora toca la torre de destino. Has elegido la torre ${index + 1}.`); return; }
    if (selected === index) { selected = -1; render(); return; }
    if (!X.hanoiMoves(pegs).some(([from, to]) => from === selected && to === index)) { ui.say('Ese movimiento colocaría un disco grande sobre uno pequeño. Elige otra torre.'); return; }
    history.push(pegs.map(p => p.slice())); pegs[index].push(pegs[selected].pop()); selected = -1;
    done = pegs[goal].length === count; render(); ui.say(done ? '¡Llevaste todos los discos a su torre!' : 'Movimiento realizado. Puedes continuar o deshacerlo.', done);
  }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    ui.board.append(G.el('p', `Destino: torre ${goal + 1} · Movimientos: ${history.length}`, 'resumen-extra'));
    const area = G.el('div', undefined, 'torres-extra');
    pegs.forEach((stack, index) => {
      const b = G.button('', () => choose(index), 'torre-extra'); b.setAttribute('aria-pressed', String(selected === index));
      b.setAttribute('aria-label', `Torre ${index + 1}${index === goal ? ', destino' : ''}. Discos de abajo hacia arriba: ${stack.join(', ') || 'ninguno'}`);
      const pole = G.el('span', undefined, 'pila-extra');
      stack.forEach(size => { const d = G.el('span', String(size), 'disco-extra'); d.style.width = `${30 + size * 15}%`; pole.append(d); });
      b.append(pole, G.el('span', `Torre ${index + 1}${index === goal ? ' ★' : ''}`)); b.disabled = done; area.append(b);
    }); ui.board.append(area);
    ui.controls.append(G.button('Pista del próximo movimiento', () => { const move = X.hanoiHint(pegs, goal); if (move) ui.say(`Mueve el disco superior de la torre ${move[0] + 1} a la torre ${move[1] + 1}.`); }, 'boton-grande secundario'));
    const undo = G.button('Deshacer', () => { if (history.length) { pegs = history.pop(); selected = -1; done = false; render(); ui.say('Movimiento deshecho.'); } }, 'boton-grande secundario'); undo.disabled = !history.length; ui.controls.append(undo);
    ui.controls.append(G.button(count === 3 ? 'Probar con 4 discos' : 'Volver a 3 discos', () => { count = count === 3 ? 4 : 3; round(); }, 'boton-grande secundario'));
  }
  round();
})();
