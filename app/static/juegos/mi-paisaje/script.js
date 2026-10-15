(function () {
  'use strict';
  const G = AgecareGames;
  const themes = [
    { name: 'Parque', key: 'parque', objects: [['🌳','Árbol'],['🌷','Flores'],['🪑','Asiento'],['🐦','Pájaro'],['⛲','Fuente'],['🌼','Margaritas'],['🏡','Casa'],['🦋','Mariposa']] },
    { name: 'Playa', key: 'playa', objects: [['🌴','Palmera'],['⛱️','Sombrilla'],['🐚','Concha'],['⛵','Velero'],['🦀','Cangrejo'],['🏖️','Reposera'],['🐦','Pájaro'],['🌞','Sol']] },
    { name: 'Campo', key: 'campo', objects: [['🏡','Casa'],['🌳','Árbol'],['🐑','Oveja'],['🐄','Vaca'],['🌻','Girasol'],['🚜','Tractor'],['🐓','Gallo'],['🌾','Trigo']] }
  ];
  const nextTheme = G.deck(themes);
  let theme, selected, cells, history;
  const ui = G.boot('Elige un elemento y toca un espacio del paisaje para colocarlo. Puedes reemplazarlo o deshacer. Aquí no hay respuestas incorrectas.', round);
  function round() { theme = nextTheme(); selected = theme.objects[0]; cells = Array(12).fill(null); history = []; ui.say(`Un nuevo paisaje de ${theme.name.toLowerCase()}. Puedes decorarlo como prefieras.`); render(); }
  function place(index) {
    history.push(cells.slice()); if (history.length > 50) history.shift();
    cells[index] = selected; render(); ui.say(`${selected ? selected[1] + ' colocado' : 'Espacio vacío'} en fila ${Math.floor(index / 4) + 1}, columna ${index % 4 + 1}.`);
  }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    ui.board.append(G.el('h2', `Tu paisaje: ${theme.name}`, 'texto-central'));
    const landscape = G.el('div', undefined, `paisaje ${theme.key}`); landscape.setAttribute('aria-label', `Paisaje de ${theme.name}`);
    cells.forEach((object, index) => {
      const b = G.button(object ? object[0] : '+', () => place(index), 'espacio-paisaje');
      b.setAttribute('aria-label', `Fila ${Math.floor(index / 4) + 1}, columna ${index % 4 + 1}: ${object ? object[1] : 'espacio libre'}`);
      landscape.append(b);
    }); ui.board.append(landscape, G.el('p', `Seleccionado: ${selected ? selected[1] : 'Borrador'}`, 'texto-central'));
    const palette = G.el('div', undefined, 'paleta');
    for (const object of [...theme.objects, null]) {
      const b = G.button(object ? object.join(' ') : 'Borrar un elemento', () => { selected = object; render(); ui.say(`Seleccionaste ${object ? object[1] : 'el borrador'}. Toca un espacio del paisaje.`); }, 'tarjeta');
      b.setAttribute('aria-pressed', String(selected === object)); palette.append(b);
    } ui.board.append(palette);
    const undo = G.button('Deshacer último cambio', () => { cells = history.pop(); render(); ui.say('Se deshizo el último cambio.'); }, 'boton-grande secundario');
    undo.disabled = !history.length; ui.controls.append(undo);
  }
  round();
})();
