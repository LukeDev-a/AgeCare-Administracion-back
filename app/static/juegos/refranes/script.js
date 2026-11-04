(function () {
  'use strict';
  const G = AgecareGames;
  const bank = [
    ['Al mal tiempo,', 'buena cara', 'paso lento', 'casa grande', 'Ante una dificultad, intenta mantener una actitud positiva.'],
    ['Más vale tarde', 'que nunca', 'que temprano', 'que ayer', 'Hacer algo con retraso puede ser mejor que no hacerlo.'],
    ['No hay mal que', 'por bien no venga', 'dure un minuto', 'se quede dormido', 'A veces una dificultad trae una oportunidad inesperada.'],
    ['Camarón que se duerme,', 'se lo lleva la corriente', 'encuentra la luna', 'se convierte en pez', 'Conviene estar atento a lo que ocurre.'],
    ['A caballo regalado,', 'no se le miran los dientes', 'se le cambia el nombre', 'se le busca un sombrero', 'Se agradece un regalo sin exigir que sea perfecto.'],
    ['En casa de herrero,', 'cuchillo de palo', 'cuchara de plata', 'sombrero de paja', 'A veces falta en casa aquello que se ofrece a los demás.'],
    ['El que mucho abarca,', 'poco aprieta', 'siempre termina', 'nunca descansa', 'Intentar demasiadas cosas puede dificultar hacerlas bien.'],
    ['Más vale pájaro en mano', 'que ciento volando', 'que uno cantando', 'que dos durmiendo', 'Algo seguro puede valer más que una posibilidad incierta.'],
    ['Dime con quién andas', 'y te diré quién eres', 'y te prestaré mis zapatos', 'y te contaré un cuento', 'Las compañías pueden influir en nuestros hábitos.'],
    ['A buen entendedor,', 'pocas palabras', 'muchos mapas', 'largos caminos', 'Una explicación breve puede ser suficiente.'],
    ['No dejes para mañana', 'lo que puedes hacer hoy', 'lo que ya pasó ayer', 'la lluvia del invierno', 'Si puedes resolver algo ahora, evita posponerlo.'],
    ['Perro que ladra', 'no muerde', 'siempre corre', 'no duerme', 'Quien amenaza mucho no siempre lleva su amenaza a la práctica.'],
    ['De tal palo,', 'tal astilla', 'tal montaña', 'tal sombrero', 'Se usa para señalar semejanzas entre personas de una familia.'],
    ['Quien tiene boca', 'se equivoca', 'siempre gana', 'se desvela', 'Equivocarse al hablar es algo normal.'],
    ['No todo lo que brilla', 'es oro', 'es luna', 'es verano', 'Las apariencias pueden engañar.'],
    ['El hábito', 'no hace al monje', 'no abre la puerta', 'no cambia de color', 'La apariencia no demuestra por sí sola cómo es alguien.'],
    ['Después de la tormenta', 'viene la calma', 'viene la nieve', 'sale otro camino', 'Los momentos difíciles pueden pasar.'],
    ['A falta de pan,', 'buenas son tortas', 'sobran las ventanas', 'llega el otoño', 'Podemos aprovechar una alternativa cuando falta lo que buscábamos.'],
    ['Barriga llena,', 'corazón contento', 'zapato nuevo', 'camino corto', 'Disfrutar una comida suele dar satisfacción.'],
    ['Cuando el río suena,', 'agua lleva', 'la luna sale', 'el viento duerme', 'Se usa cuando se sospecha que algo tiene una causa detrás.']
  ];
  const next = G.deck(bank); let question, done;
  const ui = G.boot('Lee el comienzo del refrán y elige cómo termina. Si no lo conoces, puedes pedir una pista y probar sin prisa.', round);
  function round() {
    question = next(); done = false; ui.clear();
    ui.board.append(G.el('h2', `${question[0]}…`, 'texto-central'));
    const choices = G.el('div', undefined, 'opciones');
    G.shuffle(question.slice(1,4)).forEach(option => {
      const b = G.button(option, () => {
        if (done) return;
        if (option !== question[1]) { ui.say('Esa no es la terminación habitual. Prueba otra opción o pide una pista.'); return; }
        done = true; for (const button of choices.children) button.disabled = true;
        ui.say(`¡Así es! ${question[0]} ${question[1]}. ${question[4]}`, true);
      }); choices.append(b);
    }); ui.board.append(choices);
    ui.controls.append(G.button('Pista', () => ui.say(`La respuesta comienza con «${question[1].split(' ')[0]}».`), 'boton-grande secundario'));
  }
  round();
})();
