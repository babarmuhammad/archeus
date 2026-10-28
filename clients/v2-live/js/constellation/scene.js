import {bodyMarkup, coreMarkup} from './nodeart.js';

// The mission graph, drawn with the same node art and tokens as the live map. Pure: a model in, a scene (positions, arrows) and SVG markup out.
// Only relations that exist in the record are drawn: a node without a record is left out together with its arrows.
export const BOX = Object.freeze({width: 800, height: 640});
const esc = t => String(t).replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`), fx = v => +v.toFixed(1);
const SLOT = {main: {x: 400, y: 280, radius: 100}, exec: {x: 110, y: 280, radius: 68}, result: {x: 690, y: 280, radius: 68}, task: {x: 235, y: 505, radius: 56}, out: {x: 565, y: 505, radius: 56}};
const CORE = {x: 400, y: 52, radius: 26};

// model: {id, title, lines[], state, exec?: {title, lines[], state}, result?: {title, lines[], state}, task?: {title, lines[], state}, out?: bool}
export function missionScene(model) {
  const nodes = [{id: model.id, role: 'main', kind: 'Mission', icon: 'terminal', meta: 'MISSION', title: model.title, lines: model.lines || [], state: model.state, ...SLOT.main}];
  const arrows = [{from: 'core', to: model.id, label: 'ORCHESTRATES'}];
  const add = (slot, id, icon, meta, part) => nodes.push({id, role: slot, kind: 'Mission', icon, meta, title: part.title, lines: part.lines || [], state: part.state || 'idle', ...SLOT[slot]});
  if (model.exec) { add('exec', `${model.id}:exec`, 'code', 'EXECUTION', model.exec); arrows.push({from: `${model.id}:exec`, to: model.id, label: 'EXECUTES'}); }
  if (model.result) { add('result', `${model.id}:result`, 'shield', model.result.meta || 'VERIFICATION', model.result); arrows.push({from: model.id, to: `${model.id}:result`, label: 'RESULTS IN'}); }
  if (model.task) { add('task', `${model.id}:task`, 'doc', 'TASK', model.task); arrows.push({from: model.id, to: `${model.id}:task`, label: 'USES'}); }
  if (model.task && model.result && model.out) {
    add('out', `${model.id}:out`, 'chart', 'OUTPUT', {title: 'Results', lines: []});
    arrows.push({from: model.id, to: `${model.id}:out`, label: 'PRODUCES'});
    if (model.result.meta !== 'REVIEW') arrows.push({from: `${model.id}:out`, to: `${model.id}:result`, label: 'VERIFIES'});
  }
  const at = new Map([['core', CORE], ...nodes.map(n => [n.id, n])]);
  return {box: BOX, core: CORE, nodes, arrows: arrows.map(a => {
    const p = at.get(a.from), q = at.get(a.to), d = Math.hypot(q.x - p.x, q.y - p.y), ux = (q.x - p.x) / d, uy = (q.y - p.y) / d, gap = 9;
    const x1 = p.x + ux * (p.radius + gap), y1 = p.y + uy * (p.radius + gap), x2 = q.x - ux * (q.radius + gap), y2 = q.y - uy * (q.radius + gap);
    const side = Math.abs(ux) < .3, k = ux > 0 ? 1 : -1, t = side || Math.abs(ux) > .9 ? .5 : uy > 0 ? .68 : .42, mx = x1 + (x2 - x1) * t, my = y1 + (y2 - y1) * t;
    return {...a, x1: fx(x1), y1: fx(y1), x2: fx(x2), y2: fx(y2), lx: fx(side ? mx + 12 : mx + uy * k * 16), ly: fx(side ? my + 4 : my - ux * k * 16 + 3), anchor: side ? 'start' : 'middle'};
  })};
}

export function sceneMarkup(scene, t = x => x) {
  const c = scene.core;
  let out = '<defs><marker id="am-arrowhead" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="9" markerHeight="9" orient="auto"><path d="M1 1L7 4L1 7" class="am-arrowhead"/></marker></defs>';
  out += `<g class="am-arrows">${scene.arrows.map(a => `<line class="am-arrow" x1="${a.x1}" y1="${a.y1}" x2="${a.x2}" y2="${a.y2}" marker-end="url(#am-arrowhead)"/><text class="am-arrow-label" x="${a.lx}" y="${a.ly}" text-anchor="${a.anchor}">${esc(t(a.label))}</text>`).join('')}</g>`;
  out += `<g class="am-core am-state-core" transform="translate(${c.x} ${c.y})">${coreMarkup(c.radius, 1.7, {tier: 'standard'})}<text class="am-wordmark" x="2" y="${c.radius + 30}" text-anchor="middle" style="font-size:13px">ARCHEUS</text></g>`;
  for (const n of scene.nodes) {
    out += `<g transform="translate(${n.x} ${n.y})">${bodyMarkup(n, n.icon)}</g>`;
    const rows = [n.title, ...n.lines], big = n.role === 'main';
    out += `<g class="am-label am-state-${n.state === 'needs-you' || n.state === 'running' || n.state === 'done' || n.state === 'blocked' ? n.state : 'idle'}" data-node-id="${esc(n.id)}"><text class="am-label-meta" x="${n.x}" y="${n.y + n.radius + 24}" text-anchor="middle" style="font-size:11px">${esc(t(n.meta))}</text>`
      + rows.map((r, i) => `<text class="${i ? 'am-label-sub' : 'am-label-title'}" x="${n.x}" y="${n.y + n.radius + 48 + i * 19 - (i ? 0 : 0)}" text-anchor="middle" style="font-size:${i ? 13 : big ? 22 : 18}px">${esc(r)}</text>`).join('') + '</g>';
  }
  return out;
}

const hexPoints = (R, cx = 0, cy = 0) => Array.from({length: 6}, (_, i) => [cx + R * Math.cos(Math.PI * (i / 3 - .5)), cy + R * Math.sin(Math.PI * (i / 3 - .5))]);
const SQUARE = 7;
const nearest = (list, p) => list.map(q => [Math.hypot(q[0] - p[0], q[1] - p[1]), q]).sort((a, b) => a[0] - b[0]).map(x => x[1]);
// The calm thread grid: long hairlines between panel vertices and from the panels to the core, with square nodes where lines meet.
// Pure and deterministic: lines run from vertex to vertex of neighbouring panels (and every second panel), and to the core rim.
export function threadGrid(panels, core, {box, bounds} = {}) {
  const C = [core.x, core.y], onCore = p => { const d = Math.hypot(p[0] - C[0], p[1] - C[1]) || 1; return [C[0] + (p[0] - C[0]) / d * core.radius * .95, C[1] + (p[1] - C[1]) / d * core.radius * .95]; };
  const order = panels.map(p => ({...p, v: hexPoints(p.radius, p.x, p.y), a: Math.atan2(p.y - core.y, p.x - core.x)})).sort((a, b) => a.a - b.a), P = order.length, lines = [], squares = [], seen = new Set();
  const line = (a, b) => { const k = [a, b].map(q => q.map(Math.round)).sort().join('|'); if (!seen.has(k)) { seen.add(k); lines.push(`M${fx(a[0])},${fx(a[1])}L${fx(b[0])},${fx(b[1])}`); } };
  const link = (p, q, n) => { const used = new Set(); for (const a of nearest(p.v, [q.x, q.y])) { if (used.size >= n) break; const b = nearest(q.v, a).find(b => !used.has(b)); used.add(b); line(a, b); } };
  for (const p of order) for (const v of nearest(p.v, C).slice(0, 2)) line(v, onCore(v));
  for (let i = 0; i < P && P > 1; i++) { link(order[i], order[(i + 1) % P], 2); if (P > 3) link(order[i], order[(i + 2) % P], 1); }
  for (let i = 0; i < P && P > 1; i++) {
    const p = order[i], q = order[(i + 1) % P], m = [C[0] + ((p.x + q.x) / 2 - C[0]) * .6, C[1] + ((p.y + q.y) / 2 - C[1]) * .6];
    if (order.some(o => Math.hypot(o.x - m[0], o.y - m[1]) < o.radius + 12) || Math.hypot(m[0] - C[0], m[1] - C[1]) < core.radius * 1.4) continue;
    squares.push(m); line(m, nearest(p.v, m)[0]); line(m, nearest(q.v, m)[0]); line(m, onCore(m));
  }
  // A ring of free square nodes round the core, each tied to the core rim and the nearest panel vertex.
  const all = order.flatMap(p => p.v), ring = [];
  for (let k = 0; k < 6; k++) {
    const a = Math.PI * (k / 3 - .5) + .5, d = core.radius * (k % 2 ? 3.1 : 2.3), m = [C[0] + Math.cos(a) * d, C[1] + Math.sin(a) * d];
    const inBox = (x, y) => box && x > box.x - 8 && x < box.x + box.width + 8 && y > box.y - 8 && y < box.y + box.height + 8;
    if (order.some(o => Math.hypot(o.x - m[0], o.y - m[1]) < o.radius + 12) || Array.from({length: 13}, (_, i) => inBox(C[0] + (m[0] - C[0]) * i / 12, C[1] + (m[1] - C[1]) * i / 12)).some(Boolean)
      || (bounds && (m[0] < bounds.left || m[0] > bounds.right || m[1] < bounds.top || m[1] > bounds.bottom))) continue;
    ring.push(m); squares.push(m); line(m, onCore(m)); if (all.length) line(m, nearest(all, m)[0]);
  }
  return {d: lines.join(''), squares};
}
export const gridMarkup = ({d, squares}) => `<path class="am-grid-line" d="${d}"/>${squares.map(([x, y]) => `<rect class="am-vertex" x="${fx(x - SQUARE / 2)}" y="${fx(y - SQUARE / 2)}" width="${SQUARE}" height="${SQUARE}"/>`).join('')}`;

// A project as a pointy-top hexagon panel with its items listed inside (calm state, concept 07). rows: [{label, state, word}].
// Small panels (phone) show the count only.
export function panelMarkup(n, rows, none = 'No items yet', items = 'items') {
  const R = n.radius, v = hexPoints(R), compact = R < 86, shown = compact ? [] : rows.slice(0, 3), step = R * .3, y0 = -R * .16, tx = -R * .5;
  const size = fx(Math.max(13, Math.min(21, R * .17)));
  let out = `<g class="am-star am-state-idle" data-node-id="${esc(n.id)}"><path class="am-panel" d="M${v.map(([x, y]) => `${fx(x)},${fx(y)}`).join('L')}Z"/>`
    + `<circle class="am-panel-dot am-panel-title-dot" cx="${fx(tx)}" cy="${fx(compact ? -R * .12 : -R * .56)}" r="${compact ? 3 : 5}"/><text class="am-label-title" x="${fx(tx + (compact ? 9 : 12))}" y="${fx(compact ? -R * .12 + 4 : -R * .56 + 6)}" style="font-size:${size}px">${esc(n.label || n.id)}</text>`;
  if (!compact) out += `<path class="am-panel-rule" d="M${fx(tx)},${fx(-R * .4)}h${fx(R)}"/>`;
  shown.forEach((r, i) => {
    const y = y0 + i * step;
    out += `<g class="am-state-${esc(r.state)}"><circle class="am-panel-dot" cx="${fx(tx)}" cy="${fx(y - 4)}" r="4"/><text class="am-panel-row" x="${fx(tx + 12)}" y="${fx(y)}" style="font-size:14px">${esc(r.label)}</text><text class="am-panel-word" x="${fx(tx + 12)}" y="${fx(y + 15)}" style="font-size:11px">${esc(r.word)}</text></g>`;
  });
  if (compact) out += `<text class="am-panel-word" x="${fx(tx + 9)}" y="${fx(R * .12 + 8)}" style="font-size:11px">${rows.length ? `${rows.length} ${esc(items)}` : esc(none)}</text>`;
  else if (!shown.length) out += `<text class="am-panel-word" x="${fx(tx + 12)}" y="${fx(y0)}" style="font-size:11px">${esc(none)}</text>`;
  else if (rows.length > shown.length) out += `<text class="am-panel-word" x="${fx(tx + 12)}" y="${fx(y0 + shown.length * step)}" style="font-size:11px">+${rows.length - shown.length}</text>`;
  out += v.map(([x, y]) => `<rect class="am-vertex" x="${fx(x - SQUARE / 2)}" y="${fx(y - SQUARE / 2)}" width="${SQUARE}" height="${SQUARE}"/>`).join('');
  return out + '</g>';
}
