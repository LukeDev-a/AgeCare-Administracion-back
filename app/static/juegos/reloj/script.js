(function () {
  'use strict';
  const G = AgecareGames;
  const nextHour = G.deck(Array.from({ length: 24 }, (_, i) => i * 30));
  let target, value, done;
  const ui = G.boot('Ajusta el reloj para que marque la hora indicada. Trabajamos con horas exactas y medias horas, sin prisa.', round);
  function label(minutes) { return `${Math.floor(minutes / 60) || 12}:${String(minutes % 60).padStart(2, '0')}`; }
  function round() {
    target = nextHour(); value = Math.floor(Math.random() * 24) * 30;
    if (value === target) value = (value + 60) % 720;
    done = false; ui.say(''); render();
  }
  function adjust(delta) { value = (value + delta + 720) % 720; render(); ui.say(`Tu reloj marca ${label(value)}.`); }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    ui.board.append(G.el('h2', `Hora que buscamos: ${label(target)}`, 'texto-central'));
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 300 300'); svg.setAttribute('class', 'reloj'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', `Tu reloj marca ${label(value)}`);
    function shape(tag, attrs, text) {
      const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
      for (const [key, val] of Object.entries(attrs)) node.setAttribute(key, val);
      if (text) node.textContent = text;
      svg.append(node); return node;
    }
    shape('circle', { cx: 150, cy: 150, r: 140, fill: '#fff', stroke: '#294252', 'stroke-width': 5 });
    for (let hour = 1; hour <= 12; hour++) {
      const angle = (hour * 30 - 90) * Math.PI / 180;
      shape('text', { x: 150 + 114 * Math.cos(angle), y: 150 + 114 * Math.sin(angle) + 8, 'text-anchor': 'middle', fill: '#263b45', 'font-size': 24 }, String(hour));
    }
    shape('line', { x1: 150, y1: 150, x2: 150, y2: 83, stroke: '#185fa5', 'stroke-width': 10, 'stroke-linecap': 'round', transform: `rotate(${value / 2} 150 150)` });
    shape('line', { x1: 150, y1: 150, x2: 150, y2: 49, stroke: '#8a4600', 'stroke-width': 6, 'stroke-linecap': 'round', transform: `rotate(${(value % 60) * 6} 150 150)` });
    shape('circle', { cx: 150, cy: 150, r: 7, fill: '#263b45' });
    ui.board.append(svg, G.el('p', `Tu reloj: ${label(value)}. Aguja corta: horas. Aguja larga: minutos.`, 'texto-central'));
    for (const [text, delta] of [['Hora −', -60], ['Hora +', 60], ['Minutos −30', -30], ['Minutos +30', 30]]) {
      const b = G.button(text, () => adjust(delta), 'boton-grande secundario'); b.disabled = done; ui.controls.append(b);
    }
    const check = G.button('Comprobar hora', () => {
      if (value !== target) { ui.say(`Tu reloj marca ${label(value)}. Buscamos ${label(target)}. Puedes seguir ajustándolo.`); return; }
      done = true; render(); ui.say('¡El reloj marca la hora indicada!', true);
    }); check.disabled = done;
    ui.controls.append(check, G.button('Pista', () => ui.say(`La hora es ${Math.floor(target / 60) || 12}. La aguja larga debe apuntar ${target % 60 ? 'al 6, porque son y media' : 'al 12, porque es en punto'}.`), 'boton-grande secundario'));
  }
  round();
})();
