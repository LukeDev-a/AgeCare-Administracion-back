(function () {
  'use strict';
  const G=AgecareGames,X=AgecareExtra;
  let target,opened,done,previous=-1;
  const ui=G.boot('Hay un tesoro en una de las 16 casillas. Toca una para explorar. El número indica cuántos pasos horizontales o verticales te separan del tesoro. No se cuentan diagonales.',round);
  function round(){target=X.shuffled(Array.from({length:16},(_,i)=>i).filter(i=>i!==previous))[0];previous=target;opened=new Set();done=false;render();ui.say('Elige cualquier casilla. Un número más pequeño significa que estás más cerca.');}
  function explore(index){opened.add(index);done=index===target;render();ui.say(done?'¡Encontraste el tesoro!':`Fila ${Math.floor(index/4)+1}, columna ${index%4+1}: a ${X.distance(index,target)} pasos del tesoro. Sigue buscando sin prisa.`,done);}
  function render(){
    ui.board.replaceChildren();ui.controls.replaceChildren();
    const grid=G.el('div',undefined,'cuadricula-cuatro');
    for(let i=0;i<16;i++){const seen=opened.has(i),distance=X.distance(i,target),label=seen?(i===target?'★':String(distance)):'?';const b=G.button(label,()=>explore(i),'casilla-extra'+(seen?' fija':''));b.setAttribute('aria-label',`Fila ${Math.floor(i/4)+1}, columna ${i%4+1}: ${seen?(i===target?'tesoro':`a ${distance} pasos`):'sin explorar'}`);b.disabled=seen||done;grid.append(b);}
    ui.board.append(grid,G.el('p',`Casillas exploradas: ${opened.size} de 16`,'resumen-extra'));
    const hint=G.button('Pista de la fila',()=>ui.say(`El tesoro está en la fila ${Math.floor(target/4)+1}. Usa las distancias para elegir su columna.`),'boton-grande secundario');hint.disabled=done;ui.controls.append(hint);
  }
  round();
})();
