const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../app/static/juegos');
const G = require(path.join(root, 'compartido/js/nuevos-core.js'));
const X = require(path.join(root, 'compartido/js/coleccion-core.js'));
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'coleccion.json'), 'utf8'));

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.attrs = {}; this.events = {}; this.style = {}; this.disabled = false; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  addEventListener(event, callback) { this.events[event] = callback; }
  click() { if (!this.disabled) this.events.click?.(); }
}
function walk(node) { return [node, ...node.children.flatMap(walk)]; }
function game(slug, seed = 125) {
  const nodes = Object.fromEntries(['tablero','controles','mensaje','instruccion','nueva'].map(id => [id, new Element('div')]));
  const math = Object.create(Math); math.random = G.seeded(seed);
  const document = { getElementById: id => nodes[id], createElement: tag => new Element(tag), createElementNS: (_,tag) => new Element(tag) };
  const scope = vm.createContext({ Math: math, document });
  for (const file of ['compartido/js/nuevos-core.js','compartido/js/coleccion-core.js',`${slug}/script.js`]) vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),scope);
  return { ...nodes,
    buttons: () => [...walk(nodes.tablero), ...walk(nodes.controles)].filter(n => n.tagName === 'button'),
    button(label) { return this.buttons().find(n => n.textContent === label); }
  };
}

test('200 sudokus son válidos, tienen solución única y presentan variaciones', () => {
  const signatures = new Set();
  for (let seed=1;seed<=200;seed++) {
    const puzzle=X.sudoku(G.seeded(seed)); signatures.add(String(puzzle.board));
    assert.equal(X.sudokuCount(puzzle.board),1);
    for (let i=0;i<4;i++) {
      assert.equal(new Set(puzzle.solution.slice(i*4,i*4+4)).size,4);
      assert.equal(new Set([0,1,2,3].map(r=>puzzle.solution[r*4+i])).size,4);
    }
    for (const [r,c] of [[0,0],[0,2],[2,0],[2,2]]) assert.equal(new Set([0,1,4,5].map(d=>puzzle.solution[r*4+c+d])).size,4);
    assert.ok(puzzle.board.filter(v=>!v).length >= 6);
  }
  assert.ok(signatures.size>150);
});

test('100 nonogramas tienen solución única y las pistas coinciden con el dibujo', () => {
  const signatures=new Set();
  for(let seed=1;seed<=100;seed++) {
    const puzzle=X.nonogram(G.seeded(seed)); signatures.add(String(puzzle.board));
    assert.equal(X.nonogramSolutions(puzzle),1);
    assert.deepEqual(X.clues(puzzle.board),{rows:puzzle.rows,cols:puzzle.cols});
  }
  assert.ok(signatures.size>70);
});

test('las pistas de Hanói resuelven estados legales de tres y cuatro discos', () => {
  for(const count of [3,4]) for(const goal of [1,2]) {
    const pegs=[Array.from({length:count},(_,i)=>count-i),[],[]]; let steps=0;
    while(pegs[goal].length<count) {
      const move=X.hanoiHint(pegs,goal);
      assert.ok(X.hanoiMoves(pegs).some(m=>String(m)===String(move)));
      pegs[move[1]].push(pegs[move[0]].pop()); assert.ok(++steps<=2**count-1);
    }
  }
});

test('100 balanzas siempre admiten una combinación exacta de las pesas ofrecidas', () => {
  for(let seed=1;seed<=100;seed++) {
    const {weights,target}=X.balance(G.seeded(seed));
    assert.equal(new Set(weights).size,6);
    assert.ok(Array.from({length:64},(_,mask)=>weights.reduce((sum,n,i)=>sum+((mask&(1<<i))?n:0),0)).includes(target));
  }
});

test('código secreto cuenta posiciones y figuras sin contar una figura dos veces', () => {
  assert.deepEqual(X.codeScore([0,1,2],[0,1,2]),{exact:3,present:0});
  assert.deepEqual(X.codeScore([0,1,2],[1,2,0]),{exact:0,present:3});
  assert.deepEqual(X.codeScore([0,1,2],[0,3,1]),{exact:1,present:1});
  assert.deepEqual(X.codeScore([0,1,2],[0,0,0]),{exact:1,present:0});
});

test('secuencias, distancias y bolos respetan sus reglas', () => {
  const signatures=new Set();
  for(let seed=1;seed<=100;seed++) {
    const sequence=X.sequence(5,G.seeded(seed)); signatures.add(String(sequence));
    assert.equal(sequence.length,5); assert.ok(sequence.every((n,i)=>n>=0&&n<4&&(!i||n!==sequence[i-1])));
    const pins=X.pins(G.seeded(seed)), once=X.bowl(pins,-1,3), twice=X.bowl(once,2,3);
    assert.equal(pins.length,10); assert.ok(once.every((p,i)=>!p.down||twice[i].down));
  }
  assert.ok(signatures.size>50);
  assert.equal(X.distance(0,15),6); assert.equal(X.distance(7,7),0); assert.equal(X.distance(3,4),4);
});

test('los diez juegos arrancan y admiten nuevas rondas sin red ni temporizadores', () => {
  assert.equal(catalog.length,10);
  for(const item of catalog) {
    const ui=game(item.slug);
    assert.ok(ui.tablero.children.length,item.slug); assert.ok(ui.instruccion.textContent.length>20,item.slug);
    ui.nueva.click(); assert.ok(ui.tablero.children.length,item.slug);
    assert.ok(fs.existsSync(path.join(root,item.slug,'juego.json')));
  }
});

test('sudoku, balanza, luces, nonograma y código se completan con sus controles', () => {
  const seed=125;
  const sudoku=game('sudoku',seed), solution=X.sudoku(G.seeded(seed)).solution;
  for(let i=0;i<16;i++) {
    const cell=sudoku.buttons().find(n=>n.attrs['aria-label']?.startsWith(`Fila ${Math.floor(i/4)+1}, columna ${i%4+1}:`));
    if(!cell.disabled) { cell.click(); walk(sudoku.controles).find(n=>n.tagName==='button'&&n.textContent===String(solution[i])).click(); }
  }
  assert.match(sudoku.mensaje.textContent,/Completaste/);
  const balance=game('balanza',seed), challenge=X.balance(G.seeded(seed));
  const mask=Array.from({length:64},(_,i)=>i).find(mask=>challenge.weights.reduce((sum,n,i)=>sum+((mask&(1<<i))?n:0),0)===challenge.target);
  challenge.weights.forEach((n,i)=>{if(mask&(1<<i))balance.button(`${n} unidades`).click();});
  balance.button('Comprobar equilibrio').click(); assert.match(balance.mensaje.textContent,/equilibrada/);
  const lights=game('secuencia-luces',seed), seq=X.sequence(3,G.seeded(seed));
  lights.button('Siguiente luz').click(); lights.button('Siguiente luz').click(); lights.button('Estoy listo para repetir').click();
  for(const index of seq) lights.button(['● Círculo','▲ Triángulo','■ Cuadrado','★ Estrella'][index]).click();
  assert.match(lights.mensaje.textContent,/toda la secuencia/);
  const drawing=game('dibujo-cuadricula',seed), pattern=X.nonogram(G.seeded(seed));
  pattern.board.forEach((fill,i)=>{if(fill)drawing.buttons().find(n=>n.attrs['aria-label']?.startsWith(`Fila ${Math.floor(i/5)+1}, columna ${i%5+1}:`)).click();});
  drawing.button('Comprobar dibujo').click(); assert.match(drawing.mensaje.textContent,/Completaste el dibujo/);
  const code=game('codigo-secreto',seed), secret=X.shuffled([0,1,2,3,4,5],G.seeded(seed)).slice(0,3);
  secret.forEach(i=>code.button(['☀ Sol','☾ Luna','♣ Trébol','★ Estrella','♥ Corazón','◆ Rombo'][i]).click());
  code.button('Comprobar combinación').click(); assert.match(code.mensaje.textContent,/Descubriste/);
});

test('Hanói permite deshacer y resolver usando pistas de movimientos legales', () => {
  const ui=game('torres-hanoi');
  const goal=Number(ui.tablero.textContent.match(/Destino: torre (\d)/)[1])-1;
  function state(){return ui.buttons().filter(n=>n.attrs['aria-label']?.startsWith('Torre ')).map(n=>{
    const list=n.attrs['aria-label'].split(': ')[1]; return list==='ninguno'?[]:list.split(', ').map(Number);
  });}
  let pegs=state(), move=X.hanoiHint(pegs,goal);
  const tower=i=>ui.buttons().find(n=>n.attrs['aria-label']?.startsWith(`Torre ${i+1}`));
  tower(move[0]).click(); tower(move[1]).click(); ui.button('Deshacer').click(); assert.deepEqual(state(),pegs);
  let steps=0;
  while(!ui.mensaje.textContent.includes('todos los discos')) {
    move=X.hanoiHint(state(),goal); tower(move[0]).click(); tower(move[1]).click(); assert.ok(++steps<=7);
  }
});

test('puntos, refranes, bolos y tesoro alcanzan el final y se reinician', () => {
  const dots=game('une-puntos');
  const count=dots.buttons().filter(n=>n.attrs['aria-label']?.startsWith('Punto ')).length;
  for(let n=1;n<=count;n++)dots.button(String(n)).click();
  assert.match(dots.mensaje.textContent,/Descubriste/);
  const proverb=game('refranes');
  for(const option of proverb.buttons().filter(n=>n.className==='boton-grande')) option.click();
  assert.match(proverb.mensaje.textContent,/Así es/);
  const bowling=game('bolos'); bowling.button('Lanzar pelota').click(); bowling.button('Lanzar pelota').click();
  assert.ok(bowling.button('Lanzar pelota').disabled);
  const treasure=game('tesoro');
  for(let i=0;i<16;i++) { const cell=treasure.buttons().find(n=>n.attrs['aria-label']?.startsWith(`Fila ${Math.floor(i/4)+1}, columna ${i%4+1}:`)); cell.click(); }
  assert.match(treasure.mensaje.textContent,/Encontraste/);
  for(const ui of [dots,proverb,bowling,treasure]){ui.nueva.click();assert.ok(ui.tablero.children.length);}
});
