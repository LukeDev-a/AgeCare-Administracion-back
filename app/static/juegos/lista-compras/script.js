(function () {
  'use strict';
  const G = AgecareGames;
  const products = [['🍎','Manzanas'],['🍌','Plátanos'],['🍞','Pan'],['🥛','Leche'],['🥚','Huevos'],['🧀','Queso'],
    ['🥕','Zanahorias'],['🍅','Tomates'],['🥔','Papas'],['🐟','Pescado'],['🍚','Arroz'],['🍐','Peras'],['🍊','Naranjas'],['🧅','Cebollas'],['🥬','Lechuga']];
  let list, choices, found, visible, last = '';
  const ui = G.boot('Observa los tres productos. Cuando quieras, oculta la lista y búscalos. Puedes volver a consultarla.', round);
  function round() {
    list = G.shuffle(products).slice(0, 3);
    if (list.map(p => p[1]).sort().join() === last) {
      list[2] = G.shuffle(products.filter(p => !list.includes(p)))[0];
    }
    last = list.map(p => p[1]).sort().join();
    choices = G.shuffle([...list, ...G.shuffle(products.filter(p => !list.includes(p))).slice(0, 5)]);
    found = new Set(); visible = true; ui.say(''); render();
  }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    if (visible) {
      ui.board.append(G.el('h2', 'Tu lista de compras', 'texto-central'));
      const ul = G.el('ul', undefined, 'lista-productos');
      for (const product of list) ul.append(G.el('li', product.join(' ')));
      ui.board.append(ul);
      ui.controls.append(G.button('Ya vi la lista: buscar productos', () => { visible = false; render(); ui.say('Toca los productos que estaban en la lista.'); }));
      return;
    }
    ui.board.append(G.el('p', `${found.size} de ${list.length} productos encontrados`, 'texto-central'));
    const grid = G.el('div', undefined, 'rejilla');
    for (const product of choices) {
      const b = G.button('', () => {
        if (!list.includes(product)) { ui.say('Ese producto no estaba en la lista. Puedes consultarla otra vez.'); return; }
        found.add(product); render();
        ui.say(found.size === list.length ? '¡Encontraste toda tu lista de compras!' : '¡Ese producto sí estaba! Continúa cuando quieras.', found.size === list.length);
      }, 'tarjeta');
      b.append(G.el('span', product[0], 'icono'), G.el('span', product[1]));
      b.disabled = found.has(product); b.setAttribute('aria-pressed', String(found.has(product))); grid.append(b);
    }
    ui.board.append(grid);
    ui.controls.append(G.button('Volver a ver la lista', () => { visible = true; render(); ui.say('Puedes mirar la lista todo el tiempo que necesites.'); }, 'boton-grande secundario'));
  }
  round();
})();
