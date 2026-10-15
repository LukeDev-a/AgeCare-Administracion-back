const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../app/static/juegos');
const core = require(path.join(root, 'compartido/js/nuevos-core.js'));
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'nuevos.json'), 'utf8'));

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.attrs = {}; this.events = {}; this.disabled = false; this._text = ''; this.classes = new Set(); this.classList = { add: value => this.classes.add(value), contains: value => this.classes.has(value) }; }
  set className(value) { this.classes = new Set(value.split(' ')); }
  get className() { return [...this.classes].join(' '); }
  set textContent(value) { this._text = value; this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  get firstChild() { return this.children[0]; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
  setAttribute(key, value) { this.attrs[key] = value; }
  addEventListener(event, action) { this.events[event] = action; }
  click() { if (!this.disabled) this.events.click?.(); }
}
function walk(element) { return [element, ...element.children.flatMap(walk)]; }
function game(slug, seed = 125) {
  const elements = Object.fromEntries(['tablero', 'controles', 'mensaje', 'instruccion', 'nueva'].map(id => [id, new Element('div')]));
  const math = Object.create(Math); math.random = core.seeded(seed);
  const document = { getElementById: id => elements[id], createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag) };
  const scope = vm.createContext({ Math: math, document });
  for (const file of ['compartido/js/nuevos-core.js', `${slug}/script.js`]) vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), scope);
  return { ...elements, button(label) { return walk(elements.tablero).concat(walk(elements.controles)).find(node => node.tagName === 'button' && node.textContent === label); } };
}
test('300 laberintos son conexos, sin saltos y con un camino a casa; los diseños varían', () => {
  const signatures = new Set();
  for (let seed = 1; seed <= 300; seed++) {
    const maze = core.maze(4, core.seeded(seed));
    assert.equal(maze.cells.reduce((sum, list) => sum + list.length, 0), 30);
    for (let index = 0; index < 16; index++) {
      assert.ok(core.path(maze.cells, maze.start, index).length);
      for (const next of maze.cells[index]) {
        assert.ok(maze.cells[next].includes(index));
        assert.equal(Math.abs(Math.floor(index / 4) - Math.floor(next / 4)) + Math.abs(index % 4 - next % 4), 1);
      }
    }
    assert.ok(core.path(maze.cells, maze.start, maze.goal).length > 1);
    signatures.add(JSON.stringify(maze.cells));
  }
  assert.ok(signatures.size > 250);
});
test('100 manos de dominó tienen una solución completa', () => {
  function solve(chain, hand) {
    if (!hand.length) return true;
    return hand.some((tile, index) => ['left','right'].some(side => {
      const next = core.attach(chain, tile, side);
      return next && solve(next, hand.filter((_, i) => i !== index));
    }));
  }
  for (let seed = 1; seed <= 100; seed++) {
    const round = core.domino(core.seeded(seed));
    assert.ok(solve(round.initial, round.hand));
  }
});
test('mazos recorren el banco sin repetir inmediatamente al renovarse', () => {
  const next = core.deck([1,2,3,4,5]);
  const first = Array.from({ length: 5 }, next);
  assert.equal(new Set(first).size, 5);
  assert.notEqual(next(), first[4]);
});
test('los diez juegos arrancan y reinician sin red ni servicios externos', () => {
  assert.equal(catalog.length, 10);
  for (const { slug } of catalog) {
    const ui = game(slug);
    assert.ok(ui.tablero.children.length, slug);
    for (let round = 0; round < 5; round++) { ui.nueva.click(); assert.ok(ui.tablero.children.length, slug); }
    const html = fs.readFileSync(path.join(root, slug, 'index.html'), 'utf8');
    for (const match of html.matchAll(/(?:src|href)="([^"#]+)"/g)) assert.ok(fs.existsSync(path.resolve(root, slug, match[1])), `${slug}: ${match[1]}`);
    assert.equal(JSON.parse(fs.readFileSync(path.join(root, slug, 'juego.json'), 'utf8')).id, slug);
  }
});
test('el laberinto se completa con casillas y el siguiente tablero cambia', () => {
  const ui = game('camino-casa');
  const grid = () => ui.tablero.children[0].children;
  const start = grid().findIndex(cell => cell.classes.has('persona'));
  const goal = grid().findIndex(cell => cell.classes.has('casa'));
  const cells = grid().map((cell, i) => [[-4,'pared-arriba'],[4,'pared-abajo'],[-1,'pared-izquierda'],[1,'pared-derecha']].filter(([, wall]) => !cell.classes.has(wall)).map(([offset]) => i + offset));
  for (const index of core.path(cells, start, goal).slice(1)) grid()[index].click();
  assert.match(ui.mensaje.textContent, /Llegaste a casa/);
  const old = grid().map(cell => cell.className).join(); ui.nueva.click();
  assert.notEqual(grid().map(cell => cell.className).join(), old);
});
test('compras conserva productos encontrados al volver a consultar la lista', () => {
  const ui = game('lista-compras');
  const names = ui.tablero.children[1].children.map(node => node.textContent.slice(node.textContent.indexOf(' ') + 1));
  ui.button('Ya vi la lista: buscar productos').click();
  const product = name => walk(ui.tablero).find(node => node.tagName === 'button' && node.textContent.endsWith(name));
  product(names[0]).click();
  ui.button('Volver a ver la lista').click(); ui.button('Ya vi la lista: buscar productos').click();
  assert.ok(product(names[0]).disabled);
  for (const name of names.slice(1)) product(name).click();
  assert.match(ui.mensaje.textContent, /toda tu lista/);
});
test('sílabas y clasificación se pueden completar usando las pistas', () => {
  const word = game('palabras-silabas');
  for (let i = 0; i < 5; i++) {
    word.button('Pista').click();
    const next = word.mensaje.textContent.match(/siguiente sílaba es (.+)\./);
    if (!next) break;
    const button = walk(word.tablero).find(node => node.tagName === 'button' && !node.disabled && node.textContent === next[1]);
    assert.ok(button); button.click();
    if (word.mensaje.textContent.includes('Formaste')) break;
  }
  assert.match(word.mensaje.textContent, /Formaste/);
  const groups = game('cada-cosa');
  for (let i = 0; i < 9; i++) {
    groups.button('Pista').click();
    const group = groups.mensaje.textContent.split('grupo ')[1].slice(0, -1);
    groups.button(group).click();
  }
  assert.match(groups.mensaje.textContent, /Completaste la ronda/);
});
test('patrón, reloj y conteo aceptan su respuesta y permiten otra ronda', () => {
  const pattern = game('continua-patron'); pattern.button('Pista').click();
  const expected = pattern.mensaje.textContent.split(': ')[1].split(',')[0];
  walk(pattern.controles).find(node => node.tagName === 'button' && node.textContent.endsWith(expected)).click();
  assert.match(pattern.mensaje.textContent, /continúa el patrón/);
  const clock = game('reloj');
  const target = clock.tablero.children[0].textContent.split(': ').at(-1);
  const current = () => clock.tablero.children[2].textContent.match(/Tu reloj: (\d+:\d+)/)[1];
  if (current().split(':')[1] !== target.split(':')[1]) clock.button('Minutos +30').click();
  for (let i = 0; current() !== target && i < 12; i++) clock.button('Hora +').click();
  clock.button('Comprobar hora').click(); assert.match(clock.mensaje.textContent, /hora indicada/);
  const counting = game('cuenta-elige'); const count = counting.tablero.children[1].children.length;
  counting.button(String(count)).click(); assert.match(counting.mensaje.textContent, /¡Hay/);
});
test('tres en raya finaliza y paisaje permite colocar y deshacer', () => {
  assert.equal(core.winner(['X','X','X','','','','','','']).player, 'X');
  assert.equal(core.winner(['X','O','X','X','O','O','O','X','X']), null);
  const tic = game('tres-raya');
  for (let move = 0; move < 5; move++) {
    const cell = walk(tic.tablero).find(node => node.classes.has('casilla-tres') && !node.disabled);
    if (!cell) break; cell.click();
  }
  assert.match(tic.tablero.textContent, /Partida terminada/);
  const landscape = game('mi-paisaje');
  const grid = () => landscape.tablero.children[1];
  grid().children[0].click(); assert.notEqual(grid().children[0].textContent, '+');
  landscape.button('Deshacer último cambio').click(); assert.equal(grid().children[0].textContent, '+');
});
