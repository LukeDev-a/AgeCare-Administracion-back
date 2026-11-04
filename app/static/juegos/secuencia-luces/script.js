(function () {
  'use strict';
  const G = AgecareGames, X = AgecareExtra, labels = ['● Círculo', '▲ Triángulo', '■ Cuadrado', '★ Estrella'];
  let sequence, step, answers, watching, done, length = 3;
  const ui = G.boot('Observa las figuras que se iluminan, una por una. Pulsa «Siguiente luz» a tu ritmo. Después repite el orden tocando las figuras.', round);
  function round() { sequence = X.sequence(length); replay(); }
  function replay() { step = 0; answers = []; watching = true; done = false; render(); ui.say(`Primera figura: ${labels[sequence[0]]}. Avanza cuando la hayas observado.`); }
  function answer(value) {
    if (watching || done) return;
    if (sequence[answers.length] !== value) { ui.say('Esa figura no es la siguiente. Puedes intentarlo otra vez o volver a mirar la secuencia.'); return; }
    answers.push(value); done = answers.length === sequence.length; render(); ui.say(done ? '¡Repetiste toda la secuencia!' : `Bien. Llevas ${answers.length} de ${length}. ¿Qué figura sigue?`, done);
  }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    ui.board.append(G.el('p', watching ? `Observa: paso ${step + 1} de ${length}` : `Tu turno: ${answers.length} de ${length}`, 'resumen-extra'));
    const grid = G.el('div', undefined, 'luces-extra');
    labels.forEach((label, index) => { const lit = watching && sequence[step] === index; const b = G.button(label, () => answer(index), 'luz-extra' + (lit ? ' encendida' : '')); b.setAttribute('aria-label', label + (lit ? ', iluminada' : '')); b.disabled = watching || done; grid.append(b); }); ui.board.append(grid);
    if (watching) ui.controls.append(G.button(step < length - 1 ? 'Siguiente luz' : 'Estoy listo para repetir', () => {
      if (step < length - 1) { step++; render(); ui.say(`Paso ${step + 1}: ${labels[sequence[step]]}.`); }
      else { watching = false; render(); ui.say('Ahora toca las figuras en el mismo orden.'); }
    }));
    ui.controls.append(G.button('Ver la secuencia otra vez', replay, 'boton-grande secundario'));
    for (const n of [2, 3, 4, 5]) { const b = G.button(`${n} pasos`, () => { length = n; round(); }, 'boton-grande secundario'); b.setAttribute('aria-pressed', String(length === n)); ui.controls.append(b); }
  }
  round();
})();
