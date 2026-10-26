import {clamp, isCrystal, layout, coreRadius as coreSize, hullVertices, hullPadding, wordmarkSize, polygonPath, placeLabels, nearestNeighbour, stateKey, unit, coreCentre, randomSeed} from './geometry.js';

export const MOTION = Object.freeze({appear: 160, relation: 240, label: 160, travel: 600, breath: 6000});
const NS = 'http://www.w3.org/2000/svg';
let instance = 0;
const words = {'needs-you': 'Needs you', running: 'Running', done: 'Done', blocked: 'Blocked', idle: 'Idle', paused: 'Paused', thinking: 'Thinking'};
const glowReach = {'needs-you': 6.5, running: 5.5, blocked: 4.8, done: 4.4, thinking: 4.4, paused: 3.4, idle: 3.4};
const esc = s => String(s).replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`);
export const edgeId = edge => edge.id ?? `${edge.from}->${edge.to}:${edge.kind || 'relation'}`;
function svgElement(tag, attributes = {}, text) {
  const el = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attributes)) el.setAttribute(key, value);
  if (text !== undefined) el.textContent = text;
  return el;
}
function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
const setAttr = (el, name, value) => { value = String(value); if (el.getAttribute(name) !== value) el.setAttribute(name, value); };
const setText = (el, value) => { if (el.textContent !== value) el.textContent = value; };
// Keyed DOM diff: records are reused by key, `patch` may swap `rec.el` for a fresh element, order follows `items`, records no longer listed are removed.
function reconcile(parent, cache, items, keyOf, build, patch) {
  const seen = new Set();
  let cursor = parent.firstElementChild;
  for (const item of items) {
    const key = keyOf(item);
    seen.add(key);
    let rec = cache.get(key);
    if (!rec) cache.set(key, rec = build(item));
    else { const old = rec.el; patch(rec, item); if (rec.el !== old) { if (old === cursor) cursor = old.nextElementSibling; old.remove(); } }
    if (rec.el === cursor) cursor = cursor.nextElementSibling; else parent.insertBefore(rec.el, cursor);
  }
  for (const [key, rec] of cache) if (!seen.has(key)) { rec.el.remove(); cache.delete(key); }
}
function corePaths(R) {
  const at = (k, r, turn) => { const a = (k * 45 + turn) * Math.PI / 180; return [r * Math.cos(a), r * Math.sin(a)]; };
  const tip = k => at(k, R, -90), inner = k => at(k, R * .4, -67.5);
  const pt = ([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`;
  const range = Array.from({length: 8}, (_, k) => k);
  return {
    outline: `M${range.map(k => `${pt(tip(k))}L${pt(inner(k))}`).join('L')}Z`,
    chords: range.map(k => `M${pt(tip(k))}L${pt(tip((k + 3) % 8))}`).join(''),
    ring: `M${range.map(k => pt(inner(k))).join('L')}Z`,
    spokes: range.map(k => `M0,0L${pt(tip(k))}M${pt(tip(k))}L${pt(inner((k + 7) % 8))}`).join('')
  };
}
function crystalPaths(id, r) {
  const rng = randomSeed(`crystal:${id}`), n = 7, at = k => { const a = -Math.PI / 2 + k * Math.PI * 2 / n + (rng() - .5) * .25, d = r * (.9 + rng() * .2); return [d * Math.cos(a), d * Math.sin(a)]; };
  const v = Array.from({length: n}, (_, k) => at(k)), c = [(rng() - .5) * r * .24, (rng() - .5) * r * .24];
  const pt = ([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`, inner = v.map(([x, y]) => [c[0] + (x - c[0]) * .5, c[1] + (y - c[1]) * .5]);
  return {outline: `M${v.map(pt).join('L')}Z`, dots: v.map(q => `M${pt(q)}h0`).join(''),
    facets: v.map(q => `M${pt(c)}L${pt(q)}`).join('') + [0, 2, 4, 5].map(k => `M${pt(v[k])}L${pt(v[(k + 2) % n])}`).join('') + `M${inner.map(pt).join('L')}Z` + v.map((q, k) => `M${pt(inner[k])}L${pt(v[(k + 1) % n])}`).join('')};
}
function starShape(kind, r) {
  if (kind === 'Execution') return ['path', {d: `M0,${-r * 1.25}L${r * 1.15},${r * .85}L${-r * 1.15},${r * .85}Z`}];
  if (kind === 'Decision') return ['path', {d: `M0,${-r * 1.3}L${r * 1.3},0L0,${r * 1.3}L${-r * 1.3},0Z`}];
  if (kind === 'Project') return ['path', {d: `M${r * 1.15},0L${r * .575},${r}L${-r * .575},${r}L${-r * 1.15},0L${-r * .575},${-r}L${r * .575},${-r}Z`}];
  if (kind === 'Knowledge') return ['rect', {x: -r * .85, y: -r * .85, width: r * 1.7, height: r * 1.7, rx: 1}];
  if (kind === 'Idea') { const s = r * 1.35; return ['path', {d: `M0,${-s}Q0,0 ${s},0Q0,0 0,${s}Q0,0 ${-s},0Q0,0 0,${-s}Z`}]; }
  return ['circle', {r}];
}
export function createMap(container, options = {}) {
  const T = options.t || (x => x);
  const W = k => T(words[k] || k);
  const nodeWord = n => W(stateKey(n.state));
  const kindWord = n => T(n.kind || 'Node');
  const prefix = `constellation-${++instance}`;
  const host = element('div', 'archeus-map');
  host.dataset.theme = options.theme || 'dark';
  host.setAttribute('role', 'group');
  host.setAttribute('aria-label', options.label || 'Work constellation');
  const svg = svgElement('svg', {role: 'img', 'aria-labelledby': `${prefix}-title ${prefix}-summary`});
  const title = svgElement('title', {id: `${prefix}-title`}, options.label || 'Work constellation');
  const summary = svgElement('desc', {id: `${prefix}-summary`});
  const defs = svgElement('defs');
  for (const name of ['idle', 'running', 'needs-you', 'blocked', 'done', 'thinking', 'core', 'tint-0', 'tint-1', 'tint-2', 'haze', 'plate']) {
    const gradient = svgElement('radialGradient', {id: `${prefix}-${name}`, class: `am-grad-${name}`});
    const hull = name.startsWith('tint'), plate = name === 'plate';
    gradient.append(svgElement('stop', {offset: '0', 'stop-color': 'currentColor', 'stop-opacity': hull ? '.2' : name === 'haze' ? '.9' : plate ? '.92' : '.5'}),
      svgElement('stop', {offset: plate ? '.6' : hull ? '.7' : '.22', 'stop-color': 'currentColor', 'stop-opacity': hull ? '.07' : name === 'haze' ? '.35' : plate ? '.8' : '.2'}),
      svgElement('stop', {offset: '1', 'stop-color': 'currentColor', 'stop-opacity': '0'}));
    defs.append(gradient);
  }
  const haze = svgElement('rect', {class: 'am-haze', fill: `url(#${prefix}-haze)`});
  const dust = svgElement('g', {class: 'am-dust', 'aria-hidden': 'true'});
  const world = svgElement('g', {class: 'am-world', 'aria-hidden': 'true'});
  const spokeLayer = svgElement('g', {class: 'am-spokes'}), hullLayer = svgElement('g', {class: 'am-hulls'}), edgeLayer = svgElement('g', {class: 'am-edges'}), plateLayer = svgElement('g', {class: 'am-plates'});
  const core = svgElement('g', {class: 'am-core am-state-core'});
  const nodeLayer = svgElement('g', {class: 'am-nodes'}), pulseLayer = svgElement('g', {class: 'am-pulses'});
  world.append(spokeLayer, hullLayer, edgeLayer, plateLayer, core, nodeLayer, pulseLayer);
  const leaders = svgElement('g', {class: 'am-leaders', 'aria-hidden': 'true'}), labels = svgElement('g', {class: 'am-labels', 'aria-hidden': 'true'});
  const hits = svgElement('g', {class: 'am-hits'}), selectRing = svgElement('circle', {class: 'am-select-ring'});
  const coreMark = svgElement('g', {'data-core': 'static'});
  const wordmark = svgElement('text', {class: 'am-wordmark', 'text-anchor': 'middle'}, String(options.coreLabel ?? 'Archeus').toUpperCase());
  const runningText = svgElement('text', {class: 'am-running', 'text-anchor': 'middle'});
  core.append(coreMark, wordmark, runningText);
  svg.append(title, summary, defs, haze, dust, world, leaders, labels, hits);
  const controls = element('div', 'am-controls');
  controls.setAttribute('aria-label', T('Map view'));
  const status = element('p', 'am-sr');
  status.setAttribute('role', 'status');
  const equivalent = element('div', 'am-equivalent am-sr');
  const table = element('table');
  const caption = element('caption', '', T('Constellation nodes. Select a row to focus its star.'));
  const head = element('thead'), heading = element('tr');
  for (const word of ['Node', 'Kind', 'State', 'Project']) heading.append(element('th', '', T(word)));
  head.append(heading);
  const body = element('tbody');
  table.append(caption, head, body); equivalent.append(table);
  host.append(svg, controls, status, equivalent); container.append(host);
  let graph = {nodes: [], edges: [], projects: []}, positions = [], selected = null;
  let width = 1, height = 1, camera = {x: 0, y: 0, k: 1}, destroyed = false, u = 1, centre = {x: 0, y: 0}, serif = 'serif', sans = 'sans-serif';
  let reducedOverride = options.reducedMotion;
  let layoutKey = '';
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  const listeners = new Map(), activePulses = new Set(), pointers = new Map();
  const starRecs = new Map(), hitRecs = new Map(), rowRecs = new Map(), hullRecs = new Map(), spokeRecs = new Map(), edgeRecs = new Map(), labelRecs = new Map(), plateRecs = new Map(), leaderRecs = new Map();
  let selectedEl = null, fullKey = '';
  let gesture = null;
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  const emit = (event, detail) => { for (const fn of listeners.get(event) || []) fn(detail); };
  const isReduced = () => reducedOverride === true || (reducedOverride === undefined && media.matches);
  const isLive = () => options.live === true && options.fresh !== false && graph.nodes.some(n => stateKey(n.state) === 'running');
  const coreRadius = () => coreSize(u);
  function motion() {
    host.dataset.reduced = String(isReduced());
    coreMark.dataset.core = isLive() && !document.hidden && !isReduced() ? 'breath' : 'static';
    runningText.textContent = isLive() && isReduced() ? T(`${graph.nodes.filter(n => stateKey(n.state) === 'running').length} running`) : '';
    if (isReduced() || document.hidden) {
      for (const animation of host.getAnimations({subtree: true})) if (animation.animationName !== 'core-breath') animation.cancel();
      for (const marker of activePulses) marker.remove();
      activePulses.clear();
    }
  }
  function animate(el, duration) {
    if (isReduced() || document.hidden || !el.animate) return;
    el.animate([{opacity: 0}, {opacity: 1}], {duration, easing: 'ease-out'});
  }
  function screenNodes() {
    return positions.map(n => ({...n, x: n.x * camera.k + camera.x, y: n.y * camera.k + camera.y, radius: n.radius * camera.k + (stateKey(n.state) === 'needs-you' ? 7 : 4)}));
  }
  function refreshOverlay() {
    world.setAttribute('transform', `translate(${camera.x} ${camera.y}) scale(${camera.k})`);
    const nodes = screenNodes();
    const size = clamp(Math.round(11.6 * u + 1), 13, 19), rich = width >= 1280;
    if (context) context.font = `400 ${size}px ${serif}`;
    const k = camera.k, cx = centre.x * k + camera.x, cy = centre.y * k + camera.y, reach = (coreRadius() + 6) * k;
    const metaOf = n => `${kindWord(n)} · ${words[stateKey(n.state)] ? nodeWord(n) : n.state || T('Idle')}`.toUpperCase();
    const measureMeta = text => { context.font = `500 ${size * .68}px ${sans}`; const w = context.measureText(text).width + text.length * size * .68 * .14; context.font = `400 ${size}px ${serif}`; return w; };
    const boxes = placeLabels(nodes, width, height, {selected, size, rich, metaOf, measureMeta: context ? measureMeta : undefined,
      measure: context ? text => context.measureText(text).width : undefined,
      obstacles: [{x: cx - Math.max(reach, 62 * u * k), y: cy - reach, width: Math.max(reach, 62 * u * k) * 2, height: reach + (coreRadius() + 34 * u) * k},
        {x: width - 200, y: height - 58, width: 200, height: 58}]});
    const byId = new Map(nodes.map(n => [n.id, n]));
    const items = boxes.map(box => ({box, n: byId.get(box.id), meta: box.rich ? metaOf(byId.get(box.id)) : ''}));
    const labelSig = ({box, n, meta}) => `${box.rich}|${box.size}|${stateKey(n.state)}|${n.id === selected}|${box.text}|${meta}`;
    const placeLabel = (rec, {box}) => {
      const meta = box.size * .68;
      for (const [name, value] of [['x', box.x], ['y', box.y], ['width', box.width], ['height', box.height]]) setAttr(rec.el, `data-${name}`, value);
      if (rec.meta) { setAttr(rec.meta, 'x', box.x + 2); setAttr(rec.meta, 'y', box.y + meta * 1.05); }
      setAttr(rec.title, 'x', box.x + 2); setAttr(rec.title, 'y', box.rich ? box.y + meta * 1.4 + box.size : box.y + box.size);
    };
    const buildLabel = item => {
      const {box, n} = item, state = stateKey(n.state), meta = box.size * .68;
      const el = svgElement('g', {class: `am-label am-state-${words[state] ? state : 'idle'}${n.id === selected ? ' am-selected-label' : ''}`, 'data-node-id': n.id});
      const rec = {el, sig: labelSig(item), meta: box.rich ? svgElement('text', {class: 'am-label-meta', style: `font-size:${meta}px`}, item.meta) : null,
        title: svgElement('text', {class: 'am-label-title', style: `font-size:${box.size}px`}, box.text)};
      if (rec.meta) el.append(rec.meta);
      el.append(rec.title);
      placeLabel(rec, item);
      return rec;
    };
    reconcile(labels, labelRecs, items, item => item.box.id, buildLabel, (rec, item) => {
      if (rec.sig !== labelSig(item)) Object.assign(rec, buildLabel(item)); else placeLabel(rec, item);
    });
    const placePlate = (rec, {box}) => {
      const k = camera.k;
      setAttr(rec.el, 'cx', f((box.x + box.width / 2 - camera.x) / k)); setAttr(rec.el, 'cy', f((box.y + box.height / 2 - camera.y) / k));
      setAttr(rec.el, 'rx', f((box.width / 2 + 14) / k)); setAttr(rec.el, 'ry', f((box.height / 2 + 9) / k));
    };
    reconcile(plateLayer, plateRecs, items, item => item.box.id, item => { const rec = {el: svgElement('ellipse', {class: 'am-plate', fill: `url(#${prefix}-plate)`})}; placePlate(rec, item); return rec; }, placePlate);
    const far = [];
    for (const {box, n} of items) {
      const ex = clamp(n.x, box.x, box.x + box.width), ey = clamp(n.y, box.y, box.y + box.height), d = Math.hypot(ex - n.x, ey - n.y);
      if (d - n.radius > 36) far.push({id: n.id, d: `M${f(n.x + (ex - n.x) / d * n.radius)},${f(n.y + (ey - n.y) / d * n.radius)}L${f(ex)},${f(ey)}`});
    }
    const placeLeader = (rec, item) => setAttr(rec.el, 'd', item.d);
    reconcile(leaders, leaderRecs, far, item => item.id, item => { const rec = {el: svgElement('path', {class: 'am-leader', 'data-node-id': item.id})}; placeLeader(rec, item); return rec; }, placeLeader);
    const circle = width < 480 ? 24 : 22;
    for (const n of nodes) {
      const rec = hitRecs.get(n.id);
      setAttr(rec.el, 'transform', `translate(${n.x} ${n.y})`);
      setAttr(rec.circle, 'r', Math.max(circle, n.radius));
      setAttr(rec.el, 'aria-pressed', n.id === selected);
    }
    const star = starRecs.get(selected)?.el ?? null;
    if (selectedEl && selectedEl !== star) selectedEl.classList.remove('am-selected');
    selectRing.remove();
    if (star) { star.classList.add('am-selected'); selectRing.setAttribute('r', positions.find(p => p.id === selected).radius + 11); star.append(selectRing); }
    selectedEl = star;
    const missing = nodes.filter(n => (n.id === selected || stateKey(n.state) === 'needs-you') && !boxes.some(b => b.id === n.id));
    host.dataset.labelOverflow = String(missing.length);
    status.textContent = missing.length ? T(`${missing.length} priority labels cannot fit. Full labels available in node table.`) : '';
  }
  function choose(id, reveal = false) {
    if (id !== null && !positions.some(n => n.id === id)) return;
    selected = id;
    const visible = screenNodes().find(n => n.id === id);
    if (reveal && visible && (visible.x < 28 || visible.x > width - 28 || visible.y < 28 || visible.y > height - 80)) {
      const n = positions.find(n => n.id === id);
      camera.x = width / 2 - n.x * camera.k; camera.y = height / 2 - n.y * camera.k;
    }
    refreshOverlay(); emit('select', id);
  }
  function focusNode(id) {
    const n = screenNodes().find(n => n.id === id);
    if (!n) return;
    if (n.x < 28 || n.x > width - 28 || n.y < 28 || n.y > height - 28) {
      const p = positions.find(p => p.id === id);
      camera.x = width / 2 - p.x * camera.k; camera.y = height / 2 - p.y * camera.k; refreshOverlay();
    }
    hitRecs.get(id)?.el.focus({preventScroll: true});
  }
  const f = v => +v.toFixed(2);
  function starMarkup(n) {
    const state = stateKey(n.state), colorState = words[state] ? state : 'idle', r = n.radius, crystal = isCrystal(n), g = crystal ? r / 14 : Math.max(1, r / 8);
    const cp = crystal ? crystalPaths(n.id, r) : null, [tag, shape] = crystal ? ['path', {d: cp.outline}] : starShape(n.kind, r);
    const attrs = Object.entries(shape).map(([key, value]) => `${key}="${typeof value === 'number' ? f(value) : value}"`).join(' ');
    let glyph = '', outside = '';
    if (state === 'idle') glyph = '<circle r="1.2" fill="currentColor"/>';
    if (state === 'done') glyph = '<path d="M-3,0L-1,2L3,-2" class="am-attention-glyph"/>';
    if (state === 'paused') glyph = '<path d="M-2,-3V3M2,-3V3" class="am-glyph"/>';
    if (state === 'thinking') glyph = '<path d="M0,-3L3,0L0,3L-3,0Z" class="am-attention-glyph"/>';
    if (state === 'blocked') glyph = '<path d="M-3,-3L3,3M3,-3L-3,3" class="am-glyph"/>';
    if (state === 'running' && crystal) glyph = '<circle r="3.4" class="am-glyph"/><circle r="1.1" fill="currentColor"/>';
    if (state === 'running') outside = `<path d="M0,${f(-r - 5)}v-3 M${f(r + 5)},0h3 M0,${f(r + 5)}v3 M${f(-r - 5)},0h-3" class="am-glyph"/>`;
    if (state === 'needs-you') {
      const d = f(r + 7);
      outside = `<path d="M0,${-d}L${d},0L0,${d}L${-d},0Z" class="am-attention-ring"/>`;
      glyph = `<path d="M0,-3.4V.9 M0,3.1v.4" class="${crystal ? 'am-glyph' : 'am-attention-glyph'}"/>`;
    }
    return `<g class="am-star am-state-${colorState}" data-node-id="${esc(n.id)}"><circle r="${f(r * (crystal ? 3.6 : glowReach[colorState]))}" fill="url(#${prefix}-${colorState === 'paused' ? 'idle' : colorState})" class="am-glow"/><${tag} ${attrs} class="am-body${crystal ? ' am-crystal' : ['blocked', 'running', 'paused', 'idle'].includes(state) ? ' am-hollow' : ''}"/>${crystal ? `<path d="${cp.facets}" class="am-facets"/><path d="${cp.dots}" class="am-crystal-dots"/>` : ''}${outside}${glyph ? `<g transform="scale(${f(g)})">${crystal ? '<circle r="5" class="am-mark-plate"/>' : ''}${glyph}</g>` : ''}</g>`;
  }
  function drawStar(n) {
    const holder = svgElement('g');
    holder.innerHTML = starMarkup(n);
    return holder.firstElementChild;
  }
  function updateSummary() {
    summary.textContent = T(`${positions.length} nodes across ${graph.projects.length} projects. ${positions.filter(n => stateKey(n.state) === 'needs-you').length} need you. Tab through stars, Enter to select, arrow keys move by direction. Equivalent node table follows map controls.`);
  }
  function accent(...states) {
    const keys = states.map(stateKey);
    return keys.includes('needs-you') ? 'needs-you' : keys.includes('running') ? 'running' : 'none';
  }
  function drawDust() {
    dust.replaceChildren();
    const rng = randomSeed(`${options.seed || 'archeus'}:dust`), count = clamp(Math.round(width * height / 5200), 36, 420);
    const tiers = [[], [], []];
    for (let i = 0; i < count; i++) tiers[i % 3 === 0 ? 2 : i % 3 === 1 ? 1 : 0].push(`M${(rng() * width).toFixed(1)},${(rng() * height).toFixed(1)}h0`);
    tiers.forEach((list, i) => dust.append(svgElement('path', {d: list.join(''), class: `am-dust-${i}`})));
  }
  function drawCore() {
    const R = coreRadius(), p = corePaths(R);
    core.setAttribute('transform', `translate(${centre.x} ${centre.y})`);
    coreMark.replaceChildren(svgElement('circle', {r: R * 2.6, fill: `url(#${prefix}-core)`, class: 'am-core-glow'}),
      svgElement('path', {d: p.chords, class: 'am-core-chords'}), svgElement('path', {d: p.spokes, class: 'am-core-thread'}),
      svgElement('path', {d: p.ring, class: 'am-core-ring'}), svgElement('path', {d: p.outline, class: 'am-core-outline'}),
      svgElement('circle', {r: Math.max(2.5, R * .09), class: 'am-core-dot'}));
    const ws = wordmarkSize(u);
    wordmark.setAttribute('x', ws * .2); wordmark.setAttribute('y', R + ws * 1.9); wordmark.style.fontSize = `${ws}px`;
    runningText.setAttribute('y', R + ws * 3.5); runningText.style.fontSize = `${ws * .9}px`;
  }
  function render(previous = new Map(), arrivals = false, moved = true) {
    if (moved) { for (const marker of activePulses) marker.remove(); activePulses.clear(); }
    const projects = new Map((graph.projects || []).map(p => [p.id, p.label]));
    const groups = new Map();
    for (const n of positions) { const key = n.project || 'unassigned'; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(n); }
    const hulls = [...groups.keys()].sort().map((project, i) => ({project, i, members: groups.get(project)}));
    const patchHull = (rec, item) => {
      const {i, members} = item;
      setAttr(rec.el, 'class', `am-project am-accent-${accent(...members.map(n => n.state))}`);
      setAttr(rec.fill, 'class', `am-hull-fill am-tint-${i % 3}`); setAttr(rec.fill, 'fill', `url(#${prefix}-tint-${i % 3})`);
      const shape = [width, u];
      for (const n of members) shape.push(n.x, n.y, n.radius);
      if (rec.shape && rec.shape.length === shape.length && rec.shape.every((v, k) => v === shape[k])) { item.mx = rec.mx; item.my = rec.my; return; }
      rec.shape = shape;
      const vertices = hullVertices(members, hullPadding(members, u));
      item.mx = rec.mx = members.reduce((s, n) => s + n.x, 0) / members.length; item.my = rec.my = members.reduce((s, n) => s + n.y, 0) / members.length;
      const d = polygonPath(vertices, 6 * u);
      setAttr(rec.fill, 'd', d); setAttr(rec.outline, 'd', d);
      const inner = vertices.map(v => ({x: item.mx + (v.x - item.mx) * .55, y: item.my + (v.y - item.my) * .55}));
      setAttr(rec.facet, 'd', width >= 480 ? `${polygonPath(inner)}${vertices.map((v, j) => `M${v.x},${v.y}L${inner[j].x},${inner[j].y}`).join('')}` : '');
      setAttr(rec.vertex, 'd', vertices.map(v => `M${v.x},${v.y}h0`).join(''));
    };
    reconcile(hullLayer, hullRecs, hulls, item => item.project, item => {
      const rec = {el: svgElement('g', {'data-project': item.project}), fill: svgElement('path'), outline: svgElement('path', {class: 'am-hull'}), facet: svgElement('path', {class: 'am-facet'}), vertex: svgElement('path', {class: 'am-vertex'})};
      rec.el.append(rec.fill, rec.outline, rec.facet, rec.vertex);
      patchHull(rec, item);
      return rec;
    }, patchHull);
    const patchSpoke = (rec, item) => setAttr(rec.el, 'd', `M${centre.x},${centre.y}L${item.mx},${item.my}`);
    reconcile(spokeLayer, spokeRecs, hulls, item => item.project, item => { const rec = {el: svgElement('path', {class: 'am-spoke'})}; patchSpoke(rec, item); return rec; }, patchSpoke);
    const byId = new Map(positions.map(n => [n.id, n]));
    const edges = [];
    for (const edge of graph.edges || []) {
      const a = byId.get(edge.from), b = byId.get(edge.to);
      if (a && b) edges.push({id: edgeId(edge), a, b, kind: String(edge.kind || 'relation').replace(/W/g, '')});
    }
    const freshEdges = [];
    const patchEdge = (rec, {a, b, kind}) => {
      if (rec.ax !== a.x || rec.ay !== a.y || rec.bx !== b.x || rec.by !== b.y) {
        const dx = b.x - a.x, dy = b.y - a.y, bend = a.project === b.project ? .05 : .13;
        setAttr(rec.el, 'd', `M${f(a.x)},${f(a.y)} Q${f((a.x + b.x) / 2 - dy * bend)},${f((a.y + b.y) / 2 + dx * bend)} ${f(b.x)},${f(b.y)}`);
        rec.ax = a.x; rec.ay = a.y; rec.bx = b.x; rec.by = b.y;
      }
      if (rec.sa !== a.state || rec.sb !== b.state || rec.kind !== kind) {
        setAttr(rec.el, 'class', `am-edge am-edge-${kind} am-accent-${accent(a.state, b.state)}`);
        rec.sa = a.state; rec.sb = b.state; rec.kind = kind;
      }
    };
    reconcile(edgeLayer, edgeRecs, edges, e => e.id, e => {
      const rec = {el: svgElement('path', {'data-edge-id': e.id})};
      patchEdge(rec, e);
      if (arrivals && (!previous.has(e.a.id) || !previous.has(e.b.id))) freshEdges.push(rec.el);
      return rec;
    }, patchEdge);
    const arrived = [];
    const starSig = n => `${n.state}|${n.kind}|${n.radius}`;
    const placeStar = (rec, n) => { if (rec.x !== n.x || rec.y !== n.y) { setAttr(rec.el, 'transform', `translate(${f(n.x)} ${f(n.y)})`); rec.x = n.x; rec.y = n.y; } };
    const buildStar = n => { const rec = {el: drawStar(n), sig: starSig(n)}; placeStar(rec, n); if (arrivals) arrived.push(rec.el); return rec; };
    reconcile(nodeLayer, starRecs, positions, n => n.id, buildStar, (rec, n) => { if (rec.sig !== starSig(n)) { Object.assign(rec, buildStar(n)); rec.x = rec.y = undefined; placeStar(rec, n); } else placeStar(rec, n); });
    const placeOf = n => projects.get(n.project) || n.project || T('Unassigned');
    const stateOf = n => { const state = stateKey(n.state); return words[state] ? nodeWord(n) : state; };
    const same = (rec, n) => rec.stamped && rec.label === n.label && rec.kind === n.kind && rec.state === n.state && rec.place === placeOf(n);
    const stamp = (rec, n) => { rec.stamped = true; rec.label = n.label; rec.kind = n.kind; rec.state = n.state; rec.place = placeOf(n); };
    const patchHit = (rec, n) => { if (same(rec, n)) return; setAttr(rec.el, 'aria-label', `${n.label || n.id}, ${kindWord(n)}, ${stateOf(n)}, ${placeOf(n)}`); stamp(rec, n); };
    reconcile(hits, hitRecs, positions, n => n.id, n => {
      const circle = svgElement('circle', {r: 22}), rec = {el: svgElement('g', {tabindex: 0, role: 'button', class: 'am-hit', 'data-node-id': n.id}), circle};
      rec.el.append(circle);
      patchHit(rec, n);
      return rec;
    }, patchHit);
    const patchRow = (rec, n) => {
      if (same(rec, n)) return;
      stamp(rec, n);
      setText(rec.button, String(n.label || n.id)); setText(rec.cells[0], kindWord(n)); setText(rec.cells[1], stateOf(n)); setText(rec.cells[2], placeOf(n));
    };
    reconcile(body, rowRecs, positions, n => n.id, n => {
      const button = element('button'), first = element('td'), rec = {el: element('tr'), button, cells: [element('td'), element('td'), element('td')]};
      button.type = 'button'; first.append(button); rec.el.dataset.nodeId = n.id; rec.el.append(first, ...rec.cells);
      patchRow(rec, n);
      return rec;
    }, patchRow);
    for (const el of arrived) animate(el, MOTION.appear);
    for (const el of freshEdges) animate(el, MOTION.relation);
    updateSummary();
    refreshOverlay(); motion();
    if (arrivals) animate(labels, MOTION.label);
  }
  function focusNodeIfOutside(id) {
    const n = screenNodes().find(n => n.id === id);
    if (n && (n.x < 24 || n.x > width - 24 || n.y < 24 || n.y > height - 24)) focusNode(id);
  }
  function resize() {
    if (destroyed) return;
    const rect = host.getBoundingClientRect();
    const w = Math.max(1, rect.width), h = Math.max(1, rect.height);
    if (w === width && h === height && positions.length) return;
    width = w; height = h; u = unit(w, h); centre = coreCentre(w, h); host.dataset.narrow = String(width < 480); svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    haze.setAttribute('width', width); haze.setAttribute('height', height);
    const css = getComputedStyle(host); serif = css.getPropertyValue('--am-serif').trim() || 'serif'; sans = css.getPropertyValue('--am-sans').trim() || 'sans-serif';
    drawDust(); drawCore();
    camera = {x: 0, y: 0, k: 1}; positions = layout(graph, width, height, options.seed); render(); emit('resize', {width, height});
  }
  function zoom(k, x = width / 2, y = height / 2) {
    const next = clamp(k, .5, 4), ratio = next / camera.k;
    camera.x = x - (x - camera.x) * ratio; camera.y = y - (y - camera.y) * ratio; camera.k = next;
    limitCamera(); refreshOverlay(); emit('viewchange', {...camera});
  }
  function limitCamera() {
    camera.x = clamp(camera.x, -width * camera.k, width);
    camera.y = clamp(camera.y, -height * camera.k, height);
  }
  function reset() { camera = {x: 0, y: 0, k: 1}; refreshOverlay(); emit('viewchange', {...camera}); }
  function fitView() {
    if (!positions.length) return reset();
    const minX = Math.min(...positions.map(n => n.x - n.radius - 28)), maxX = Math.max(...positions.map(n => n.x + n.radius + 28));
    const minY = Math.min(...positions.map(n => n.y - n.radius - 28)), maxY = Math.max(...positions.map(n => n.y + n.radius + 28));
    const k = clamp(Math.min((width - 32) / (maxX - minX || 1), (height - 90) / (maxY - minY || 1)), .5, 4);
    camera = {k, x: width / 2 - (minX + maxX) / 2 * k, y: (height - 50) / 2 - (minY + maxY) / 2 * k};
    refreshOverlay(); emit('viewchange', {...camera});
  }
  for (const [label, text, action] of [['Zoom out', '−', () => zoom(camera.k / 1.25)], ['Zoom in', '+', () => zoom(camera.k * 1.25)], ['Fit all nodes', 'Fit', fitView], ['Reset map view', 'Reset', reset]].map(([a, t, g]) => [T(a), t === 'Fit' || t === 'Reset' ? T(t) : t, g])) {
    const button = element('button', '', text); button.type = 'button'; button.setAttribute('aria-label', label); button.addEventListener('click', action); controls.append(button);
  }
  function point(event) { const r = svg.getBoundingClientRect(); return {x: event.clientX - r.left, y: event.clientY - r.top}; }
  function wheel(event) { event.preventDefault(); const p = point(event); zoom(camera.k * Math.exp(-event.deltaY * .0015), p.x, p.y); }
  let suppressClick = false;
  function startGesture() {
    const values = [...pointers.values()];
    gesture = {camera: {...camera}, center: values.length > 1 ? {x: (values[0].x + values[1].x) / 2, y: (values[0].y + values[1].y) / 2} : values[0],
      distance: values.length > 1 ? Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y) : 0};
  }
  function down(event) {
    if (event.button !== 0) return;
    if (!pointers.size) suppressClick = false;
    pointers.set(event.pointerId, point(event)); event.target.setPointerCapture(event.pointerId); startGesture();
  }
  function move(event) {
    if (!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, point(event));
    const values = [...pointers.values()];
    const center = values.length > 1 ? {x: (values[0].x + values[1].x) / 2, y: (values[0].y + values[1].y) / 2} : values[0];
    const distance = values.length > 1 ? Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y) : 0;
    if (Math.hypot(center.x - gesture.center.x, center.y - gesture.center.y) > 4 || values.length > 1) suppressClick = true;
    const k = gesture.distance ? clamp(gesture.camera.k * distance / gesture.distance, .5, 4) : gesture.camera.k;
    camera = {k, x: center.x - (gesture.center.x - gesture.camera.x) * k / gesture.camera.k, y: center.y - (gesture.center.y - gesture.camera.y) * k / gesture.camera.k};
    limitCamera(); refreshOverlay();
  }
  function up(event) {
    pointers.delete(event.pointerId);
    if (pointers.size) startGesture(); else { gesture = null; emit('viewchange', {...camera}); }
  }
  hits.addEventListener('focusin', event => { const id = event.target.closest('.am-hit')?.dataset.nodeId; if (id) focusNodeIfOutside(id); });
  hits.addEventListener('keydown', event => {
    const id = event.target.closest('.am-hit')?.dataset.nodeId;
    if (!id) return;
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(id); }
    else if (event.key.startsWith('Arrow')) { event.preventDefault(); const next = nearestNeighbour(positions, id, event.key); if (next) focusNode(next); }
  });
  body.addEventListener('click', event => { const id = event.target.closest('tr')?.dataset.nodeId; if (id && event.target.closest('button')) { choose(id, true); focusNode(id); } });
  hits.addEventListener('click', event => {
    if (suppressClick) return;
    if (!event.detail) { const id = event.target.closest('.am-hit')?.dataset.nodeId; if (id) choose(id); return; }
    const p = point(event);
    let best = null, nearest = Infinity;
    for (const n of screenNodes()) {
      const d = Math.hypot(n.x - p.x, n.y - p.y);
      if (d < Math.max(width < 480 ? 24 : 22, n.radius) && d < nearest) { best = n.id; nearest = d; }
    }
    if (best) choose(best);
  });
  svg.addEventListener('wheel', wheel, {passive: false});
  svg.addEventListener('pointerdown', down); svg.addEventListener('pointermove', move);
  svg.addEventListener('pointerup', up); svg.addEventListener('pointercancel', up);
  media.addEventListener('change', motion); document.addEventListener('visibilitychange', motion);
  const observer = new ResizeObserver(resize); observer.observe(host);
  const refit = () => { if (!destroyed && positions.length) refreshOverlay(); };
  document.fonts?.addEventListener('loadingdone', refit);
  const api = {
    update(next) {
      if (destroyed) return;
      const ids = new Set();
      for (const n of next.nodes) { if (ids.has(n.id)) throw new Error(`Duplicate node id: ${n.id}`); ids.add(n.id); }
      const previous = new Map(graph.nodes.map(n => [n.id, n]));
      graph = {nodes: next.nodes.map(n => ({...n})), edges: (next.edges || []).map(e => ({...e})), projects: (next.projects || []).map(p => ({...p}))};
      if (!ids.has(selected)) selected = null;
      const full = JSON.stringify(graph);
      if (full === fullKey) return;
      fullKey = full;
      const key = graph.nodes.map(n => `${n.id}|${n.kind}|${n.project}|${n.weight}|${isCrystal(n)}`).join(';');
      const moved = key !== layoutKey;
      if (moved) positions = layout(graph, width, height, options.seed);
      else { const at = new Map(positions.map(p => [p.id, p])); positions = graph.nodes.map(n => { const p = at.get(n.id); return {...n, x: p.x, y: p.y, radius: p.radius, rank: p.rank}; }).sort((x, y) => String(x.id).localeCompare(String(y.id))); }
      layoutKey = key;
      render(previous, true, moved);
      emit('update', {nodes: positions.length});
    },
    setSelection: id => { if (!destroyed) choose(id, true); },
    setTheme(name) { if (!destroyed) host.dataset.theme = name; },
    setReducedMotion(bool) { reducedOverride = Boolean(bool); if (!destroyed) motion(); },
    resize, fitView,
    element: host,
    setLive(live) { options.live = live === true; if (!destroyed) motion(); },
    pulse(id) {
      const path = edgeRecs.get(id)?.el;
      if (destroyed || !path || isReduced() || document.hidden || activePulses.size >= 8) return false;
      const marker = svgElement('circle', {r: 3, class: 'am-marker'});
      marker.style.offsetPath = `path('${path.getAttribute('d')}')`;
      pulseLayer.append(marker); activePulses.add(marker);
      const animation = marker.animate([{offsetDistance: '0%', opacity: 0}, {offsetDistance: '10%', opacity: 1, offset: .1}, {offsetDistance: '90%', opacity: 1, offset: .9}, {offsetDistance: '100%', opacity: 0}], {duration: MOTION.travel, easing: 'linear'});
      const finish = () => { marker.remove(); activePulses.delete(marker); };
      animation.onfinish = finish; animation.oncancel = finish; emit('pulse', id); return true;
    },
    on(event, fn) { if (!listeners.has(event)) listeners.set(event, new Set()); listeners.get(event).add(fn); return () => listeners.get(event)?.delete(fn); },
    destroy() {
      if (destroyed) return;
      destroyed = true; observer.disconnect(); media.removeEventListener('change', motion); document.removeEventListener('visibilitychange', motion); document.fonts?.removeEventListener('loadingdone', refit);
      for (const animation of host.getAnimations({subtree: true})) animation.cancel();
      pointers.clear(); activePulses.clear(); listeners.clear(); host.remove();
    }
  };
  resize(); if (options.graph) api.update(options.graph); return api;
}
