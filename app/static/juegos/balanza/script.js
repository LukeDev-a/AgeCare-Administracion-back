(function () {
  'use strict';
  const G = AgecareGames, X = AgecareExtra;
  let challenge, selected, done;
  const ui = G.boot('El lado izquierdo tiene un peso fijo. Toca las pesas para añadirlas o quitarlas del lado derecho y busca el mismo total.', round);
  function round() { challenge = X.balance(); selected = new Set(); done = false; render(); ui.say('Puedes combinar varias pesas. No hay límite de intentos.'); }
  function total() { return [...selected].reduce((sum, i) => sum + challenge.weights[i], 0); }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    const amount = total(), slope = Math.max(-18, Math.min(18, (amount - challenge.target) * 2));
    const svg = X.svg('svg', { viewBox: '0 0 300 180', class: 'diagrama-extra', role: 'img', 'aria-label': `Balanza: izquierda ${challenge.target}, derecha ${amount} unidades` });
    svg.append(X.svg('path', { d: 'M120 165 L150 80 L180 165 Z', fill: '#6f8794' }));
    const beam = X.svg('g', { transform: `rotate(${slope} 150 75)` });
    beam.append(X.svg('line', { x1: 40, y1: 75, x2: 260, y2: 75, stroke: '#233b46', 'stroke-width': 7 }));
    for (const [x, value] of [[55, challenge.target], [245, amount]]) {
      beam.append(X.svg('line', { x1: x, y1: 75, x2: x, y2: 112, stroke: '#233b46', 'stroke-width': 3 }),
        X.svg('path', { d: `M${x - 35} 112 Q${x} 160 ${x + 35} 112 Z`, fill: '#d1e8f5', stroke: '#233b46', 'stroke-width': 2 }),
        X.svg('text', { x, y: 105, 'text-anchor': 'middle', 'font-size': 21, fill: '#233b46' }, value));
    } svg.append(beam); ui.board.append(svg, G.el('p', `Buscamos ${challenge.target} · Tus pesas suman ${amount}`, 'resumen-extra'));
    const choices = G.el('div', undefined, 'opciones');
    challenge.weights.forEach((weight, index) => { const b = G.button(`${weight} unidades`, () => { selected.has(index) ? selected.delete(index) : selected.add(index); render(); }, 'tarjeta'); b.setAttribute('aria-pressed', String(selected.has(index))); b.disabled = done; choices.append(b); });
    ui.board.append(choices);
    const check = G.button('Comprobar equilibrio', () => { done = total() === challenge.target; render(); ui.say(done ? '¡La balanza está equilibrada!' : total() < challenge.target ? `Faltan ${challenge.target - total()} unidades. Puedes añadir o cambiar pesas.` : `Sobran ${total() - challenge.target} unidades. Puedes quitar o cambiar pesas.`, done); }); check.disabled = done;
    ui.controls.append(check, G.button('Pista', () => ui.say(`Hay una solución combinando ${challenge.target === challenge.weights[0] + challenge.weights[1] ? 'dos' : 'tres'} pesas. Puedes probar otra combinación que sume lo mismo.`), 'boton-grande secundario'));
  }
  round();
})();
