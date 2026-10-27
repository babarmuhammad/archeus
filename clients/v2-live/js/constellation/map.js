import {driftOf, ambientField, coreKeepOut, clamp, coversNode, overlaps, isCrystal, layout, layoutPhone, layoutCalm, coreRadius as coreSize, coreReach, INSET, wordmarkSize, placeLabels, nearestNeighbour, stateKey, unit, coreCentre} from './geometry.js';
import {bodyMarkup, coreStar} from './nodeart.js';
import {panelMarkup, threadGrid, gridMarkup} from './scene.js';

export const MOTION = Object.freeze({appear: 160, relation: 240, label: 160, travel: 600, breath: 6000});
const NS = 'http://www.w3.org/2000/svg';
let instance = 0;
const words = {'needs-you': 'Needs you', running: 'Running', done: 'Done', blocked: 'Blocked', idle: 'Idle', paused: 'Paused', thinking: 'Thinking'};
const kinds = {Execution: 'Agent execution'};
const ICON = {Project: 'notes', Execution: 'code', Idea: 'bulb', Knowledge: 'doc'};
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
function starShape(kind, r) {
  if (kind === 'Decision') return ['path', {d: `M0,${-r * 1.3}L${r * 1.3},0L0,${r * 1.3}L${-r * 1.3},0Z`}];
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
  host.dataset.theme = options.theme || 'dark'; host.dataset.calm = String(options.calm === true);
  host.setAttribute('role', 'group');
  host.setAttribute('aria-label', options.label || 'Work constellation');
  const svg = svgElement('svg', {role: 'img', 'aria-labelledby': `${prefix}-title ${prefix}-summary`});
  const title = svgElement('title', {id: `${prefix}-title`}, options.label || 'Work constellation');
  const summary = svgElement('desc', {id: `${prefix}-summary`});
  const world = svgElement('g', {class: 'am-world', 'aria-hidden': 'true'});
  const spokeLayer = svgElement('g', {class: 'am-spokes'}), gridLayer = svgElement('g', {class: 'am-grid'}), ambient = svgElement('g', {class: 'am-ambient'}), edgeLayer = svgElement('g', {class: 'am-edges'});
  const core = svgElement('g', {class: 'am-core am-state-core'});
  const nodeLayer = svgElement('g', {class: 'am-nodes'}), pulseLayer = svgElement('g', {class: 'am-pulses'});
  world.append(ambient, spokeLayer, gridLayer, edgeLayer, core, nodeLayer, pulseLayer);
  const leaders = svgElement('g', {class: 'am-leaders', 'aria-hidden': 'true'}), labels = svgElement('g', {class: 'am-labels', 'aria-hidden': 'true'});
  const reviews = svgElement('g', {class: 'am-reviews'});
  const hits = svgElement('g', {class: 'am-hits'}), selectRing = svgElement('circle', {class: 'am-select-ring'});
  const coreMark = svgElement('g', {'data-core': 'static'});
  const wordmark = svgElement('text', {class: 'am-wordmark', 'text-anchor': 'middle'}, String(options.coreLabel ?? 'Archeus').toUpperCase());
  const tagline = svgElement('text', {class: 'am-tagline', 'text-anchor': 'middle'}, options.calm ? T('Understand · Plan · Do').toUpperCase() : T('Your projects. In context.'));
  const runningText = svgElement('text', {class: 'am-running', 'text-anchor': 'middle'});
  core.append(coreMark, wordmark, tagline, runningText);
  svg.append(title, summary, world, leaders, labels, hits, reviews);
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
  let controlsBottom = 12, inset = INSET, width = 1, height = 1, camera = {x: 0, y: 0, k: 1}, destroyed = false, u = 1, centre = {x: 0, y: 0}, serif = 'serif', sans = 'sans-serif';
  let reducedOverride = options.reducedMotion;
  let layoutKey = '';
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  const listeners = new Map(), activePulses = new Set(), pointers = new Map();
  const starRecs = new Map(), hitRecs = new Map(), rowRecs = new Map(), spokeRecs = new Map(), edgeRecs = new Map(), labelRecs = new Map(), leaderRecs = new Map(), reviewRecs = new Map();
  let selectedEl = null, fullKey = '', visible = true, playing = options.playing === true, hovered = null;
  let gesture = null;
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  const emit = (event, detail) => { for (const fn of listeners.get(event) || []) fn(detail); };
  const isReduced = () => reducedOverride === true || (reducedOverride === undefined && media.matches);
  const isLive = () => options.live === true && options.fresh !== false && graph.nodes.some(n => stateKey(n.state) === 'running');
  const phoneOverview = () => options.overview && !options.calm && width < 600;
  const layoutScene = () => (options.calm ? layoutCalm : phoneOverview() ? layoutPhone : layout)(graph, width, height, options.seed, inset);
  const coreRadius = () => phoneOverview() ? 28 : coreSize(u, options.calm, width), reachOf = () => coreReach(width, options.calm);
  // Ambient motion (drift, rings, travelling markers) runs only for a playing simulation, with full motion, a visible tab and a visible map; the calm scene has none.
  const ambientOn = () => playing && visible && !isReduced() && !document.hidden && !options.calm;
  function motion() {
    host.dataset.reduced = String(isReduced());
    host.dataset.ambient = ambientOn() ? 'on' : 'off';
    coreMark.dataset.core = isLive() && !document.hidden && !isReduced() ? 'breath' : 'static';
    runningText.textContent = isLive() && isReduced() ? T(`${graph.nodes.filter(n => stateKey(n.state) === 'running').length} running`) : '';
    if (isReduced() || document.hidden) {
      for (const animation of host.getAnimations({subtree: true})) if (animation.animationName !== 'core-breath') animation.cancel();
      for (const marker of activePulses) marker.remove();
      activePulses.clear();
    }
  }
  function animate(el, duration, delay = 0, grow = false) {
    if (isReduced() || document.hidden || !el.animate) return;
    el.animate(grow ? [{opacity: 0, scale: .9}, {opacity: 1, scale: 1}] : [{opacity: 0}, {opacity: 1}], {duration, delay, easing: 'cubic-bezier(.23, 1, .32, 1)', fill: 'backwards'});
  }
  // The hairlines of the selected, hovered or focused node brighten.
  const hotEdge = rec => rec.el.classList.toggle('am-hot', [selected, hovered].some(id => id !== null && (rec.aid === id || rec.bid === id)));
  const syncHot = () => { for (const rec of edgeRecs.values()) hotEdge(rec); };
  const driftVars = (el, id) => { const d = driftOf(options.seed, id); el.style.setProperty('--dx', d.dx + 'px'); el.style.setProperty('--dy', d.dy + 'px'); el.style.setProperty('--dp', d.period + 'ms'); el.style.setProperty('--dd', d.delay + 'ms'); };
  function screenNodes() {
    return positions.map(n => ({...n, x: n.x * camera.k + camera.x, y: n.y * camera.k + camera.y, radius: n.radius * camera.k + (stateKey(n.state) === 'needs-you' ? 7 : 4)}));
  }
  function refreshOverlay() {
    world.setAttribute('transform', `translate(${camera.x} ${camera.y}) scale(${camera.k})`);
    const nodes = screenNodes();
    const size = width < 360 ? 12 : width < 480 ? 14 : clamp(Math.round(17 * u + 2), 15, 24), rich = width >= 700;
    if (context) context.font = `400 ${size}px ${serif}`;
    const k = camera.k, cx = centre.x * k + camera.x, cy = centre.y * k + camera.y, reach = (coreRadius() * reachOf() + 6) * k, below = (coreRadius() * reachOf() + wordmarkSize(u) * (width < 480 ? 3 : 5)) * k;
    const cw = (controls.offsetWidth || 200) + 24, hold = Math.max(reach, 62 * u * k), coreBox = {x: cx - hold, y: cy - reach, width: hold * 2, height: reach + below};
    const metaOf = n => kindWord(n).toUpperCase(), subOf = n => n.kind === 'Project' ? '' : words[stateKey(n.state)] ? nodeWord(n) : n.state || T('Idle');
    const reviewFor = nodes.filter(n => n.kind === 'Mission' && stateKey(n.state) === 'needs-you').sort((a, b) => (a.id === selected ? -1 : b.id === selected ? 1 : String(a.id).localeCompare(String(b.id))))[0];
    // The button goes below, above, right or left of its node, whichever side clears every other node and the bands the headline and drawer own.
    const reviewSpots = reviewFor && width >= 480 && !phoneOverview() && options.review !== false ? [[-56, reviewFor.radius + 12], [-130, reviewFor.radius + 12], [8, reviewFor.radius + 12], [-56, -reviewFor.radius - 56], [-130, -reviewFor.radius - 56], [8, -reviewFor.radius - 56], [reviewFor.radius + 12, -22], [-reviewFor.radius - 124, -22], [-56, reviewFor.radius + 40], [-56, -reviewFor.radius - 84]]
      .map(([dx, dy]) => ({id: reviewFor.id, x: reviewFor.x + dx, y: reviewFor.y + dy, width: 112, height: 44}))
      .filter(b => b.x >= 8 && b.x + b.width <= width - 8 && b.y >= inset.top && b.y + b.height <= height - inset.bottom && !overlaps(b, coreBox, 6) && !nodes.some(o => coversNode(b, o, 2))) : [];
    const measureMeta = text => { context.font = `500 ${size * .68}px ${sans}`; const w = context.measureText(text).width + text.length * size * .68 * .14; context.font = `400 ${size}px ${serif}`; return w; };
    const labelsFor = review => options.calm ? [] : placeLabels(nodes, width, height, {selected, size, rich, metaOf, measureMeta: context ? measureMeta : undefined,
      measure: context ? text => context.measureText(text).width : undefined,
      obstacles: [coreBox,
        {x: 0, y: 0, width, height: Math.max(0, inset.top - 8)}, {x: 0, y: height - Math.max(0, inset.bottom - 12), width, height: Math.max(0, inset.bottom - 12)}, {x: width - cw, y: height - controlsBottom - 56, width: cw, height: controlsBottom + 56}, ...(review ? [review] : [])]});
    // The button takes the first spot that leaves its node a full label; failing that, one that leaves a shortened label.
    let reviewBox = reviewSpots[0] ?? null, boxes = labelsFor(reviewBox);
    if (reviewFor && reviewBox) {
      const full = String(reviewFor.label || reviewFor.id), grade = list => { const b = list.find(x => x.id === reviewFor.id); return b ? (b.text === full ? 2 : 1) : 0; };
      let best = grade(boxes);
      for (const spot of reviewSpots.slice(1)) { if (best === 2) break; const trial = labelsFor(spot), g = grade(trial); if (g > best) { best = g; reviewBox = spot; boxes = trial; } }
    }
    const byId = new Map(nodes.map(n => [n.id, n]));
    if (phoneOverview()) boxes = nodes.filter(n => n.kind === 'Mission' && stateKey(n.state) === 'needs-you').slice(0, 1).map(n => {
      const full = String(n.label || n.id), x = n.x + n.radius + 10, available = width - x - 8;
      let text = full;
      while (text.length > 1 && (context ? context.measureText(text).width : text.length * 7.5) > available) text = text.slice(0, -2) + '…';
      return {id: n.id, x, y: n.y - 8, width: available, height: 20, text, rich: false, mandatory: true, size: 14};
    });
    const items = boxes.map(box => ({box, n: byId.get(box.id), meta: box.rich ? metaOf(byId.get(box.id)) : ''}));
    const labelSig = ({box, n, meta}) => `${box.rich}|${box.size}|${stateKey(n.state)}|${n.id === selected}|${box.text}|${meta}|${subOf(n)}`;
    const placeLabel = (rec, {box}) => {
      const meta = box.size * .68;
      for (const [name, value] of [['x', box.x], ['y', box.y], ['width', box.width], ['height', box.height]]) setAttr(rec.el, `data-${name}`, value);
      if (rec.meta) { setAttr(rec.meta, 'x', box.x + 2); setAttr(rec.meta, 'y', box.y + meta * 1.05); }
      setAttr(rec.title, 'x', box.x + 2); setAttr(rec.title, 'y', box.rich ? box.y + meta * 1.4 + box.size : box.y + box.size);
      if (rec.sub) { setAttr(rec.sub, 'x', box.x + 2); setAttr(rec.sub, 'y', box.y + meta * 1.4 + box.size * 1.95); }
    };
    const buildLabel = item => {
      const {box, n} = item, state = stateKey(n.state), meta = box.size * .68;
      const el = svgElement('g', {class: `am-label am-state-${words[state] ? state : 'idle'}${n.id === selected ? ' am-selected-label' : ''}`, 'data-node-id': n.id});
      const rec = {el, sig: labelSig(item), meta: box.rich ? svgElement('text', {class: 'am-label-meta', style: `font-size:${meta}px`}, item.meta) : null,
        title: svgElement('text', {class: 'am-label-title', style: `font-size:${box.size}px`}, box.text)};
      rec.sub = box.rich && subOf(n) ? svgElement('text', {class: 'am-label-sub', style: `font-size:${box.size * .72}px`}, subOf(n)) : null;
      if (rec.meta) el.append(rec.meta);
      el.append(rec.title);
      if (rec.sub) el.append(rec.sub);
      placeLabel(rec, item);
      return rec;
    };
    reconcile(labels, labelRecs, items, item => item.box.id, buildLabel, (rec, item) => {
      if (rec.sig !== labelSig(item)) Object.assign(rec, buildLabel(item)); else placeLabel(rec, item);
    });
    const placeReview = (rec, b) => setAttr(rec.el, 'transform', `translate(${f(b.x + b.width / 2)} ${f(b.y + b.height / 2)})`);
    reconcile(reviews, reviewRecs, reviewBox ? [reviewBox] : [], b => b.id, b => {
      const el = svgElement('g', {class: 'am-review am-state-needs-you', tabindex: 0, role: 'button', 'data-node-id': b.id, 'aria-label': `${T('Review')}: ${byId.get(b.id).label}`});
      el.append(svgElement('rect', {x: -56, y: -22, width: 112, height: 44, rx: 6}), svgElement('text', {x: -42, y: 5, class: 'am-review-label'}, T('Review')), svgElement('path', {d: 'M26 0h14m-5-5 5 5-5 5', class: 'am-review-arrow'}));
      el.addEventListener('click', () => emit('review', el.dataset.nodeId));
      el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); emit('review', el.dataset.nodeId); } });
      const rec = {el}; placeReview(rec, b); return rec;
    }, placeReview);
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
    syncHot();
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
  const calmRows = n => graph.nodes.filter(m => m.project === n.id && m.kind === 'Mission').map(m => ({label: m.label || m.id, state: words[stateKey(m.state)] ? stateKey(m.state) : 'idle', word: nodeWord(m)})).concat((graph.projects.find(p => p.id === n.id)?.captured || []).map(label => ({label, state: 'idle', word: T('Captured')})));
  function starMarkup(n) {
    const state = stateKey(n.state), colorState = words[state] ? state : 'idle', r = n.radius, body = ['Mission', 'Project', 'Execution'].includes(n.kind);
    if (options.calm && n.kind === 'Project') return panelMarkup(n, calmRows(n), T('No items yet'), T('items'));
    if (body) return bodyMarkup(n, n.kind === 'Mission' ? (state === 'done' ? 'check' : state === 'needs-you' ? 'doc-search' : 'doc') : ICON[n.kind]);
    const [tag, shape] = starShape(n.kind, r), attrs = Object.entries(shape).map(([key, value]) => `${key}="${typeof value === 'number' ? f(value) : value}"`).join(' ');
    return `<g class="am-star am-state-${colorState}" data-node-id="${esc(n.id)}"><${tag} ${attrs} class="am-body${['blocked', 'running', 'paused', 'idle'].includes(state) ? ' am-hollow' : ''}"/></g>`;
  }
  function drawStar(n) {
    const holder = svgElement('g');
    holder.innerHTML = starMarkup(n);
    const star = holder.firstElementChild, state = stateKey(n.state);
    driftVars(star, n.id);
    if (!options.calm && (state === 'needs-you' || state === 'running')) star.insertAdjacentHTML('afterbegin', `<circle class="am-ring" r="${f(n.radius + 4)}"/>`);
    return star;
  }
  function updateSummary() {
    summary.textContent = T(`${positions.length} nodes across ${graph.projects.length} projects. ${positions.filter(n => stateKey(n.state) === 'needs-you').length} need you. Tab through stars, Enter to select, arrow keys move by direction. Equivalent node table follows map controls.`);
  }
  function accent(...states) {
    const keys = states.map(stateKey);
    return keys.includes('needs-you') ? 'needs-you' : keys.includes('running') ? 'running' : 'none';
  }
  function drawCore() {
    const R = coreRadius(), p = coreStar(R, reachOf());
    core.setAttribute('transform', `translate(${centre.x} ${centre.y})`);
    coreMark.replaceChildren(svgElement('path', {d: p.threads, class: 'am-core-chords'}), svgElement('path', {d: p.spikes, class: 'am-core-thread'}), svgElement('path', {d: p.tips, class: 'am-core-dot'}));
    const ws = wordmarkSize(u, options.calm), base = R * reachOf() + ws * 1.9;
    wordmark.setAttribute('x', ws * .2); wordmark.setAttribute('y', base); wordmark.style.fontSize = `${ws}px`;
    tagline.style.display = phoneOverview() || width < 480 ? 'none' : ''; tagline.setAttribute('y', base + ws * 1.9); tagline.style.fontSize = `${ws * (options.calm ? .6 : .95)}px`; if (options.calm) tagline.style.letterSpacing = '.22em';
    runningText.setAttribute('y', base + ws * 3.6); runningText.style.fontSize = `${ws * .9}px`;
  }
  function render(previous = new Map(), arrivals = false, moved = true) {
    if (moved) { for (const marker of activePulses) marker.remove(); activePulses.clear(); }
    const projects = new Map((graph.projects || []).map(p => [p.id, p.label]));
    const groups = new Map();
    for (const n of positions) { const key = n.project || 'unassigned'; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(n); }
    const hubs = options.calm ? [] : phoneOverview() ? positions.map(n => ({project: n.id, mx: n.x, my: n.y})) : [...groups.keys()].sort().map(project => { const members = groups.get(project), hub = members.find(n => n.kind === 'Project'); return {project, mx: hub ? hub.x : members.reduce((t, n) => t + n.x, 0) / members.length, my: hub ? hub.y : members.reduce((t, n) => t + n.y, 0) / members.length}; });
    const patchSpoke = (rec, item) => setAttr(rec.el, 'd', `M${centre.x},${centre.y}L${item.mx},${item.my}`);
    reconcile(spokeLayer, spokeRecs, hubs, item => item.project, item => { const rec = {el: svgElement('path', {class: 'am-spoke'})}; patchSpoke(rec, item); return rec; }, patchSpoke);
    gridLayer.innerHTML = options.calm && positions.length ? gridMarkup(threadGrid(positions, {...centre, radius: coreRadius() * 1.1}, {box: coreKeepOut(width, height, u, inset, true).box, bounds: {left: 8, top: inset.top, right: width - 8, bottom: height - inset.bottom}})) : '';
    const byId = new Map(positions.map(n => [n.id, n]));
    const edges = [];
    for (const edge of graph.edges || []) {
      const a = byId.get(edge.from), b = byId.get(edge.to);
      if (a && b) edges.push({id: edgeId(edge), a, b, kind: String(edge.kind || 'relation').replace(/W/g, '')});
    }
    const freshEdges = [];
    // Relations are straight hairlines from rim to rim with a joint dot at each end.
    const patchEdge = (rec, {a, b, kind}) => {
      if (rec.ax !== a.x || rec.ay !== a.y || rec.bx !== b.x || rec.by !== b.y || rec.ar !== a.radius || rec.br !== b.radius) {
        const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1, ux = dx / d, uy = dy / d, ra = Math.min(a.radius, d / 2), rb = Math.min(b.radius, d / 2);
        const p = [a.x + ux * ra, a.y + uy * ra, b.x - ux * rb, b.y - uy * rb].map(f);
        setAttr(rec.line, 'd', `M${p[0]},${p[1]}L${p[2]},${p[3]}`); setAttr(rec.hot, 'd', `M${p[0]},${p[1]}L${p[2]},${p[3]}`);
        setAttr(rec.jointA, 'd', `M${p[0]},${p[1]}h0`); setAttr(rec.jointB, 'd', `M${p[2]},${p[3]}h0`);
        for (const [i, v] of [['--x0', p[0]], ['--y0', p[1]], ['--x1', p[2]], ['--y1', p[3]]]) rec.marker.style.setProperty(i, v + 'px');
        rec.ax = a.x; rec.ay = a.y; rec.bx = b.x; rec.by = b.y; rec.ar = a.radius; rec.br = b.radius;
      }
      if (rec.sa !== a.state || rec.sb !== b.state || rec.kind !== kind) {
        const acc = accent(a.state, b.state);
        setAttr(rec.el, 'class', `am-edge am-edge-${kind} am-accent-${acc}`);
        setAttr(rec.marker, 'display', acc === 'running' && !options.calm ? 'inline' : 'none');
        rec.sa = a.state; rec.sb = b.state; rec.kind = kind; rec.aid = a.id; rec.bid = b.id;
        hotEdge(rec);
      }
    };
    reconcile(edgeLayer, edgeRecs, edges, e => e.id, e => {
      const line = svgElement('path', {class: 'am-line'}), hot = svgElement('path', {class: 'am-line-hot'}), jointA = svgElement('path', {class: 'am-joint'}), jointB = svgElement('path', {class: 'am-joint'}), marker = svgElement('circle', {class: 'am-travel', r: 2.6, display: 'none'});
      const rec = {el: svgElement('g', {'data-edge-id': e.id}), line, hot, jointA, jointB, marker};
      rec.el.append(line, hot, jointA, jointB, marker);
      driftVars(jointA, e.a.id); driftVars(jointB, e.b.id);
      const t = driftOf(options.seed, e.id); marker.style.setProperty('--tp', Math.round(t.period / 2.4) + 'ms'); marker.style.setProperty('--td', Math.round(t.delay / 2.4) + 'ms');
      patchEdge(rec, e);
      if (arrivals && (!previous.has(e.a.id) || !previous.has(e.b.id))) freshEdges.push(rec.el);
      return rec;
    }, patchEdge);
    const arrived = [];
    const starSig = n => `${n.phone}|${n.state}|${n.kind}|${n.radius}${options.calm && n.kind === 'Project' ? '|' + calmRows(n).map(r => r.label + r.state).join(',') : ''}`;
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
      // A node lifts a little under the pointer and under keyboard focus.
      const lift = on => { starRecs.get(n.id)?.el.classList.toggle('am-lift', on); hovered = on ? n.id : hovered === n.id ? null : hovered; syncHot(); };
      rec.el.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') lift(true); }); rec.el.addEventListener('pointerleave', () => lift(false));
      rec.el.addEventListener('focus', () => lift(rec.el.matches(':focus-visible'))); rec.el.addEventListener('blur', () => lift(false));
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
    arrived.forEach((el, i) => animate(el, MOTION.appear, Math.min(i, 12) * 30, true));
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
    inset = {...INSET, ...(typeof options.inset === 'function' ? options.inset(w, h) : options.inset)};
    controlsBottom = inset.bottom > INSET.bottom ? inset.bottom + 8 : 12; controls.style.bottom = `${controlsBottom}px`;
    width = w; height = h; u = unit(w, h); centre = options.overview && !options.calm && w < 600 ? {x: w / 2, y: h * .32} : coreCentre(w, h, inset); host.dataset.phoneOverview = String(phoneOverview()); host.dataset.narrow = String(width < 480); svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    const css = getComputedStyle(host); serif = css.getPropertyValue('--am-serif').trim() || 'serif'; sans = css.getPropertyValue('--am-sans').trim() || 'sans-serif';
    drawCore();
    ambient.innerHTML = options.calm || phoneOverview() || options.ambient === false ? '' : (f => `<path d="${f.d}"/>${f.dots.map(([x, y]) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5"/>`).join('')}`)(ambientField(width, height, options.seed));
    camera = {x: 0, y: 0, k: 1}; positions = layoutScene(); render(); emit('resize', {width, height});
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
  const seen = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries => { visible = entries[entries.length - 1].isIntersecting; motion(); }) : null; seen?.observe(host);
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
      const key = graph.nodes.map(n => `${n.id}|${n.kind}|${n.project}|${n.weight}|${isCrystal(n)}|${phoneOverview() ? n.state : ''}`).join(';');
      const moved = key !== layoutKey;
      if (moved) positions = layoutScene();
      else { const byId = new Map(graph.nodes.map(n => [n.id, n])); positions = positions.map(p => ({...p, ...byId.get(p.id)})).sort((x, y) => String(x.id).localeCompare(String(y.id))); }
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
    setAmbient(on) { playing = on === true; if (!destroyed) motion(); },
    pulse(id) {
      const path = edgeRecs.get(id)?.line;
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
      destroyed = true; observer.disconnect(); seen?.disconnect(); media.removeEventListener('change', motion); document.removeEventListener('visibilitychange', motion); document.fonts?.removeEventListener('loadingdone', refit);
      for (const animation of host.getAnimations({subtree: true})) animation.cancel();
      pointers.clear(); activePulses.clear(); listeners.clear(); host.remove();
    }
  };
  resize(); if (options.graph) api.update(options.graph); return api;
}
