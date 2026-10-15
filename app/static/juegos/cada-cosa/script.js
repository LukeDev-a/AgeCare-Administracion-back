(function () {
  'use strict';
  const G = AgecareGames;
  const groups = [
    { name: 'Cocina', items: [['🥄','Cuchara'],['🍳','Sartén'],['🍽️','Plato'],['🫖','Tetera']] },
    { name: 'Ropa', items: [['🧣','Bufanda'],['🧦','Calcetines'],['👕','Camisa'],['🧥','Abrigo']] },
    { name: 'Herramientas', items: [['🔨','Martillo'],['🪛','Destornillador'],['🔧','Llave inglesa'],['🪚','Sierra']] },
    { name: 'Frutas', items: [['🍎','Manzana'],['🍐','Pera'],['🍇','Uvas'],['🍊','Naranja']] },
    { name: 'Instrumentos musicales', items: [['🎸','Guitarra'],['🎺','Trompeta'],['🥁','Tambor'],['🎻','Violín']] }
  ];
  const nextGroup = G.deck(groups);
  let categories, items, position;
  const ui = G.boot('Mira el objeto y toca el grupo al que pertenece. Puedes pedir una pista.', round);
  function round() {
    categories = [nextGroup(), nextGroup(), nextGroup()];
    // Al renovar el mazo, evitar que una categoría aparezca dos veces en la misma ronda.
    categories = [...new Set(categories)];
    for (const group of G.shuffle(groups)) if (categories.length < 3 && !categories.includes(group)) categories.push(group);
    items = G.shuffle(categories.flatMap(group => G.shuffle(group.items).slice(0, 3).map(item => ({ icon: item[0], name: item[1], group: group.name }))));
    position = 0; ui.say(''); render();
  }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    if (position === items.length) { ui.board.append(G.el('p', '¡Todos los objetos están en su grupo!', 'texto-central')); ui.say('Completaste la ronda. Puedes jugar con otros objetos.', true); return; }
    const item = items[position];
    ui.board.append(G.el('p', `Objeto ${position + 1} de ${items.length}`, 'texto-central'));
    const card = G.el('div', undefined, 'destacado'); card.append(G.el('span', item.icon, 'icono'), G.el('h2', item.name)); ui.board.append(card);
    for (const group of categories) ui.controls.append(G.button(group.name, () => {
      if (group.name !== item.group) { ui.say('Puedes probar otro grupo. No hay apuro.'); return; }
      position++; render(); if (position < items.length) ui.say(`${item.name}: ${item.group}. ¡Bien! Ahora mira el siguiente objeto.`);
    }));
    ui.controls.append(G.button('Pista', () => ui.say(`${item.name} pertenece al grupo ${item.group}.`), 'boton-grande secundario'));
  }
  round();
})();
