(function () {
  'use strict';
  const G = AgecareGames, X = AgecareExtra;
  let puzzle, cells, mode, done;
  const ui = G.boot('Los números junto a cada fila y columna indican grupos de casillas pintadas. Entre dos grupos deja al menos una vacía. Por ejemplo, «2 1» significa dos pintadas juntas, un espacio y otra pintada. El 0 indica que no se pinta ninguna.', round);
  function round() { puzzle = X.nonogram(); cells = Array(25).fill(0); mode = 1; done = false; render(); ui.say('Selecciona «Pintar» o «Marcar vacío». Tocar de nuevo una marca del mismo tipo la borra. Las cruces son una ayuda, no son obligatorias.'); }
  function render() {
    ui.board.replaceChildren(); ui.controls.replaceChildren();
    const area = G.el('div', undefined, 'zona-nonograma'), grid = G.el('div', undefined, 'nonograma-extra'); grid.append(G.el('span'));
    puzzle.cols.forEach((clue,c) => { const label = G.el('span',clue.join('\n'),'pista-columna'); label.setAttribute('aria-label', `Columna ${c+1}: grupos ${clue.join(' y ')}`); grid.append(label); });
    for (let r=0;r<5;r++) {
      const label = G.el('span',puzzle.rows[r].join(' '),'pista-fila'); label.setAttribute('aria-label',`Fila ${r+1}: grupos ${puzzle.rows[r].join(' y ')}`); grid.append(label);
      for (let c=0;c<5;c++) {
        const i=r*5+c, b=G.button(cells[i]===2 ? '×' : cells[i]===1 ? '●' : '·',()=>{ cells[i]=cells[i]===mode ? 0 : mode; render(); },'casilla-extra'+(cells[i]===1?' pintada':''));
        b.setAttribute('aria-label',`Fila ${r+1}, columna ${c+1}: ${cells[i]===1?'pintada':cells[i]===2?'marcada vacía':'sin marcar'}`); b.disabled=done; grid.append(b);
      }
    } area.append(grid); ui.board.append(area);
    for (const [label,value] of [['Pintar',1],['Marcar vacío',2]]) { const b=G.button(label,()=>{mode=value;render();ui.say(`Modo: ${label.toLowerCase()}.`);},'boton-grande secundario'); b.setAttribute('aria-pressed',String(mode===value)); b.disabled=done; ui.controls.append(b); }
    const check=G.button('Comprobar dibujo',()=>{
      const actual=X.clues(cells.map(v=>v===1)); done=JSON.stringify(actual.rows)===JSON.stringify(puzzle.rows)&&JSON.stringify(actual.cols)===JSON.stringify(puzzle.cols);
      render();ui.say(done?'¡Todas las filas y columnas coinciden! Completaste el dibujo.':'Todavía hay grupos que no coinciden con sus números. Puedes corregir marcas o completar una casilla con la ayuda.',done);
    });check.disabled=done;
    const hint=G.button('Ayuda con una casilla',()=>{
      const i=cells.findIndex((v,j)=>puzzle.board[j]?v!==1:v===1||v===0);
      if(i<0){ui.say('Las casillas ya coinciden. Pulsa «Comprobar dibujo».');return;}
      cells[i]=puzzle.board[i]?1:2;render();ui.say(`Fila ${Math.floor(i/5)+1}, columna ${i%5+1}: ${puzzle.board[i]?'se pinta':'queda vacía'}.`);
    },'boton-grande secundario');hint.disabled=done;ui.controls.append(check,hint);
  }
  round();
})();
