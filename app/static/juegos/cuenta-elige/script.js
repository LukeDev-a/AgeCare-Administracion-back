(function () {
  'use strict';
  const G = AgecareGames;
  const nextCount = G.deck([3,4,5,6,7,8,9]);
  const nextObject = G.deck([['🍎','manzanas'],['🌼','flores'],['🐟','peces'],['🍐','peras'],['☕','tazas'],['🍋','limones'],['🦋','mariposas']]);
  let count, object, marked, done;
  const ui = G.boot('Cuenta los objetos y elige su cantidad. Puedes tocarlos para marcar los que ya contaste.', round);
  function round() { count = nextCount(); object = nextObject(); marked = new Set(); done = false; ui.say(''); render(); }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    ui.board.append(G.el('h2', `¿Cuántas ${object[1]} hay?`, 'texto-central'));
    // Peces y limones requieren concordancia sin alterar la mecánica.
    if (['peces','limones'].includes(object[1])) ui.board.firstChild.textContent = `¿Cuántos ${object[1]} hay?`;
    const grid = G.el('div', undefined, 'objetos-contar');
    for (let i = 0; i < count; i++) {
      const b = G.button(`${object[0]}${marked.has(i) ? ' ✓' : ''}`, () => {
        if (marked.has(i)) marked.delete(i); else marked.add(i);
        render(); ui.say(`Marcaste ${marked.size}. Puedes seguir contando.`);
      }, 'tarjeta objeto');
      b.setAttribute('aria-label', `Objeto ${i + 1}, ${marked.has(i) ? 'marcado' : 'sin marcar'}`);
      b.setAttribute('aria-pressed', String(marked.has(i))); grid.append(b);
    }
    ui.board.append(grid, G.el('p', 'Elige la cantidad:', 'texto-central'));
    const options = G.el('div', undefined, 'opciones');
    for (const number of G.shuffle([count - 1, count, count + 1])) {
      const b = G.button(String(number), () => {
        if (number !== count) { ui.say('Puedes contarlos otra vez, marcando uno por uno.'); return; }
        done = true; render(); ui.say(`¡Hay ${count} ${object[1]}!`, true);
      }); b.disabled = done; options.append(b);
    }
    ui.board.append(options);
    ui.controls.append(G.button('Contar un objeto conmigo', () => {
      const next = Array.from({ length: count }, (_, i) => i).find(i => !marked.has(i));
      if (next !== undefined) marked.add(next);
      render(); ui.say(next === undefined ? `Ya marcaste todos: hay ${count}.` : `${marked.size}. Marcamos un objeto más.`);
    }, 'boton-grande secundario'));
  }
  round();
})();
