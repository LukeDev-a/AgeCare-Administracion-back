(function () {
  'use strict';
  const G=AgecareGames,X=AgecareExtra, symbols=['☀ Sol','☾ Luna','♣ Trébol','★ Estrella','♥ Corazón','◆ Rombo'];
  let secret,guess,history,done,previous='';
  const ui=G.boot('Descubre tres figuras distintas y su orden. Elige tres figuras y comprueba. Las pistas indican cuántas están en el lugar correcto y cuántas pertenecen al código, pero están en otro lugar. No hay límite de intentos.',round);
  function round(){do{secret=X.shuffled([0,1,2,3,4,5]).slice(0,3);}while(String(secret)===previous);previous=String(secret);guess=[];history=[];done=false;render();ui.say('Elige la primera figura de tu intento.');}
  function render(){
    ui.board.replaceChildren();ui.controls.replaceChildren();
    const slots=G.el('div',undefined,'codigo-extra');
    for(let i=0;i<3;i++){const slot=G.el('span',guess[i]===undefined?'?':symbols[guess[i]],'hueco-extra');slot.setAttribute('aria-label',`Lugar ${i+1}: ${guess[i]===undefined?'sin elegir':symbols[guess[i]]}`);slots.append(slot);}ui.board.append(slots);
    const options=G.el('div',undefined,'opciones');symbols.forEach((symbol,index)=>{const b=G.button(symbol,()=>{guess.push(index);render();ui.say(`Elegiste ${symbol}. ${guess.length<3?'Elige la siguiente figura.':'Ya puedes comprobar.'}`);},'tarjeta');b.disabled=done||guess.includes(index)||guess.length===3;options.append(b);});ui.board.append(options);
    const list=G.el('ol',undefined,'intentos-extra');history.forEach(h=>list.append(G.el('li',`${h.guess.map(i=>symbols[i]).join(' · ')}. Lugar correcto: ${h.exact}. En otro lugar: ${h.present}.`)));ui.board.append(list);
    const check=G.button('Comprobar combinación',()=>{const result=X.codeScore(secret,guess);history.push({guess:guess.slice(),...result});done=result.exact===3;guess=[];render();ui.say(done?'¡Descubriste el código secreto!':`Lugar correcto: ${result.exact}. En otro lugar: ${result.present}. Usa las pistas para tu siguiente intento.`,done);});check.disabled=done||guess.length!==3;
    const remove=G.button('Borrar última figura',()=>{guess.pop();render();ui.say('Puedes elegir otra figura.');},'boton-grande secundario');remove.disabled=done||!guess.length;
    const hint=G.button('Revelar primera figura',()=>ui.say(`La primera figura del código es ${symbols[secret[0]]}.`),'boton-grande secundario');hint.disabled=done;ui.controls.append(check,remove,hint);
  }
  round();
})();
