import {clamp, isCrystal, layout, coreRadius as coreSize, hullVertices, polygonPath, placeLabels, nearestNeighbour, stateKey, unit, coreCentre, randomSeed} from './geometry.js';

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
  const pt = ([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`;
  return {outline: `M${v.map(pt).join('L')}Z`, facets: v.map(q => `M${pt(c)}L${pt(q)}`).join('') + [0, 2, 4, 5].map(k => `M${pt(v[k])}L${pt(v[(k + 2) % n])}`).join('')};
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
  for (const name of ['idle', 'running', 'needs-you', 'blocked', 'done', 'thinking', 'core', 'tint-0', 'tint-1', 'tint-2', 'haze']) {
    const gradient = svgElement('radialGradient', {id: `${prefix}-${name}`, class: `am-grad-${name}`});
    const hull = name.startsWith('tint');
    gradient.append(svgElement('stop', {offset: '0', 'stop-color': 'currentColor', 'stop-opacity': hull ? '.2' : name === 'haze' ? '.9' : '.5'}),
      svgElement('stop', {offset: hull ? '.7' : '.22', 'stop-color': 'currentColor', 'stop-opacity': hull ? '.07' : name === 'haze' ? '.35' : '.2'}),
      svgElement('stop', {offset: '1', 'stop-color': 'currentColor', 'stop-opacity': '0'}));
    defs.append(gradient);
  }
  const haze = svgElement('rect', {class: 'am-haze', fill: `url(#${prefix}-haze)`});
  const dust = svgElement('g', {class: 'am-dust', 'aria-hidden': 'true'});
  const world = svgElement('g', {class: 'am-world', 'aria-hidden': 'true'});
  const spokeLayer = svgElement('g', {class: 'am-spokes'}), hullLayer = svgElement('g', {class: 'am-hulls'}), edgeLayer = svgElement('g', {class: 'am-edges'});
  const core = svgElement('g', {class: 'am-core am-state-core'});
  const nodeLayer = svgElement('g', {class: 'am-nodes'}), pulseLayer = svgElement('g', {class: 'am-pulses'});
  world.append(spokeLayer, hullLayer, edgeLayer, core, nodeLayer, pulseLayer);
  const labels = svgElement('g', {class: 'am-labels', 'aria-hidden': 'true'});
  const hits = svgElement('g', {class: 'am-hits'}), selectRing = svgElement('circle', {class: 'am-select-ring'});
  const coreMark = svgElement('g', {'data-core': 'static'});
  const wordmark = svgElement('text', {class: 'am-wordmark', 'text-anchor': 'middle'}, String(options.coreLabel ?? 'Archeus').toUpperCase());
  const runningText = svgElement('text', {class: 'am-running', 'text-anchor': 'middle'});
  core.append(coreMark, wordmark, runningText);
  svg.append(title, summary, defs, haze, dust, world, labels, hits);
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
  const listeners = new Map(), paths = new Map(), activePulses = new Set(), pointers = new Map(), hullEls = new Map(), edgeEls = [];
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
    labels.replaceChildren();
    const byId = new Map(nodes.map(n => [n.id, n]));
    for (const box of boxes) {
      const n = byId.get(box.id), state = stateKey(n.state), meta = size * .68;
      const group = svgElement('g', {class: `am-label am-state-${words[state] ? state : 'idle'}${n.id === selected ? ' am-selected-label' : ''}`, 'data-node-id': n.id,
        'data-x': box.x, 'data-y': box.y, 'data-width': box.width, 'data-height': box.height});
      if (box.rich) {
        group.append(svgElement('text', {x: box.x + 2, y: box.y + meta * 1.05, class: 'am-label-meta', style: `font-size:${meta}px`}, metaOf(n)));
        group.append(svgElement('text', {x: box.x + 2, y: box.y + meta * 1.4 + size, class: 'am-label-title', style: `font-size:${size}px`}, box.text));
      } else group.append(svgElement('text', {x: box.x + 2, y: box.y + size, class: 'am-label-title', style: `font-size:${size}px`}, box.text));
      labels.append(group);
    }
    for (const target of hits.children) {
      const n = byId.get(target.dataset.nodeId);
      target.setAttribute('transform', `translate(${n.x} ${n.y})`);
      target.querySelector('circle').setAttribute('r', Math.max(width < 480 ? 24 : 22, n.radius));
      target.setAttribute('aria-pressed', String(n.id === selected));
    }
    selectRing.remove();
    for (const node of nodeLayer.children) {
      const on = node.dataset.nodeId === selected;
      node.classList.toggle('am-selected', on);
      if (on) { selectRing.setAttribute('r', positions.find(p => p.id === selected).radius + 11); node.append(selectRing); }
    }
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
    [...hits.children].find(el => el.dataset.nodeId === id)?.focus({preventScroll: true});
  }
  const f = v => +v.toFixed(2);
  function starMarkup(n) {
    const state = stateKey(n.state), colorState = words[state] ? state : 'idle', r = n.radius, g = Math.max(1, r / 8);
    const crystal = isCrystal(n), [tag, shape] = crystal ? ['path', {d: crystalPaths(n.id, r).outline}] : starShape(n.kind, r);
    const attrs = Object.entries(shape).map(([key, value]) => `${key}="${typeof value === 'number' ? f(value) : value}"`).join(' ');
    let glyph = '', outside = '';
    if (state === 'idle') glyph = '<circle r="1.2" fill="currentColor"/>';
    if (state === 'done') glyph = '<path d="M-3,0L-1,2L3,-2" class="am-attention-glyph"/>';
    if (state === 'paused') glyph = '<path d="M-2,-3V3M2,-3V3" class="am-glyph"/>';
    if (state === 'thinking') glyph = '<path d="M0,-3L3,0L0,3L-3,0Z" class="am-attention-glyph"/>';
    if (state === 'blocked') glyph = '<path d="M-3,-3L3,3M3,-3L-3,3" class="am-glyph"/>';
    if (state === 'running') outside = `<path d="M0,${f(-r - 5)}v-3 M${f(r + 5)},0h3 M0,${f(r + 5)}v3 M${f(-r - 5)},0h-3" class="am-glyph"/>`;
    if (state === 'needs-you') {
      const d = f(r + 7);
      outside = `<path d="M0,${-d}L${d},0L0,${d}L${-d},0Z" class="am-attention-ring"/>`;
      glyph = `<path d="M0,-3V1 M0,3v.5" class="${crystal ? 'am-glyph' : 'am-attention-glyph'}"/>`;
    }
    return `<g transform="translate(${f(n.x)} ${f(n.y)})" class="am-star am-state-${colorState}" data-node-id="${esc(n.id)}"><circle r="${f(r * glowReach[colorState])}" fill="url(#${prefix}-${colorState === 'paused' ? 'idle' : colorState})" class="am-glow"/><${tag} ${attrs} class="am-body${crystal ? ' am-crystal' : ['blocked', 'running', 'paused', 'idle'].includes(state) ? ' am-hollow' : ''}"/>${crystal ? `<path d="${crystalPaths(n.id, r).facets}" class="am-facets"/>` : ''}${outside}${glyph ? `<g transform="scale(${f(g)})">${glyph}</g>` : ''}</g>`;
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
  function paintAccents() {
    for (const [project, el] of hullEls) el.setAttribute('class', `am-project am-accent-${accent(...positions.filter(n => (n.project || 'unassigned') === project).map(n => n.state))}`);
    const byId = new Map(positions.map(n => [n.id, n]));
    for (const {el, from, to, kind} of edgeEls) el.setAttribute('class', `am-edge am-edge-${kind} am-accent-${accent(byId.get(from).state, byId.get(to).state)}`);
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
    const ws = Math.round(11 * u + 1);
    wordmark.setAttribute('x', ws * .2); wordmark.setAttribute('y', R + ws * 1.9); wordmark.style.fontSize = `${ws}px`;
    runningText.setAttribute('y', R + ws * 3.5); runningText.style.fontSize = `${ws * .9}px`;
  }
  function render(previous = new Map(), arrivals = false) {
    const focused = hits.contains(document.activeElement) ? document.activeElement.dataset.nodeId : null;
    for (const marker of activePulses) marker.remove(); activePulses.clear();
    spokeLayer.replaceChildren(); hullLayer.replaceChildren();
    paths.clear(); hullEls.clear(); edgeEls.length = 0;
    const projects = new Map((graph.projects || []).map(p => [p.id, p.label]));
    const keys = [...new Set(positions.map(n => n.project || 'unassigned'))].sort();
    keys.forEach((project, i) => {
      const members = positions.filter(n => (n.project || 'unassigned') === project);
      const vertices = hullVertices(members, Math.max(17 * u + 7, Math.max(...members.map(n => n.radius)) + 10)), mx = members.reduce((s, n) => s + n.x, 0) / members.length, my = members.reduce((s, n) => s + n.y, 0) / members.length;
      const group = svgElement('g', {class: 'am-project', 'data-project': project});
      group.append(svgElement('path', {d: polygonPath(vertices, 6 * u), class: `am-hull-fill am-tint-${i % 3}`, fill: `url(#${prefix}-tint-${i % 3})`}),
        svgElement('path', {d: polygonPath(vertices, 6 * u), class: 'am-hull'}));
      if (width >= 480) {
        const inner = vertices.map(v => ({x: mx + (v.x - mx) * .55, y: my + (v.y - my) * .55}));
        group.append(svgElement('path', {d: `${polygonPath(inner)}${vertices.map((v, j) => `M${v.x},${v.y}L${inner[j].x},${inner[j].y}`).join('')}`, class: 'am-facet'}));
      }
      group.append(svgElement('path', {d: vertices.map(v => `M${v.x},${v.y}h0`).join(''), class: 'am-vertex'}));
      hullLayer.append(group); hullEls.set(project, group);
      spokeLayer.append(svgElement('path', {d: `M${centre.x},${centre.y}L${mx},${my}`, class: 'am-spoke'}));
    });
    const byId = new Map(positions.map(n => [n.id, n]));
    const edgeMarkup = [], edgeMeta = [];
    for (const edge of graph.edges || []) {
      const a = byId.get(edge.from), b = byId.get(edge.to);
      if (!a || !b) continue;
      const dx = b.x - a.x, dy = b.y - a.y, bend = a.project === b.project ? .05 : .13, kind = String(edge.kind || 'relation').replace(/W/g, '');
      edgeMarkup.push(`<path d="M${f(a.x)},${f(a.y)} Q${f((a.x + b.x) / 2 - dy * bend)},${f((a.y + b.y) / 2 + dx * bend)} ${f(b.x)},${f(b.y)}" data-edge-id="${esc(edgeId(edge))}"/>`);
      edgeMeta.push({id: edgeId(edge), from: edge.from, to: edge.to, kind});
    }
    edgeLayer.innerHTML = edgeMarkup.join('');
    edgeMeta.forEach((meta, i) => {
      const path = edgeLayer.children[i];
      paths.set(meta.id, path); edgeEls.push({el: path, ...meta});
      if (arrivals && (!previous.has(meta.from) || !previous.has(meta.to))) animate(path, MOTION.relation);
    });
    paintAccents();
    const rows = [], targets = [];
    nodeLayer.innerHTML = positions.map(starMarkup).join('');
    positions.forEach((n, i) => {
      const state = stateKey(n.state), place = projects.get(n.project) || n.project || T('Unassigned');
      targets.push(`<g tabindex="0" role="button" class="am-hit" data-node-id="${esc(n.id)}" aria-label="${esc(`${n.label || n.id}, ${kindWord(n)}, ${words[state] ? nodeWord(n) : state}, ${place}`)}"><circle r="22"/></g>`);
      rows.push(`<tr data-node-id="${esc(n.id)}"><td><button type="button">${esc(n.label || n.id)}</button></td>${[kindWord(n), words[state] ? nodeWord(n) : state, place].map(v => `<td>${esc(v)}</td>`).join('')}</tr>`);
      if (arrivals && (!previous.has(n.id) || previous.get(n.id).state !== n.state)) animate(nodeLayer.children[i], MOTION.appear);
    });
    hits.innerHTML = targets.join('');
    body.innerHTML = rows.join('');
    updateSummary();
    refreshOverlay(); motion();
    if (focused && byId.has(focused)) focusNode(focused);
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
      const key = JSON.stringify({nodes: graph.nodes.map(n => { const {state, ...rest} = n; return {...rest, c: isCrystal(n)}; }), edges: graph.edges, projects: graph.projects});
      if (key === layoutKey && graph.nodes.every(n => previous.get(n.id)?.state === n.state)) return;
      if (key === layoutKey) {
        const nextById = new Map(graph.nodes.map(n => [n.id, n]));
        positions = positions.map(n => ({...n, state: nextById.get(n.id).state}));
        const stars = new Map([...nodeLayer.children].map(el => [el.dataset.nodeId, el]));
        const targets = new Map([...hits.children].map(el => [el.dataset.nodeId, el]));
        const rows = new Map([...body.children].map(el => [el.dataset.nodeId, el]));
        const projects = new Map(graph.projects.map(p => [p.id, p.label]));
        for (const n of positions) if (previous.get(n.id).state !== n.state) {
          const star = drawStar(n), state = words[stateKey(n.state)] ? nodeWord(n) : n.state;
          stars.get(n.id).replaceWith(star); animate(star, MOTION.appear);
          targets.get(n.id).setAttribute('aria-label', `${n.label || n.id}, ${kindWord(n)}, ${state}, ${projects.get(n.project) || n.project || T('Unassigned')}`);
          rows.get(n.id).children[2].textContent = state;
        }
        paintAccents(); updateSummary(); refreshOverlay(); motion(); animate(labels, MOTION.label);
      } else {
        positions = layout(graph, width, height, options.seed); render(previous, true);
      }
      layoutKey = key; emit('update', {nodes: positions.length});
    },
    setSelection: id => { if (!destroyed) choose(id, true); },
    setTheme(name) { if (!destroyed) host.dataset.theme = name; },
    setReducedMotion(bool) { reducedOverride = Boolean(bool); if (!destroyed) motion(); },
    resize, fitView,
    element: host,
    setLive(live) { options.live = live === true; if (!destroyed) motion(); },
    pulse(id) {
      const path = paths.get(id);
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
      pointers.clear(); paths.clear(); activePulses.clear(); listeners.clear(); host.remove();
    }
  };
  resize(); if (options.graph) api.update(options.graph); return api;
}
