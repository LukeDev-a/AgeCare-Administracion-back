(function () {
  'use strict';
  const G = AgecareGames, X = AgecareExtra;
  const drawings = [
    ['una casa', [[20,45],[50,15],[80,45],[80,80],[20,80]]],
    ['un barco', [[15,60],[50,15],[85,60],[70,85],[30,85]]],
    ['un árbol', [[50,12],[82,62],[60,62],[60,88],[40,88],[40,62],[18,62]]],
    ['una cometa', [[50,12],[80,45],[50,78],[20,45]]],
    ['una montaña', [[12,80],[35,28],[50,56],[68,15],[88,80]]],
    ['una estrella', [[50,10],[61,35],[88,35],[67,53],[76,82],[50,65],[24,82],[33,53],[12,35],[39,35]]]
  ];
  const next = G.deck(drawings); let drawing, points, progress, hint;
  const ui = G.boot('Toca los números en orden, empezando por el 1. Las líneas irán formando un dibujo. No es necesario arrastrar.', round);
  function round() {
    drawing = next(); progress = 0; hint = false;
    points = drawing[1].map(p => p.slice());
    render(); ui.say('Busca el número 1 para comenzar.');
  }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    const area = G.el('div', undefined, 'puntos-extra'), svg = X.svg('svg', { viewBox:'0 0 100 100', 'aria-hidden':'true' });
    const line = points.slice(0,progress);
    if (progress === points.length) line.push(points[0]);
    if (progress > 1) svg.append(X.svg('polyline', { points: line.map(p=>p.join(',')).join(' '), fill:'none', stroke:'#24638b', 'stroke-width':1.5, 'stroke-linejoin':'round' })); area.append(svg);
    points.forEach(([x,y], index) => {
      const b = G.button(String(index + 1), () => {
        if (index !== progress) { ui.say(`Ahora buscamos el número ${progress + 1}.`); return; }
        progress++; hint = false; render(); ui.say(progress === points.length ? `¡Descubriste ${drawing[0]}!` : `Bien. Busca el número ${progress + 1}.`, progress === points.length);
      }, 'punto-extra' + (hint && index === progress ? ' pista' : ''));
      b.style.left = `${x}%`; b.style.top = `${y}%`; b.disabled = index < progress; b.setAttribute('aria-label', `Punto ${index + 1}${index < progress ? ', unido' : ''}`); area.append(b);
    });
    ui.board.append(area, G.el('p', `Puntos unidos: ${progress} de ${points.length}`, 'resumen-extra'));
    const help = G.button('Señalar el siguiente punto', () => { hint = true; render(); ui.say(`Busca el punto ${progress + 1}, marcado con un borde grueso.`); }, 'boton-grande secundario'); help.disabled = progress === points.length; ui.controls.append(help);
  }
  round();
})();
