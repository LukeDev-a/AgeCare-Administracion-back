(function () {
  'use strict';
  const G = AgecareGames, X = AgecareExtra;
  let pins, aim, force, throws, last;
  const ui = G.boot('Ajusta la dirección y la fuerza con los botones. Luego lanza. Dispones de dos lanzamientos y no necesitas reaccionar rápido.', round);
  function round() { pins = X.pins(); aim = 0; force = 2; throws = 0; last = false; render(); ui.say('Elige hacia dónde quieres lanzar.'); }
  function fallen() { return pins.filter(p => p.down).length; }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    const done = throws >= 2 || fallen() === 10;
    ui.board.append(G.el('p', `Derribados: ${fallen()} de 10 · Lanzamientos: ${throws} de 2`, 'resumen-extra'));
    const svg = X.svg('svg', { viewBox: '0 0 300 330', class: 'diagrama-extra', role: 'img', 'aria-label': `Pista de bolos: ${10 - fallen()} siguen en pie. Dirección ${aim < 0 ? 'izquierda' : aim > 0 ? 'derecha' : 'centro'}, nivel ${Math.abs(aim)}.` });
    svg.append(X.svg('rect', { x: 20, y: 5, width: 260, height: 315, rx: 16, fill: '#f4e4bd', stroke: '#6e5229', 'stroke-width': 3 }),
      X.svg('line', { x1: 150, y1: 295, x2: 150 + aim * 18, y2: 70, stroke: '#185f97', 'stroke-width': 4, 'stroke-dasharray': '8 6' }));
    pins.forEach((p, i) => { svg.append(X.svg('circle', { cx: p.x, cy: p.y, r: 12, fill: p.down ? '#b3bfbd' : '#fff', stroke: '#304854', 'stroke-width': 2 }),
      X.svg('text', { x: p.x, y: p.y + 5, 'text-anchor': 'middle', 'font-size': 14, fill: '#203540' }, p.down ? '×' : i + 1)); });
    svg.append(X.svg('circle', { cx: last ? 150 + aim * 18 : 150, cy: last ? 190 : 295, r: 14, fill: '#185f97' })); ui.board.append(svg,
      G.el('p', `Dirección: ${aim === 0 ? 'centro' : `${Math.abs(aim)} a la ${aim < 0 ? 'izquierda' : 'derecha'}`} · Fuerza: ${['', 'suave', 'media', 'firme'][force]}`, 'resumen-extra'));
    for (const [label, action, disabled] of [
      ['Apuntar a la izquierda', () => { aim--; last = false; render(); }, aim <= -3],
      ['Apuntar a la derecha', () => { aim++; last = false; render(); }, aim >= 3],
      ['Menos fuerza', () => { force--; render(); }, force <= 1],
      ['Más fuerza', () => { force++; render(); }, force >= 3]]) {
      const b = G.button(label, action, 'boton-grande secundario'); b.disabled = done || disabled; ui.controls.append(b);
    }
    const launch = G.button('Lanzar pelota', () => { const before = fallen(); pins = X.bowl(pins, aim, force); throws++; last = true; render(); ui.say(fallen() === 10 ? '¡Derribaste todos los bolos!' : `Derribaste ${fallen() - before} en este lanzamiento. ${throws === 2 ? 'Puedes empezar otra ronda cuando quieras.' : 'Todavía tienes otro lanzamiento.'}`, fallen() === 10); }); launch.disabled = done; ui.controls.append(launch);
  }
  round();
})();
