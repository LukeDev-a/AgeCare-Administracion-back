(function () {
  'use strict';
  const G = AgecareGames;
  let chain, hand, selected, lastSignature = '';
  const ui = G.boot('Toca una ficha y después el extremo de la mesa donde quieres colocarla. Los números deben coincidir.', round);
  function round() {
    let next;
    for (let i = 0; i < 10; i++) {
      next = G.domino();
      if (JSON.stringify(next) !== lastSignature) break;
    }
    lastSignature = JSON.stringify(next); chain = next.initial; hand = next.hand; selected = null;
    ui.say(''); render();
  }
  function place(side) {
    if (selected === null) { ui.say('Primero selecciona una ficha de tu mano.'); return; }
    const next = G.attach(chain, hand[selected], side);
    if (!next) { ui.say('Ese extremo necesita otro número. Puedes probar en el otro extremo o pedir una pista.'); return; }
    chain = next; hand.splice(selected, 1); selected = null; render();
    ui.say(hand.length ? 'Ficha colocada. Continúa con otra de tu mano.' : '¡Completaste la mesa de dominó!', !hand.length);
  }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    ui.board.append(G.el('p', `Extremo izquierdo: ${chain[0]} · Extremo derecho: ${chain[chain.length - 1]}`, 'destacado'));
    const table = G.el('div', undefined, 'texto-central'); table.setAttribute('aria-label', 'Cadena de números en la mesa');
    for (const number of chain) table.append(G.el('span', String(number), 'pieza'));
    ui.board.append(table, G.el('h2', `Tus fichas (${hand.length})`, 'texto-central'));
    const choices = G.el('div', undefined, 'fichas');
    hand.forEach((tile, index) => {
      const b = G.button(`${tile[0]} | ${tile[1]}`, () => { selected = index; render(); ui.say(`Ficha ${tile[0]} y ${tile[1]} seleccionada. Elige un extremo.`); }, 'tarjeta');
      b.setAttribute('aria-label', `Ficha ${tile[0]} y ${tile[1]}`); b.setAttribute('aria-pressed', String(selected === index)); choices.append(b);
    });
    ui.board.append(choices);
    if (hand.length) {
      ui.controls.append(G.button('Colocar a la izquierda', () => place('left')),
        G.button('Colocar a la derecha', () => place('right')),
        G.button('Pista', () => {
          const index = hand.findIndex(tile => tile.includes(chain[0]) || tile.includes(chain[chain.length - 1]));
          if (index < 0) { ui.say('Esta combinación quedó sin movimiento. Puedes empezar una ronda nueva, sin penalización.'); return; }
          selected = index; render(); ui.say(`Prueba la ficha ${hand[index][0]} y ${hand[index][1]} en el extremo ${hand[index].includes(chain[0]) ? 'izquierdo' : 'derecho'}.`);
        }, 'boton-grande secundario'));
    }
  }
  round();
})();
