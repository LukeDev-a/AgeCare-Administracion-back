(function () {
  'use strict';
  const G = AgecareGames;
  const words = [
    ['🍅','TOMATE',['TO','MA','TE']],['👕','CAMISA',['CA','MI','SA']],['👟','ZAPATO',['ZA','PA','TO']],
    ['🦋','MARIPOSA',['MA','RI','PO','SA']],['🐘','ELEFANTE',['E','LE','FAN','TE']],['🍌','PLÁTANO',['PLÁ','TA','NO']],
    ['🪟','VENTANA',['VEN','TA','NA']],['🥄','CUCHARA',['CU','CHA','RA']],['🐢','TORTUGA',['TOR','TU','GA']],
    ['🚲','BICICLETA',['BI','CI','CLE','TA']],['🌼','MARGARITA',['MAR','GA','RI','TA']],['🧅','CEBOLLA',['CE','BO','LLA']],
    ['🎸','GUITARRA',['GUI','TA','RRA']],['🍎','MANZANA',['MAN','ZA','NA']],['📞','TELÉFONO',['TE','LÉ','FO','NO']],
    ['🦒','JIRAFA',['JI','RA','FA']],['🐰','CONEJO',['CO','NE','JO']],['🍍','PIÑA',['PI','ÑA']]
  ];
  const next = G.deck(words);
  let word, tiles, used;
  const ui = G.boot('Construye la palabra tocando las sílabas en orden. Puedes deshacer o pedir una pista.', round);
  function round() { word = next(); tiles = G.shuffle(word[2].map((text, id) => ({ text, id }))); used = []; ui.say(''); render(); }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    const icon = G.el('p', word[0], 'palabra-icono'); icon.setAttribute('aria-label', 'Imagen de la palabra; usa Pista si necesitas su nombre'); ui.board.append(icon);
    ui.board.append(G.el('p', used.length === word[2].length ? word[1] : word[2].map((_, i) => i < used.length ? word[2][i] : '___').join(' · '), 'texto-central'));
    const group = G.el('div', undefined, 'opciones');
    for (const tile of tiles) {
      const b = G.button(tile.text, () => {
        if (tile.text !== word[2][used.length]) { ui.say('Prueba otra sílaba. Puedes usar Pista para ver cómo empieza.'); return; }
        used.push(tile.id); render();
        ui.say(used.length === word[2].length ? `¡Formaste ${word[1]}!` : 'Bien. Busca la siguiente sílaba.', used.length === word[2].length);
      });
      b.disabled = used.includes(tile.id) || used.length === word[2].length;
      group.append(b);
    }
    ui.board.append(group);
    const undo = G.button('Deshacer última sílaba', () => { used.pop(); render(); ui.say('Puedes elegir nuevamente.'); }, 'boton-grande secundario');
    undo.disabled = !used.length;
    ui.controls.append(undo, G.button('Pista', () => ui.say(`La palabra es ${word[1]}. ${used.length < word[2].length ? 'La siguiente sílaba es ' + word[2][used.length] + '.' : 'Ya la completaste.'}`), 'boton-grande secundario'));
  }
  round();
})();
