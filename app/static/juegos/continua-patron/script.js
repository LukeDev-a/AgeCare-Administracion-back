(function () {
  'use strict';
  const G = AgecareGames;
  const shapes = [['●','Círculo'],['▲','Triángulo'],['■','Cuadrado'],['★','Estrella'],['◆','Rombo']];
  const nextRule = G.deck([[0,1],[0,0,1],[0,1,1],[0,1,2],[0,0,1,1],[0,1,2,1]]);
  let rule, symbols, answer, done;
  const ui = G.boot('Mira cómo se repite la serie y elige la figura que sigue. Los nombres de las figuras también te ayudan.', round);
  function round() { rule = nextRule(); symbols = G.shuffle(shapes); answer = rule[0]; done = false; ui.say(''); render(); }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    const series = G.el('ol', undefined, 'serie'); series.setAttribute('aria-label', 'Serie de figuras en orden');
    for (let i = 0; i < rule.length * 2; i++) {
      const shape = symbols[rule[i % rule.length]];
      const cell = G.el('li', undefined, 'figura'); cell.append(G.el('span', shape[0], 'icono'), G.el('span', shape[1])); series.append(cell);
    }
    series.append(G.el('li', done ? symbols[answer][0] : '?', 'figura interrogacion')); ui.board.append(series);
    for (const shape of G.shuffle(symbols.slice(0, 3))) {
      const b = G.button(`${shape[0]} ${shape[1]}`, () => {
        if (shape !== symbols[answer]) { ui.say('Observa el grupo que se repite. Puedes pedir una pista.'); return; }
        done = true; render(); ui.say('¡Esa figura continúa el patrón!', true);
      }); b.disabled = done; ui.controls.append(b);
    }
    ui.controls.append(G.button('Pista', () => ui.say(`El grupo que se repite es: ${rule.map(i => symbols[i][1]).join(', ')}. Después empieza de nuevo.`), 'boton-grande secundario'));
  }
  round();
})();
