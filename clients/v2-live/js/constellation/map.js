import {driftOf, coreKeepOut, clamp, coversNode, overlaps, layout, layoutPhone, layoutCalm, coreRadius as coreSize, coreReach, coreScaleFor, taglineOn, satRank, INSET, wordmarkSize, placeLabels, nearestNeighbour, stateKey, unit, coreCentre} from './geometry.js';
import {bodyMarkup, ringMarkMarkup, worktreeMarkup, corePaths, coreTier, coreState} from './nodeart.js';
import {layoutRings, ringStep, LANES} from './rings.js';
import {expansion, expandCluster, sameLevels, pickFocus, receding, DRAW, MAX_K, MIN_K, OVERVIEW_MAX, REF, BUDGET} from './detail.js';
import {orderProjects} from './order.js';
import {panelMarkup, threadGrid, gridMarkup} from './scene.js';

export const MOTION = Object.freeze({appear: 160, relation: 240, label: 160, glide: 220, travel: 600, breath: 6000});
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
// `stable` leaves records that exist where they stand and appends new ones (used for the hit areas, where moving an element would drop its keyboard focus).
function reconcile(parent, cache, items, keyOf, build, patch, stable = false) {
  const seen = new Set();
  let cursor = parent.firstElementChild;
  for (const item of items) {
    const key = keyOf(item);
    seen.add(key);
    let rec = cache.get(key);
    const fresh = !rec;
    if (!rec) cache.set(key, rec = build(item));
    else { const old = rec.el; patch(rec, item); if (rec.el !== old) { if (old === cursor) cursor = old.nextElementSibling; old.remove(); } }
    if (stable) { if (fresh) parent.append(rec.el); continue; }
    if (rec.el === cursor) cursor = cursor.nextElementSibling; else parent.insertBefore(rec.el, cursor);
  }
  for (const [key, rec] of cache) if (!seen.has(key)) { rec.el.remove(); cache.delete(key); }
}
function starShape(kind, r) {
  if (kind === 'Decision') return ['path', {d: `M0,${-r * 1.3}L${r * 1.3},0L0,${r * 1.3}L${-r * 1.3},0Z`}];
  if (kind === 'Knowledge' || kind === 'Verification') return ['rect', {x: -r * .85, y: -r * .85, width: r * 1.7, height: r * 1.7, rx: 1}];
  if (kind === 'Idea') { const s = r * 1.35; return ['path', {d: `M0,${-s}Q0,0 ${s},0Q0,0 0,${s}Q0,0 ${-s},0Q0,0 0,${-s}Z`}]; }
  return ['circle', {r}];
}
export function createMap(container, options = {}) {
  const T = options.t || (x => x);
  const W = k => T(words[k] || k);
  const nodeWord = n => (n.word ? T(n.word) : W(stateKey(n.state)));
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
  const spokeLayer = svgElement('g', {class: 'am-spokes'}), gridLayer = svgElement('g', {class: 'am-grid'}), edgeLayer = svgElement('g', {class: 'am-edges'});
  const core = svgElement('g', {class: 'am-core am-state-core'});
  const nodeLayer = svgElement('g', {class: 'am-nodes'}), ghostLayer = svgElement('g', {class: 'am-ghosts'}), pulseLayer = svgElement('g', {class: 'am-pulses'});
  world.append(spokeLayer, gridLayer, edgeLayer, core, nodeLayer, ghostLayer, pulseLayer);
  const tagLayer = svgElement('g', {class: 'am-tags', 'aria-hidden': 'true'}), leaders = svgElement('g', {class: 'am-leaders', 'aria-hidden': 'true'}), labels = svgElement('g', {class: 'am-labels', 'aria-hidden': 'true'});
  const reviews = svgElement('g', {class: 'am-reviews'});
  const hits = svgElement('g', {class: 'am-hits'}), selectRing = svgElement('circle', {class: 'am-select-ring'});
  const coreMark = svgElement('g', {'data-core': 'static'});
  const wordmark = svgElement('text', {class: 'am-wordmark', 'text-anchor': 'middle'}, String(options.coreLabel ?? 'Archeus').toUpperCase());
  const tagline = svgElement('text', {class: 'am-tagline', 'text-anchor': 'middle'}, options.calm ? T('Understand · Plan · Do').toUpperCase() : T('Your projects. In context.'));
  const runningText = svgElement('text', {class: 'am-running', 'text-anchor': 'middle'});
  core.append(coreMark, wordmark, tagline, runningText);
  svg.append(title, summary, world, tagLayer, leaders, labels, hits, reviews);
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
  const card = element('div', 'am-card'); card.hidden = true; card.setAttribute('aria-hidden', 'true');
  // The focus caption: once the camera is in close it names the project in view (hover is never needed to know which project this is); a click opens its work.
  const focusCap = element('button', 'am-focuscap'); focusCap.type = 'button'; focusCap.hidden = true;
  host.append(svg, card, focusCap, controls, status, equivalent); container.append(host);
  let graph = {nodes: [], edges: [], projects: []}, positions = [], selected = null;
  let focusCapId = null, focusCapSig = '', controlsBottom = 12, inset = INSET, width = 1, height = 1, camera = {x: 0, y: 0, k: 1}, destroyed = false, u = 1, centre = {x: 0, y: 0}, serif = 'serif', sans = 'sans-serif';
  let reducedOverride = options.reducedMotion;
  let slots = new Map(), memory = new Map(), level = 0, projectOf = new Map(), hotCluster = null, hotEls = new Set(), hoverId = null, cardTimer = 0, graceTimer = 0, cardHide = 0;
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  const listeners = new Map(), activePulses = new Set(), pointers = new Map();
  const tagRecs = new Map(), starRecs = new Map(), hitRecs = new Map(), rowRecs = new Map(), spokeRecs = new Map(), edgeRecs = new Map(), labelRecs = new Map(), leaderRecs = new Map(), reviewRecs = new Map();
  let selectedEl = null, fullKey = '', visible = true, playing = options.playing === true, hovered = null, stopped = false, coreSig = '', coreTierNow = 'full', ringsOut = null;
  const laneLayer = svgElement('g', {class: 'am-lanes'}), laneRecs = new Map();
  world.prepend(laneLayer);
  let gesture = null;
  // Semantic zoom (detail.js): which projects are open and how far, the mission whose timeline is open, what each project says in detail, and the clusters that give way.
  let levels = new Map(), gLevel = 0, focusM = null, extra = {edges: [], open: new Map()}, receded = new Set(), pointerAt = null, flight = 0, counts = new Map(), baseCache = null, projOf = new Map(), kidsOf = new Map(), detailData = new Map(), eventData = new Map(), compact = [];
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  const emit = (event, detail) => { for (const fn of listeners.get(event) || []) fn(detail); };
  const isReduced = () => reducedOverride === true || (reducedOverride === undefined && media.matches);
  const isLive = () => options.live === true && options.fresh !== false && graph.nodes.some(n => stateKey(n.state) === 'running');
  // The Projects view (options.rings): lanes by state round the core, one mark per project (js/constellation/rings.js); the Network view lays the same projects out as clusters.
  const ringed = () => options.rings === true && !options.calm;
  const phoneOverview = () => options.overview && !options.calm && width < 600 && !options.rings;
  // The Network view groups by project: hubs on a ring of cells round the core (the calm scene and the phone keep their own layouts).
  const clustered = () => !options.calm && !phoneOverview();
  const coreFactor = () => (clustered() ? coreScaleFor(new Set(graph.nodes.map(n => n.project || 'unassigned')).size) : 1);
  // The zoom buttons stand in a column at the bottom right; no cell may sit under them.
  const controlsBox = () => ({x: width - 68, y: height - controlsBottom - 156, width: 68, height: 160});
  function layoutScene() {
    host.dataset.grouped = String(clustered());
    if (options.calm) return layoutCalm(graph, width, height, options.seed, inset);
    if (phoneOverview()) return layoutPhone(graph, width, height, options.seed, inset);
    if (ringed()) {
      // The ring layout (one mark per project) also only changes with the graph or the size. Its nodes come in attention order, which is the Tab order of the hit areas.
      const out = baseCache ?? (baseCache = layoutRings(ringInput(), width, height, inset, {memory, avoid: [controlsBox()]}));
      memory = out.memory; ringsOut = out; level = 0; host.dataset.dense = String(out.tier.name === 'dense'); host.dataset.tier = out.tier.name; host.dataset.scale = String(out.scale);
      const byId = new Map(out.nodes.map(n => [n.id, n]));
      compact = out.order.map(id => byId.get(id));
      return expandScene(compact);
    }
    ringsOut = null;
    // The compact layout only changes with the graph or the size: a level change reuses it.
    const out = baseCache ?? (baseCache = layout(graph, width, height, inset, {slots, memory, avoid: [controlsBox()]}));
    memory = out.memory; level = out.level; host.dataset.dense = String(level >= 5);
    compact = out.nodes;
    return expandScene(out.nodes);
  }
  // What the ring layout needs of a project: its lane (the worst state), all its missions, its worktrees; the busiest dozen running ones pulse.
  function ringInput() {
    const info = id => projectOf.get(id), busy = new Set(graph.nodes.filter(n => n.kind === 'Project' && stateKey(n.state) === 'running').sort((a, b) => (info(b.id)?.weight || 0) - (info(a.id)?.weight || 0) || String(a.id).localeCompare(String(b.id))).slice(0, 12).map(n => n.id));
    return graph.nodes.filter(n => n.kind === 'Project').map(n => ({...n, lane: stateKey(n.state), missions: info(n.id)?.total ?? 0, worktrees: info(n.id)?.worktrees?.length ?? 0, hub: true, cluster: n.id, rank: 8, pulse: busy.has(n.id)}));
  }
  const detailFor = id => { if (!detailData.has(id)) detailData.set(id, options.detail?.(id) || {}); return detailData.get(id); };
  const eventsFor = id => { if (!eventData.has(id)) eventData.set(id, options.events?.(id) || []); return eventData.get(id); };
  const wtNode = (w, project) => ({id: w.id, kind: 'Worktree', label: w.branch, project, state: w.tone, word: w.word, owner: w.owner, mission: w.mission, time: w.time, ownerWord: w.ownerWord});
  // Semantic zoom: each open project's own nodes (not its hub) are replaced by its detailed cluster, laid out round the same hub; the other projects keep the compact layout.
  function expandScene(base) {
    extra = {edges: [], open: new Map()}; host.dataset.level = String(gLevel);
    if (!levels.size) { host.dataset.detailNodes = '0'; receded = new Set(); return base; }
    const keep = coreKeepOut(width, height, u, inset, false, coreFactor()), ctl = controlsBox(), hubs = base.filter(n => n.hub);
    let nodes = base, left = BUDGET;
    for (const [id, lv] of levels) {
      const hub = hubs.find(n => n.cluster === id);
      if (!hub || left <= 0) continue;
      const p = projectOf.get(id), missions = graph.nodes.filter(n => n.kind === 'Mission' && (n.project || 'unassigned') === id);
      const blocked = (x, y, r) => Math.hypot(x - keep.x, y - keep.y) < keep.radius + r || coversNode(keep.box, {x, y, radius: r}, 0) || coversNode(ctl, {x, y, radius: r}, 0) || hubs.some(h => h.cluster !== id && Math.hypot(x - h.x, y - h.y) < h.radius + r + 6);
      const detail = lv >= 2 ? detailFor(id) : {}, kids = new Map(missions.map(m => [m.id, lv >= 2 ? detail[m.id] || [] : kidsOf.get(m.id) || []]));
      const ideas = (p?.ideaList || []).map(i => ({id: i.id, kind: 'Idea', label: i.title, project: id, state: 'idle', word: i.word}));
      const res = expandCluster({level: lv, key: id, hub: {x: hub.x, y: hub.y, tag: hub.tag, outward: Math.atan2(hub.y - keep.y, hub.x - keep.x)}, missions, worktrees: (p?.worktrees || []).map(w => wtNode(w, id)), kids, ideas,
        events: lv >= 3 && focusM && missions.some(m => m.id === focusM) ? eventsFor(focusM).map(e => ({...e, project: id})) : [], focusId: focusM, blocked, limit: left, lanes: ringed()});
      left -= res.nodes.length;
      nodes = nodes.filter(n => n.cluster !== id || n.hub).map(n => (n.hub && n.cluster === id ? {...n, ...res.hub, quiet: res.quiet, wtQuiet: res.wtQuiet, expanded: lv} : n)).concat(res.nodes);
      extra.edges.push(...res.edges); extra.open.set(id, {id, x: hub.x, y: hub.y, extent: res.extent});
    }
    receded = receding(hubs, [...extra.open.values()]);
    host.dataset.detailNodes = String(nodes.filter(n => n.detail).length);
    return nodes;
  }
  const coreRadius = () => phoneOverview() ? 28 : coreSize(u, options.calm, width) * coreFactor(), reachOf = () => coreReach(width, options.calm);
  // Ambient motion (drift, rings, travelling markers) runs only for a playing simulation, with full motion, a visible tab and a visible map; the calm scene has none.
  const ambientOn = () => playing && visible && !isReduced() && !document.hidden && !options.calm;
  function motion() {
    host.dataset.reduced = String(isReduced());
    host.dataset.ambient = ambientOn() ? 'on' : 'off';
    coreMark.dataset.core = isLive() && !document.hidden && !isReduced() ? 'breath' : 'static';
    // The static twin carries the core's working or stopped state as a word under the wordmark (the needs you thread is static and loses nothing) (the art itself is aria-hidden).
    const cf = coreFlags();
    runningText.textContent = !isReduced() ? '' : cf.stopped ? T('Stopped') : isLive() ? T(`${graph.nodes.filter(n => stateKey(n.state) === 'running').length} running`) : '';
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
    return positions.map(n => ({...n, x: n.x * camera.k + camera.x, y: n.y * camera.k + camera.y, radius: n.radius * camera.k + (stateKey(n.state) === 'needs-you' ? 7 : 4), rk: n.radius * camera.k}));
  }
  // A hub's tag stands centred under it, 4 px below its rim, in screen space (its width and height are pixels at any zoom).
  const tagRect = n => ({x: n.x - n.tag.width / 2, y: n.y + n.rk + 4, width: n.tag.width, height: n.tag.height});
  const inScene = b => b.x >= 0 && b.x + b.width <= width && b.y >= 0 && b.y + b.height <= height;
  function refreshOverlay() {
    world.setAttribute('transform', `translate(${camera.x} ${camera.y}) scale(${camera.k})`);
    syncCore();
    const nodes = screenNodes();
    const size = width < 360 ? 12 : width < 480 || clustered() ? 14 : clamp(Math.round(17 * u + 2), 15, 24), rich = width >= 700;
    if (context) context.font = `400 ${size}px ${serif}`;
    const k = camera.k, cx = centre.x * k + camera.x, cy = centre.y * k + camera.y, reach = (coreRadius() * reachOf() + 6) * k, below = (coreRadius() * reachOf() + wordmarkSize(u) * (width < 480 || !taglineOn(coreFactor()) ? 3 : 5)) * k;
    const hold = Math.max(reach, 62 * u * k), coreBox = {x: cx - hold, y: cy - reach, width: hold * 2, height: reach + below};
    const ctl = {x: width - 68, y: height - controlsBottom - 156, width: 68, height: 160}, grouped = clustered();
    // A hub's label stands under it and scales with the camera's position, not its size; below 0.8x the labels give way to the hub marks.
    const tagged = grouped && k >= .8 ? nodes.filter(n => n.hub && n.tag && !receded.has(n.cluster) && inScene(tagRect(n))) : [], tagBoxes = tagged.map(n => ({id: n.id, ...tagRect(n)}));
    // The caption takes the first corner that no tag, label slot, mark, the core or the controls occupy; with none free it stays away (the name is then on the map itself).
    const CAP = {width: 300, height: 60};
    let capBox = null, capNode = null;
    if (options.overview && grouped && k >= 1.3) {
      const mx = (inset.left + width - inset.right) / 2, my = (inset.top + height - inset.bottom) / 2, lim = Math.min(width, height) * .45;
      focusCapId = pickFocus(focusCapId, nodes.filter(n => n.hub).map(n => ({id: n.id, d: Math.hypot(n.x - mx, n.y - my)})).filter(c => c.d <= lim));
      capNode = nodes.find(n => n.id === focusCapId) || null;
      const corners = [[inset.left, inset.top + 8], [inset.left, height - inset.bottom - CAP.height - 8], [width - inset.right - CAP.width - 72, inset.top + 8]].map(([x, y]) => ({x, y, ...CAP}))
        .filter(b => b.x >= 8 && b.x + b.width <= width - 8 && b.y >= inset.top && b.y + b.height <= height - inset.bottom && !overlaps(b, coreBox, 6) && !overlaps(b, ctl, 4) && !tagBoxes.some(t => overlaps(b, t, 4)));
      // A corner clear of every mark first; failing that one that only covers marks (the caption is opaque, and no text is ever covered).
      if (capNode) capBox = corners.find(b => !nodes.some(o => coversNode(b, o, 4))) ?? corners[0] ?? null;
    } else focusCapId = null;
    const shortOf = text => (grouped && [...text].length > 24 ? [...text].slice(0, 23).join('').trimEnd() + '…' : text);
    const slotOf = n => slots.get(n.cluster) ?? 1e9, live = n => ['needs-you', 'running'].includes(stateKey(n.state));
    // Only the hubs, the selected node and the first few that need you or run carry a label; the rest speak on hover and focus.
    const onScreen = n => n.x > -10 && n.x < width + 10 && n.y > -10 && n.y < height + 10, deep = n => n.detail && onScreen(n) && !receded.has(n.cluster);
    const titled = n => n.kind === 'Mission' || n.kind === 'Worktree' || (['needs-you', 'running', 'blocked'].includes(stateKey(n.state)) && n.kind !== 'Event') || (n.kind === 'Event' && n.last);
    // The rings label by priority and size tier: all named at 12 projects or fewer (or when zoomed in), the ones that need you, are blocked or are busy at 40 or fewer, only the first needs you lane and a few blocked beyond.
    const ringLabelIds = () => {
      if (!ringed() || !ringsOut) return [];
      const tierName = k >= 1.3 ? 'named' : ringsOut.tier.name, on = nodes.filter(n => n.hub && n.lane && !n.expanded && !receded.has(n.cluster) && onScreen(n)), miss = n => projectOf.get(n.id)?.total || 0, st = n => stateKey(n.state);
      if (tierName === 'named') return on.map(n => n.id);
      if (tierName === 'mixed') { const run = on.filter(n => st(n) === 'running').map(miss).sort((a, b) => a - b), med = run[Math.floor(run.length / 2)] || 0; return on.filter(n => ['needs-you', 'blocked'].includes(st(n)) || (st(n) === 'running' && miss(n) >= med)).map(n => n.id); }
      const top = (state, limit, first) => on.filter(n => st(n) === state && (!first || n.laneNo === 0)).sort((a, b) => miss(b) - miss(a) || String(a.id).localeCompare(String(b.id))).slice(0, limit).map(n => n.id);
      return [...top('needs-you', 8, true), ...top('blocked', 4, false)];
    };
    const labelTier = ringed() && ringsOut ? (k >= 1.3 ? 'named' : ringsOut.tier.name) : '';
    const eligible = grouped ? new Set([selected, ...ringLabelIds(), ...nodes.filter(n => deep(n) && titled(n)).slice(0, 70).map(n => n.id), ...nodes.filter(n => !n.hub && !n.detail && live(n) && !receded.has(n.cluster)).sort((a, b) => slotOf(a) - slotOf(b) || satRank(a) - satRank(b) || String(a.id).localeCompare(String(b.id))).slice(0, [10, 10, 8, 6, 4][level] ?? 0).map(n => n.id)]) : null;
    const metaOf = n => kindWord(n).toUpperCase(), subOf = n => n.kind === 'Event' ? '' : n.kind === 'Project' ? (labelTier && n.lane ? nodeWord(n) + (labelTier === 'named' ? ' · ' + T(`${projectOf.get(n.id)?.total || 0} ${projectOf.get(n.id)?.total === 1 ? 'mission' : 'missions'}`) : '') : '') : n.kind === 'Worktree' ? `${nodeWord(n)} · ${T(n.ownerWord)}` : words[stateKey(n.state)] ? nodeWord(n) : n.state || T('Idle');
    const reviewFor = nodes.filter(n => n.kind === 'Mission' && stateKey(n.state) === 'needs-you').sort((a, b) => (a.id === selected ? -1 : b.id === selected ? 1 : slotOf(a) - slotOf(b) || String(a.id).localeCompare(String(b.id))))[0];
    // The button goes below, above, right or left of its node, whichever side clears every other node and the bands the headline and drawer own.
    const reviewSpots = reviewFor && width >= 480 && !phoneOverview() && options.review !== false ? [[-56, reviewFor.radius + 12], [-130, reviewFor.radius + 12], [8, reviewFor.radius + 12], [-56, -reviewFor.radius - 56], [-130, -reviewFor.radius - 56], [8, -reviewFor.radius - 56], [reviewFor.radius + 12, -22], [-reviewFor.radius - 124, -22], [-56, reviewFor.radius + 40], [-56, -reviewFor.radius - 84],
      ...[60, 100, 140].flatMap(d => Array.from({length: 12}, (_, i) => [Math.cos(i * Math.PI / 6) * (reviewFor.radius + d) - 56, Math.sin(i * Math.PI / 6) * (reviewFor.radius + d) - 22]))]
      .map(([dx, dy]) => ({id: reviewFor.id, x: reviewFor.x + dx, y: reviewFor.y + dy, width: 112, height: 44}))
      .filter(b => b.x >= 8 && b.x + b.width <= width - 8 && b.y >= inset.top && b.y + b.height <= height - inset.bottom && !overlaps(b, coreBox, 6) && !overlaps(b, ctl, 4) && !tagBoxes.some(t => overlaps(b, t, 4)) && !(capBox && overlaps(b, capBox, 4)) && !nodes.some(o => coversNode(b, o, 2))) : [];
    const measureMeta = text => { context.font = `500 ${size * .68}px ${sans}`; const w = context.measureText(text).width + text.length * size * .68 * .14; context.font = `400 ${size}px ${serif}`; return w; };
    const labelsFor = review => options.calm ? [] : placeLabels(grouped ? nodes.map(n => ({...n, label: shortOf(String(n.label || n.id))})) : nodes, width, height, {selected, size, rich: grouped ? false : rich, sub: grouped, only: eligible ?? undefined, metaOf, budget: ringed() ? 1e3 : undefined,
      priorityOf: ringed() ? n => (n.id === selected ? 1e4 : (({'needs-you': 5000, blocked: 3000, running: 1000})[stateKey(n.state)] || 0) + (projectOf.get(n.id)?.total || 0)) : undefined,
      outwardOf: ringed() ? n => { const dx = n.x - cx, dy = n.y - cy, d = Math.hypot(dx, dy) || 1; return [dx / d, dy / d]; } : undefined,
      subWidth: grouped && context ? n => { const s = subOf(n).toUpperCase(); context.font = `500 ${size * .72}px ${sans}`; const w = context.measureText(s).width + s.length * size * .72 * .1; context.font = `400 ${size}px ${serif}`; return w; } : undefined, measureMeta: context ? measureMeta : undefined,
      measure: context ? text => context.measureText(text).width : undefined,
      obstacles: [coreBox,
        {x: 0, y: 0, width, height: Math.max(0, inset.top - 8)}, {x: 0, y: height - Math.max(0, inset.bottom - 12), width, height: Math.max(0, inset.bottom - 12)}, ctl, ...tagBoxes, ...(capBox ? [capBox] : []), ...(review ? [review] : [])]});
    // The button takes the first spot that leaves its node a full label; failing that, one that leaves a shortened label.
    let reviewBox = reviewSpots[0] ?? null, boxes = labelsFor(reviewBox);
    if (reviewFor && reviewBox) {
      const full = shortOf(String(reviewFor.label || reviewFor.id)), grade = list => { const b = list.find(x => x.id === reviewFor.id); return b ? (b.text === full ? 2 : 1) : 0; };
      let best = grade(boxes);
      for (const spot of reviewSpots.slice(1)) { if (best === 2 || (eligible && !eligible.has(reviewFor.id))) break; const trial = labelsFor(spot), g = grade(trial); if (g > best) { best = g; reviewBox = spot; boxes = trial; } }
    }
    const byId = new Map(nodes.map(n => [n.id, n]));
    if (phoneOverview()) boxes = nodes.filter(n => n.kind === 'Mission' && stateKey(n.state) === 'needs-you').slice(0, 1).map(n => {
      const full = String(n.label || n.id), x = n.x + n.radius + 10, available = width - x - 8;
      let text = full;
      while (text.length > 1 && (context ? context.measureText(text).width : text.length * 7.5) > available) text = text.slice(0, -2) + '…';
      return {id: n.id, x, y: n.y - 8, width: available, height: 20, text, rich: false, mandatory: true, size: 14};
    });
    const items = boxes.map(box => ({box, n: byId.get(box.id), meta: box.rich ? metaOf(byId.get(box.id)) : ''}));
    const labelSig = ({box, n, meta}) => `${box.rich}|${box.sub}|${box.size}|${stateKey(n.state)}|${n.id === selected}|${box.text}|${meta}|${subOf(n)}`;
    const placeLabel = (rec, {box}) => {
      const meta = box.size * .68;
      for (const [name, value] of [['x', box.x], ['y', box.y], ['width', box.width], ['height', box.height]]) setAttr(rec.el, `data-${name}`, value);
      if (rec.meta) { setAttr(rec.meta, 'x', box.x + 2); setAttr(rec.meta, 'y', box.y + meta * 1.05); }
      setAttr(rec.title, 'x', box.x + 2); setAttr(rec.title, 'y', box.rich ? box.y + meta * 1.4 + box.size : box.y + box.size);
      if (rec.sub) { setAttr(rec.sub, 'x', box.x + 2); setAttr(rec.sub, 'y', box.rich ? box.y + meta * 1.4 + box.size * 1.95 : box.y + box.size * 2.15); }
    };
    const buildLabel = item => {
      const {box, n} = item, state = stateKey(n.state), meta = box.size * .68;
      const el = svgElement('g', {class: `am-label am-state-${words[state] ? state : 'idle'}${n.id === selected ? ' am-selected-label' : ''}`, 'data-node-id': n.id});
      const rec = {el, sig: labelSig(item), meta: box.rich ? svgElement('text', {class: 'am-label-meta', style: `font-size:${meta}px`}, item.meta) : null,
        title: svgElement('text', {class: 'am-label-title', style: `font-size:${box.size}px`}, box.text)};
      rec.sub = (box.rich || box.sub) && subOf(n) ? svgElement('text', {class: box.rich ? 'am-label-sub' : 'am-label-word', style: `font-size:${box.size * .72}px`}, box.rich ? subOf(n) : subOf(n).toUpperCase()) : null;
      if (rec.meta) el.append(rec.meta);
      el.append(rec.title);
      if (rec.sub) el.append(rec.sub);
      placeLabel(rec, item);
      return rec;
    };
    reconcile(labels, labelRecs, items, item => item.box.id, buildLabel, (rec, item) => {
      if (rec.sig !== labelSig(item)) Object.assign(rec, buildLabel(item)); else placeLabel(rec, item);
    });
    // A hub's label: its name in serif (with the state word when it needs you or runs), then the last thing Archeus did there and how many missions are folded away.
    const fitText = (text, max, font) => {
      if (!context || !(max > 0)) return text;
      context.font = font;
      let t = String(text);
      if (context.measureText(t).width <= max) return t;
      while (t.length > 1 && context.measureText(t + '…').width > max) t = t.slice(0, -1);
      return t.trimEnd() + '…';
    };
    const wtChip = n => { const c = n.expanded ? n.wtQuiet : projectOf.get(n.id)?.worktrees?.length; return c ? T(`+${c} ${c === 1 ? 'worktree' : 'worktrees'}`) : ''; };
    const tagSig = n => [n.label, stateKey(n.state), n.quiet, n.tag.width, n.lines, n.expanded, wtChip(n), projectOf.get(n.id)?.last?.text, projectOf.get(n.id)?.last?.time].join('|');
    const buildTag = n => {
      const p = projectOf.get(n.id), state = stateKey(n.state), w = n.tag.width, mid = w / 2, el = svgElement('g', {class: 'am-tag'});
      let word = n.lines && (state === 'needs-you' || state === 'running') ? W(state).toUpperCase() : '';
      const qOnly = n.quiet ? T(`+${n.quiet} quiet`) : '';
      // The chips are measured: the worktree count is dropped when it would leave the last action no room (the tag keeps its width).
      const chipW = text => (text ? (context ? (context.font = `400 11px ${sans}`, context.measureText(text).width) : text.length * 6.5) + 12 : 0);
      let quiet = [qOnly, wtChip(n)].filter(Boolean).join(' · ');
      if (w - chipW(quiet) < (n.lines === 2 ? 70 : 8)) quiet = qOnly;
      const line = (y, cls, ...parts) => { const t = svgElement('text', {class: cls, x: mid, y, 'text-anchor': 'middle'}); parts.forEach(([text, klass], i) => { if (text) t.append(svgElement('tspan', {...(klass ? {class: klass} : {}), ...(i ? {dx: 8} : {})}, text)); }); el.append(t); };
      if (n.lines === 0) line(11, 'am-tag-quiet', [n.quiet ? `+${n.quiet}` : '']);
      else {
        // A name cut to a stub leaves no room for the state word (the hub's own mark still says it): the word is dropped rather than drawn over the name.
        const name = fitText(n.label || n.id, w - (word ? 84 : 0), `400 16px ${serif}`);
        if (word && context && context.measureText(name).width > w - 84 + 1) word = '';
        line(16, 'am-tag-name', [name], [word, `am-tag-word am-state-${state}`]);
        if (n.lines === 2) line(34, 'am-tag-sub', [fitText(p?.last ? `${p.last.time} · ${p.last.text}` : p?.total === 0 ? T('No missions yet') : '', w - chipW(quiet), `400 12px ${sans}`)], [quiet, 'am-tag-quiet']);
        else if (quiet) line(31, 'am-tag-quiet', [quiet]);
      }
      return {el, sig: tagSig(n)};
    };
    const placeTag = (rec, n) => { const r = tagRect(n); setAttr(rec.el, 'transform', `translate(${f(r.x)} ${f(r.y)})`); };
    reconcile(tagLayer, tagRecs, tagged, n => n.id, n => { const rec = buildTag(n); placeTag(rec, n); return rec; }, (rec, n) => { if (rec.sig !== tagSig(n)) Object.assign(rec, buildTag(n)); placeTag(rec, n); });
    if (hotCluster !== null) setHot(hotCluster);
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
    for (const n of nodes) {
      const rec = hitRecs.get(n.id);
      setAttr(rec.el, 'transform', `translate(${n.x} ${n.y})`);
      setAttr(rec.circle, 'r', hitR(n));
      setAttr(rec.el, 'aria-pressed', n.id === selected);
    }
    syncHot();
    const star = starRecs.get(selected)?.el ?? null;
    if (selectedEl && selectedEl !== star) selectedEl.classList.remove('am-selected');
    selectRing.remove();
    if (star) { star.classList.add('am-selected'); selectRing.setAttribute('r', positions.find(p => p.id === selected).radius + 11 / k); star.append(selectRing); }
    selectedEl = star;
    const missing = nodes.filter(n => (n.id === selected || (eligible ? eligible.has(n.id) && stateKey(n.state) === 'needs-you' : stateKey(n.state) === 'needs-you')) && !boxes.some(b => b.id === n.id));
    host.dataset.labelOverflow = String(missing.length);
    status.textContent = missing.length ? T(`${missing.length} priority labels cannot fit. Full labels available in node table.`) : '';
    paintFocusCap(capBox, capNode);
  }
  function paintFocusCap(box, n) {
    if (!box || !n) { focusCap.hidden = true; focusCapSig = ''; return; }
    const p = projectOf.get(n.id), word = nodeWord(n), count = p?.total ? T(`${p.total} ${p.total === 1 ? 'mission' : 'missions'}`) : '', sig = [n.id, n.label, stateKey(n.state), word, count].join('|');
    if (sig !== focusCapSig) {
      focusCapSig = sig;
      focusCap.setAttribute('aria-label', `${T('Project')}: ${n.label || n.id}, ${word}${count ? ', ' + count : ''}. ${T('Open work')}`);
      focusCap.dataset.nodeId = n.id;
      focusCap.replaceChildren(element('span', 'am-cap-kind', T('Project')), element('span', 'am-cap-name', String(n.label || n.id)), element('span', `am-cap-sub am-state-${words[stateKey(n.state)] ? stateKey(n.state) : 'idle'}`, [word, count].filter(Boolean).join(' · ')));
    }
    focusCap.style.left = f(box.x) + 'px'; focusCap.style.top = f(box.y) + 'px'; focusCap.hidden = false;
  }
  focusCap.addEventListener('click', () => { if (focusCap.dataset.nodeId) emit('select', focusCap.dataset.nodeId); });
  // A mark answers a pointer within 22 px (24 on a narrow scene, 12 on the dense rings whose marks are 28 px apart), a detailed one within its own radius or 9 px.
  const hitR = n => (n.detail ? Math.max(9, n.radius) : Math.max(ringed() && ringsOut?.tier.name === 'dense' && camera.k < 1.6 ? 12 : width < 480 ? 24 : 22, n.radius));
  function choose(id, reveal = false) {
    if (id !== null && !positions.some(n => n.id === id) && !graph.nodes.some(n => n.id === id)) return;
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
    // Hubs, worktrees and the marks of a detailed cluster are drawn at a design radius and scaled to the laid out one: a small mark is the same picture as a big one.
    if (n.art && n.art !== n.radius) return starMarkup({...n, radius: n.art, art: 0}).replace(/^(<g[^>]*>)([\s\S]*)<\/g>$/, `$1<g transform="scale(${f(n.radius / n.art)})">$2</g></g>`);
    const state = stateKey(n.state), colorState = words[state] ? state : 'idle', r = n.radius, body = ['Mission', 'Project', 'Execution'].includes(n.kind);
    if (options.calm && n.kind === 'Project') return panelMarkup(n, calmRows(n), T('No items yet'), T('items'));
    if (n.hub) return ringMarkMarkup(n.expanded ? {...n, worktrees: 0} : n);
    if (n.kind === 'Worktree') return worktreeMarkup(n);
    if (body) return bodyMarkup(n, n.kind === 'Mission' ? (state === 'done' ? 'check' : state === 'needs-you' ? 'doc-search' : 'doc') : ICON[n.kind]);
    const [tag, shape] = starShape(n.kind, r), attrs = Object.entries(shape).map(([key, value]) => `${key}="${typeof value === 'number' ? f(value) : value}"`).join(' ');
    return `<g class="am-star am-state-${colorState}" data-node-id="${esc(n.id)}"><${tag} ${attrs} class="am-body${['blocked', 'running', 'paused', 'idle'].includes(state) ? ' am-hollow' : ''}"/></g>`;
  }
  function drawStar(n) {
    const holder = svgElement('g');
    holder.innerHTML = starMarkup(n);
    const star = holder.firstElementChild, state = stateKey(n.state);
    driftVars(star, n.id);
    if (!options.calm && (state === 'needs-you' || state === 'running') && (!n.detail || n.kind === 'Mission') && (!ringed() || !n.hub || n.pulse)) (n.art ? star.firstElementChild : star).insertAdjacentHTML('afterbegin', `<circle class="am-ring am-state-${state}" r="${f((n.art || n.radius) + 4)}"/>`);
    return star;
  }
  function updateSummary() {
    const cf = coreFlags(), word = cf.stopped ? 'is stopped' : cf.needsYou ? 'needs you' : cf.running ? 'is working' : 'is calm';
    summary.textContent = T(`${graph.nodes.length} nodes across ${graph.projects.length} projects. ${graph.nodes.filter(n => stateKey(n.state) === 'needs-you').length} need you.`) + ' ' + T(`Archeus ${word}.`) + ' ' + T(ringed() ? 'Tab through the projects in the order of the lanes, arrow keys walk along a lane and between lanes, Enter to select. Equivalent node table follows map controls.' : 'Tab through stars, Enter to select, arrow keys move by direction. Equivalent node table follows map controls.');
  }
  function accent(...states) {
    const keys = states.map(stateKey);
    return keys.includes('needs-you') ? 'needs-you' : keys.includes('running') ? 'running' : 'none';
  }
  // The core mark: its size tier follows the camera (hysteresis in coreTier) and its state marks follow the work; it is only rebuilt when one of them changes.
  const coreFlags = () => ({stopped, needsYou: graph.nodes.some(n => n.kind !== 'Project' && stateKey(n.state) === 'needs-you'), running: graph.nodes.some(n => n.kind !== 'Project' && stateKey(n.state) === 'running')});
  function syncCore() {
    const R = coreRadius(), reach = reachOf(), flags = coreFlags();
    coreTierNow = coreTier(R * reach * camera.k, coreTierNow);
    const sig = [f(R), reach, coreTierNow, flags.stopped, flags.needsYou, flags.running].join('|');
    if (sig === coreSig) return;
    coreSig = sig;
    coreMark.replaceChildren(...corePaths(R, reach, {tier: coreTierNow, ...flags}).map(q => {
      const el = svgElement(q.t || 'path', q.t ? {class: q.c, r: q.r} : {class: q.c, d: q.d});
      if (q.x1 !== undefined) { for (const [k, v] of [['--x0', 0], ['--y0', 0], ['--x1', q.x1], ['--y1', q.y1]]) el.style.setProperty(k, v + 'px'); }
      return el;
    }));
    coreMark.dataset.state = flags.stopped ? 'stopped' : flags.running ? 'working' : flags.needsYou ? 'needs-you' : 'calm'; coreMark.dataset.needs = String(flags.needsYou && !flags.stopped);
    motion();
  }
  function drawCore() {
    const R = coreRadius();
    core.setAttribute('transform', `translate(${centre.x} ${centre.y})`);
    coreSig = ''; syncCore();
    const ws = wordmarkSize(u, options.calm), base = R * reachOf() + ws * 1.9;
    wordmark.setAttribute('x', ws * .2); wordmark.setAttribute('y', base); wordmark.style.fontSize = `${ws}px`;
    tagline.style.display = phoneOverview() || width < 480 || !taglineOn(coreFactor()) ? 'none' : ''; tagline.setAttribute('y', base + ws * 1.9); tagline.style.fontSize = `${ws * (options.calm ? .6 : .95)}px`; if (options.calm) tagline.style.letterSpacing = '.22em';
    runningText.setAttribute('y', base + ws * 3.6); runningText.style.fontSize = `${ws * .9}px`; runningText.style.display = phoneOverview() ? 'none' : '';
  }
  // glide: a layout step (a level change, a new project, the Details sheet) moves the nodes that stay by transform; the edges, which are redrawn at once, fade in once the nodes are on the way.
  function render(previous = new Map(), arrivals = false, moved = true, glide = false) {
    glide = glide && !isReduced() && !document.hidden && typeof Element.prototype.animate === 'function';
    if (moved) { for (const marker of activePulses) marker.remove(); activePulses.clear(); }
    const projects = new Map((graph.projects || []).map(p => [p.id, p.label]));
    const graphHubs = positions.filter(n => n.hub).length;
    const hubs = options.calm || ringed() ? [] : phoneOverview() ? positions.map(n => ({project: n.id, mx: n.x, my: n.y})) : positions.filter(n => n.hub && (graphHubs <= 24 || ['needs-you', 'running'].includes(stateKey(n.state)))).map(n => ({project: n.cluster, mx: n.x, my: n.y}));
    const patchSpoke = (rec, item) => setAttr(rec.el, 'd', `M${centre.x},${centre.y}L${item.mx},${item.my}`);
    reconcile(spokeLayer, spokeRecs, hubs, item => item.project, item => { const rec = {el: svgElement('path', {class: 'am-spoke'})}; patchSpoke(rec, item); return rec; }, patchSpoke);
    // The lanes: thin dotted ellipses in the state colour, no text on or beside them (state is read from colour, dash, the marks' own labels and the list).
    const patchLane = (rec, l) => { for (const [k, v] of [['cx', centre.x], ['cy', centre.y], ['rx', f(l.rx)], ['ry', f(l.ry)]]) setAttr(rec.el, k, v); };
    reconcile(laneLayer, laneRecs, ringed() && ringsOut ? ringsOut.lanes : [], l => `${l.state}:${l.n}`, l => { const rec = {el: svgElement('ellipse', {class: `am-lane am-lane-${l.state} am-state-${l.state}`})}; patchLane(rec, l); return rec; }, patchLane);
    gridLayer.innerHTML = options.calm && positions.length ? gridMarkup(threadGrid(positions, {...centre, radius: coreRadius() * 1.1}, {box: coreKeepOut(width, height, u, inset, true).box, bounds: {left: 8, top: inset.top, right: width - 8, bottom: height - inset.bottom}})) : '';
    const byId = new Map(positions.map(n => [n.id, n]));
    // A lit cluster grows 4% about its hub (CSS scale, origin from --hx/--hy), so every member and edge carries its hub's place.
    const hubAt = new Map(positions.filter(n => n.hub).map(n => [n.cluster, n]));
    const edges = [];
    for (const edge of [...(graph.edges || []).filter(e => !extra.open.has(projOf.get(e.from))), ...extra.edges]) {
      const a = byId.get(edge.from), b = byId.get(edge.to);
      if (a && b) edges.push({id: edgeId(edge), a, b, kind: String(edge.kind || 'relation').replace(/W/g, '')});
    }
    const freshEdges = [];
    // Relations are straight hairlines from rim to rim with a joint dot at each end.
    const patchEdge = (rec, {a, b, kind}) => {
      const hub = hubAt.get(a.cluster) ?? a;
      if (rec.hx !== hub.x || rec.hy !== hub.y) { rec.el.style.setProperty('--hx', f(hub.x) + 'px'); rec.el.style.setProperty('--hy', f(hub.y) + 'px'); rec.hx = hub.x; rec.hy = hub.y; }
      if (rec.ax !== a.x || rec.ay !== a.y || rec.bx !== b.x || rec.by !== b.y || rec.ar !== a.radius || rec.br !== b.radius) {
        const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1, ux = dx / d, uy = dy / d, ra = Math.min(a.radius, d / 2), rb = Math.min(b.radius, d / 2);
        const p = [a.x + ux * ra, a.y + uy * ra, b.x - ux * rb, b.y - uy * rb].map(f);
        setAttr(rec.line, 'd', `M${p[0]},${p[1]}L${p[2]},${p[3]}`); setAttr(rec.hot, 'd', `M${p[0]},${p[1]}L${p[2]},${p[3]}`);
        setAttr(rec.jointA, 'd', `M${p[0]},${p[1]}h0`); setAttr(rec.jointB, 'd', `M${p[2]},${p[3]}h0`);
        for (const [i, v] of [['--x0', p[0]], ['--y0', p[1]], ['--x1', p[2]], ['--y1', p[3]]]) rec.marker.style.setProperty(i, v + 'px');
        rec.ax = a.x; rec.ay = a.y; rec.bx = b.x; rec.by = b.y; rec.ar = a.radius; rec.br = b.radius;
      }
      if (rec.sa !== a.state || rec.sb !== b.state || rec.kind !== kind) {
        const acc = b.detail && (a.hub || a.kind === 'Worktree') ? accent(b.state) : accent(a.state, b.state);
        setAttr(rec.el, 'class', `am-edge am-edge-${kind} am-accent-${acc}`);
        setAttr(rec.marker, 'display', acc === 'running' && !options.calm ? 'inline' : 'none');
        rec.sa = a.state; rec.sb = b.state; rec.kind = kind; rec.aid = a.id; rec.bid = b.id;
        hotEdge(rec);
      }
    };
    reconcile(edgeLayer, edgeRecs, edges, e => e.id, e => {
      const line = svgElement('path', {class: 'am-line'}), hot = svgElement('path', {class: 'am-line-hot'}), jointA = svgElement('path', {class: 'am-joint'}), jointB = svgElement('path', {class: 'am-joint'}), marker = svgElement('path', {class: 'am-travel', d: 'M0,0h0', display: 'none'});
      const rec = {el: svgElement('g', {'data-edge-id': e.id}), line, hot, jointA, jointB, marker};
      rec.el.append(line, hot, jointA, jointB, marker);
      driftVars(jointA, e.a.id); driftVars(jointB, e.b.id);
      const t = driftOf(options.seed, e.id); marker.style.setProperty('--tp', Math.round(t.period / 2.4) + 'ms'); marker.style.setProperty('--td', Math.round(t.delay / 2.4) + 'ms');
      patchEdge(rec, e);
      if (arrivals && (!previous.has(e.a.id) || !previous.has(e.b.id))) freshEdges.push(rec.el);
      return rec;
    }, patchEdge);
    const arrived = [];
    const starSig = n => `${n.phone}|${n.state}|${n.kind}|${n.radius}|${n.art}|${n.lane}|${n.worktrees}|${n.pulse}|${n.expanded}|${n.tangent}${options.calm && n.kind === 'Project' ? '|' + calmRows(n).map(r => r.label + r.state).join(',') : ''}`;
    const placeStar = (rec, n) => {
      const hub = hubAt.get(n.cluster) ?? n;
      if (rec.x !== n.x || rec.y !== n.y || rec.hx !== hub.x || rec.hy !== hub.y) { setAttr(rec.el, 'transform', `translate(${f(n.x)} ${f(n.y)})`); rec.el.style.setProperty('--hx', f(hub.x) + 'px'); rec.el.style.setProperty('--hy', f(hub.y) + 'px'); rec.x = n.x; rec.y = n.y; rec.hx = hub.x; rec.hy = hub.y; }
      rec.r = n.radius;
    };
    const buildStar = n => { const rec = {el: drawStar(n), sig: starSig(n)}; placeStar(rec, n); if (arrivals) arrived.push(rec.el); return rec; };
    // A mark that changes size with the level fades in from its old place; one that only moves glides.
    const glideStar = (el, from, n) => el.animate([{transform: `translate(${f(from.x)}px, ${f(from.y)}px)`, opacity: from.r !== n.radius ? .3 : 1}, {transform: `translate(${f(n.x)}px, ${f(n.y)}px)`, opacity: 1}], {duration: MOTION.glide, easing: 'cubic-bezier(.65, 0, .35, 1)'});
    // Marks that leave with a level change fade out where they stood (a clone, 160 ms), so a level is a cross-fade and not a cut.
    if (glide) { const keepIds = new Set(positions.map(n => n.id)); let ghosts = 0; for (const [id, rec] of starRecs) if (!keepIds.has(id) && rec.x !== undefined && ghosts++ < 40) { const ghost = rec.el.cloneNode(true); ghost.classList.remove('am-in', 'am-lift'); ghostLayer.append(ghost); const a = ghost.animate([{opacity: 1}, {opacity: 0}], {duration: MOTION.appear, easing: 'ease-out'}); a.onfinish = a.oncancel = () => ghost.remove(); } }
    reconcile(nodeLayer, starRecs, positions, n => n.id, buildStar, (rec, n) => {
      const was = {x: rec.x, y: rec.y, r: rec.r};
      if (rec.sig !== starSig(n)) { Object.assign(rec, buildStar(n)); rec.x = rec.y = rec.hx = rec.hy = undefined; placeStar(rec, n); } else placeStar(rec, n);
      if (glide && was.x !== undefined && (was.x !== n.x || was.y !== n.y || was.r !== n.radius)) glideStar(rec.el, was, n);
    });
    if (glide) for (const layer of [edgeLayer, spokeLayer]) layer.animate([{opacity: 0}, {opacity: 0, offset: .55}, {opacity: 1}], {duration: MOTION.glide, easing: 'linear'});
    const placeOf = n => projects.get(n.project) || n.project || T('Unassigned');
    const stateOf = n => { const state = stateKey(n.state); return words[state] ? nodeWord(n) : state; };
    const same = (rec, n) => rec.stamped && rec.label === n.label && rec.kind === n.kind && rec.state === n.state && rec.place === placeOf(n);
    const stamp = (rec, n) => { rec.stamped = true; rec.label = n.label; rec.kind = n.kind; rec.state = n.state; rec.place = placeOf(n); };
    const ringAria = n => {
      const p = projectOf.get(n.id), ofState = ringsOut.lanes.filter(l => l.state === n.state).length, w = p?.worktrees?.length || 0;
      return [n.label || n.id, kindWord(n), stateOf(n), T(`lane ${n.laneNo + 1} of ${ofState} for ${W(stateKey(n.state))}`), T(`${p?.total || 0} ${p?.total === 1 ? 'mission' : 'missions'}`), ...(w ? [T(`${w} ${w === 1 ? 'worktree' : 'worktrees'}`)] : [])].join(', ');
    };
    const patchHit = (rec, n) => {
      setAttr(rec.el, 'tabindex', !clustered() || n.hub || (!n.detail && ['needs-you', 'running'].includes(stateKey(n.state))) ? 0 : -1);
      if (ringed() && n.hub && n.lane) { const label = ringAria(n); if (rec.aria !== label) { setAttr(rec.el, 'aria-label', label); rec.aria = label; } return; }
      if (same(rec, n)) return; setAttr(rec.el, 'aria-label', `${n.label || n.id}, ${kindWord(n)}, ${stateOf(n)}, ${placeOf(n)}`); stamp(rec, n);
    };
    reconcile(hits, hitRecs, positions, n => n.id, n => {
      const circle = svgElement('circle', {r: 22}), rec = {el: svgElement('g', {tabindex: 0, role: 'button', class: 'am-hit', 'data-node-id': n.id}), circle};
      rec.el.append(circle);
      rec.el.addEventListener('focus', () => { if (rec.el.matches(':focus-visible')) hoverTo(n.id, true); }); rec.el.addEventListener('blur', () => hoverTo(null));
      patchHit(rec, n);
      return rec;
    }, patchHit, !ringed() || hits.contains(document.activeElement));
    const patchRow = (rec, n) => {
      if (same(rec, n)) return;
      stamp(rec, n);
      setText(rec.button, String(n.label || n.id)); setText(rec.cells[0], kindWord(n)); setText(rec.cells[1], stateOf(n)); setText(rec.cells[2], placeOf(n));
    };
    const detailIds = new Set(positions.filter(n => n.detail).map(n => n.id));
    const listed = [...graph.nodes.filter(n => !detailIds.has(n.id)), ...positions.filter(n => n.detail && n.kind !== 'Event')], byListed = new Map(listed.map(n => [n.id, n]));
    reconcile(body, rowRecs, ringed() && ringsOut ? [...ringsOut.order.map(id => byListed.get(id)).filter(Boolean), ...listed.filter(n => !ringsOut.order.includes(n.id))] : listed, n => n.id, n => {
      const button = element('button'), first = element('td'), rec = {el: element('tr'), button, cells: [element('td'), element('td'), element('td')]};
      button.type = 'button'; first.append(button); rec.el.dataset.nodeId = n.id; rec.el.append(first, ...rec.cells);
      patchRow(rec, n);
      return rec;
    }, patchRow);
    arrived.slice(0, 80).forEach((el, i) => animate(el, MOTION.appear, Math.min(i, 12) * 30, true));
    for (const el of freshEdges) animate(el, MOTION.relation);
    updateSummary();
    applyRecede();
    refreshOverlay(); motion();
    if (arrivals) animate(labels, MOTION.label);
  }
  // Hover and focus: the node lifts, its project's cluster stays lit and the rest dims (100 ms in, 180 ms out, see map.css); the preview card opens after a 180 ms dwell, at once on focus.
  // A cluster that an open project has grown over gives way (opacity only, the existing 180 ms transition).
  function applyRecede() {
    const of = new Map(positions.map(n => [n.id, n.cluster]));
    for (const n of positions) starRecs.get(n.id)?.el.classList.toggle('am-recede', receded.has(n.cluster));
    for (const rec of edgeRecs.values()) rec.el.classList.toggle('am-recede', receded.has(of.get(rec.aid)));
    for (const [key, rec] of spokeRecs) rec.el.classList.toggle('am-recede', receded.has(key));
    for (const [id, rec] of tagRecs) rec.el.classList.toggle('am-recede', receded.has(of.get(id)));
  }
  function setHot(cluster) {
    hotCluster = cluster;
    if (cluster === null) delete host.dataset.hot; else host.dataset.hot = 'on';
    const next = new Set(), inside = new Set();
    if (cluster !== null) {
      for (const n of positions) if (n.cluster === cluster) { inside.add(n.id); next.add(starRecs.get(n.id)?.el); next.add(labelRecs.get(n.id)?.el); if (n.hub) next.add(tagRecs.get(n.id)?.el); }
      for (const rec of edgeRecs.values()) if (inside.has(rec.aid) && inside.has(rec.bid)) next.add(rec.el);
      next.add(spokeRecs.get(cluster)?.el);
    }
    for (const el of hotEls) if (el && !next.has(el)) el.classList.remove('am-in');
    for (const el of next) el?.classList.add('am-in');
    hotEls = next;
  }
  function placeCard(n) {
    const p = projectOf.get(n.cluster), state = stateKey(n.state), at = screenNodes().find(m => m.id === n.id);
    if (!at) return;
    const wt = n.kind === 'Worktree', line = wt ? (n.time ? `${T('Last activity')} ${n.time}` : '') : p?.last ? `${p.last.time} · ${p.last.text}` : '', kind = n.hub ? T('Project') : n.kind === 'Execution' ? T('Agent execution') : T(n.kind || 'Node');
    const place = wt ? `${T(n.ownerWord)} · ${n.mission || T('No mission')}` : n.hub ? `${p?.code ?? ''}${p?.total ? ' · ' + T(`${p.total} ${p.total === 1 ? 'mission' : 'missions'}`) : ''}` : p?.label || '';
    card.replaceChildren(element('p', 'am-card-kind', kind), element('p', 'am-card-name', n.label || n.id), element('p', `am-card-state am-state-${words[state] ? state : 'idle'}`, words[state] ? W(state) : String(n.state || '')),
      ...(place ? [element('p', 'am-card-line', place)] : []), ...(line ? [element('p', 'am-card-last', line)] : []), ...(n.hub || n.kind === 'Mission' ? [element('p', 'am-card-act', n.hub ? T('Open work') : T('Open mission'))] : []));
    clearTimeout(cardHide); card.classList.remove('am-on'); card.hidden = false;
    const cw = card.offsetWidth, ch = card.offsetHeight, nodes = screenNodes(), k = camera.k;
    // The card stands clear of the node (radius + 16 px), preferably on the side away from the core, flipping to any side where it
    // stays in the scene, clears the zoom column and the dock band, and covers neither the node, its label nor its project's other nodes.
    const region = {x: 8, y: Math.max(8, inset.top), r: width - 8, b: Math.max(inset.top + ch, height - inset.bottom)};
    const own = nodes.filter(m => m.cluster === n.cluster), clear = at.radius + 12;
    const boxes = [{x: width - 68 - 8, y: height - controlsBottom - 156 - 8, width: 68 + 16, height: 160 + 16},
      ...own.flatMap(m => [labelRecs.get(m.id)?.el, m.hub && tagRecs.get(m.id)?.el].filter(Boolean).map(el => (el.dataset.x ? {x: +el.dataset.x, y: +el.dataset.y, width: +el.dataset.width, height: +el.dataset.height} : m.tag && tagRect(m))).filter(Boolean))];
    // Other projects' labels, nodes and the core are priced lower: the card may cross them when nothing else fits, but prefers not to.
    const others = [...labelRecs.values()].map(r => r.el).filter(el => el.dataset.x && !own.some(m => m.id === el.dataset.nodeId)).map(el => ({x: +el.dataset.x, y: +el.dataset.y, width: +el.dataset.width, height: +el.dataset.height}))
      .concat(nodes.filter(m => m.hub && m.cluster !== n.cluster && m.tag && tagRecs.has(m.id)).map(tagRect));
    const coreAt = {x: centre.x * k + camera.x, y: centre.y * k + camera.y, r: (coreRadius() * reachOf() + 6) * k};
    const gapTo = (b, x, y) => Math.hypot(Math.max(b.x - x, 0, x - b.x - b.width), Math.max(b.y - y, 0, y - b.y - b.height));
    // Every spot on a 12 px grid inside the region is priced: a hard price for sitting nearer the node than radius + 16, for covering its project's other nodes or
    // any label, and a soft one for distance from the ideal spot (straight out from the core, just clear of the node). The cheapest wins.
    const ax = at.x - (centre.x * k + camera.x), ay = at.y - (centre.y * k + camera.y), al = Math.hypot(ax, ay) || 1, ux = ax / al, uy = ay / al;
    const ideal = {x: at.x + ux * (clear + (Math.abs(ux) * cw + Math.abs(uy) * ch) / 2), y: at.y + uy * (clear + (Math.abs(ux) * cw + Math.abs(uy) * ch) / 2)};
    let best = null;
    for (let y = region.y; y <= Math.max(region.y, region.b - ch) + 1; y += 12) for (let x = region.x; x <= Math.max(region.x, region.r - cw) + 1; x += 12) {
      const b = {x, y, width: cw, height: ch};
      let cost = Math.hypot(x + cw / 2 - ideal.x, y + ch / 2 - ideal.y) * .5 + 400 * Math.max(0, clear - gapTo(b, at.x, at.y));
      for (const m of own) cost += 40 * Math.max(0, m.radius + 4 - gapTo(b, m.x, m.y));
      if (boxes.some(o => overlaps(b, o, 6))) cost += 800;
      cost += 6 * Math.max(0, coreAt.r - gapTo(b, coreAt.x, coreAt.y)) + 120 * others.filter(o => overlaps(b, o, 4)).length + 3 * nodes.reduce((s, m) => s + (m.cluster === n.cluster ? 0 : Math.max(0, m.radius + 2 - gapTo(b, m.x, m.y))), 0);
      if (!best || cost < best.cost) best = {cost, b};
    }
    const x = clamp(best.b.x, 8, Math.max(8, width - cw - 8)), y = clamp(best.b.y, 8, Math.max(8, height - ch - 8));
    card.style.left = `${f(x)}px`; card.style.top = `${f(y)}px`;
    // It settles 4 px towards its resting place: it starts a little nearer the node.
    const cxm = x + cw / 2 - at.x, cym = y + ch / 2 - at.y, cl = Math.hypot(cxm, cym) || 1;
    card.style.setProperty('--tx', `${f(-cxm / cl * 4)}px`); card.style.setProperty('--ty', `${f(-cym / cl * 4)}px`);
    void card.offsetWidth; card.classList.add('am-on');
  }
  function closeCard() {
    clearTimeout(cardHide); card.classList.remove('am-on');
    cardHide = setTimeout(() => { card.hidden = true; }, isReduced() ? 0 : 120);
  }
  // Moving from one hub to the next keeps the dim in place (no flash back to full) until a 120 ms grace passes; the card fades out and the next dwells 180 ms.
  function hoverTo(id, now = false) {
    if (id === hoverId) return;
    starRecs.get(hoverId)?.el.classList.remove('am-lift');
    hoverId = hovered = id;
    clearTimeout(cardTimer); clearTimeout(graceTimer);
    const at = positions.find(m => m.id === id);
    starRecs.get(id)?.el.classList.add('am-lift');
    syncHot();
    if (!clustered()) return;
    if (!at) { graceTimer = setTimeout(() => { setHot(null); closeCard(); }, 120); return; }
    setHot(at.cluster);
    if (!card.hidden) card.classList.remove('am-on');
    if (now) placeCard(at); else cardTimer = setTimeout(() => placeCard(at), 180);
  }
  function hoverAt(p) {
    let best = null, nearest = Infinity;
    for (const m of screenNodes()) { const d = Math.hypot(m.x - p.x, m.y - p.y); if (d < Math.max(14, m.radius) && d < nearest) { best = m.id; nearest = d; } }
    hoverTo(best);
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
    const was = {w: width, h: height};
    inset = {...INSET, ...(typeof options.inset === 'function' ? options.inset(w, h) : options.inset)};
    controlsBottom = inset.bottom > INSET.bottom ? inset.bottom + 8 : 12; controls.style.bottom = `${controlsBottom}px`;
    width = w; height = h; u = unit(w, h); centre = options.overview && !options.calm && w < 600 ? {x: w / 2, y: h * .32} : coreCentre(w, h, inset); host.dataset.phoneOverview = String(phoneOverview()); host.dataset.narrow = String(width < 480); svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    const css = getComputedStyle(host); serif = css.getPropertyValue('--am-serif').trim() || 'serif'; sans = css.getPropertyValue('--am-sans').trim() || 'sans-serif';
    drawCore();
    const step = Math.abs(w - was.w) + Math.abs(h - was.h) > 120 && positions.length > 0;
    baseCache = null; cancelAnimationFrame(flight); levels = new Map(); gLevel = 0; focusM = null; pointerAt = null;
    camera = {x: 0, y: 0, k: 1}; positions = layoutScene(); render(new Map(), false, true, step); emit('resize', {width, height});
  }
  const maxK = () => (clustered() ? MAX_K : 4);
  function zoom(k, x = width / 2, y = height / 2) {
    const next = clamp(k, MIN_K, maxK()), ratio = next / camera.k;
    camera.x = x - (x - camera.x) * ratio; camera.y = y - (y - camera.y) * ratio; camera.k = next;
    limitCamera(); refreshOverlay(); syncDetail(); emit('viewchange', {...camera});
  }
  // Semantic zoom: the projects near the view centre (or the pointer, while it zooms) open as far as the zoom asks; a level change re-lays the open projects out and glides the marks.
  function syncDetail() {
    if (!clustered() || !positions.length) return;
    const k = camera.k, at = pointerAt && performance.now() - pointerAt.t < 1500 ? pointerAt : {x: width / 2, y: height / 2}, on = n => ({x: n.x * k + camera.x, y: n.y * k + camera.y});
    const hubs = positions.filter(n => n.hub).map(n => ({id: n.cluster, ...on(n), ...(counts.get(n.cluster) || {missions: 0, ideas: 0, worktrees: 0})}));
    const next = expansion({k, prevGlobal: gLevel, prev: levels, hubs, centre: at, radius: Math.min(width, height) * .5});
    const deepest = [...next.levels].find(([, lv]) => lv >= 3)?.[0];
    const focus = deepest === undefined ? null : pickFocus(focusM, positions.filter(n => n.kind === 'Mission' && n.cluster === deepest).map(n => ({id: n.id, d: Math.hypot(on(n).x - at.x, on(n).y - at.y)})));
    if (next.global === gLevel && sameLevels(next.levels, levels) && focus === focusM) return;
    gLevel = next.global; levels = next.levels; focusM = focus; relayout();
  }
  function relayout() {
    const previous = new Map(positions.map(n => [n.id, n]));
    positions = layoutScene();
    if (selected !== null && !positions.some(n => n.id === selected) && !graph.nodes.some(n => n.id === selected)) selected = null;
    render(previous, true, true, true);
  }
  // The camera glides to a view (240 ms, the glide easing); under Reduced motion it is there at once. Any new input takes over.
  function tween(to) {
    cancelAnimationFrame(flight);
    const from = {...camera}, t0 = performance.now(), end = () => { camera = {...to}; limitCamera(); refreshOverlay(); syncDetail(); emit('viewchange', {...camera}); };
    if (isReduced() || document.hidden || (from.k === to.k && from.x === to.x && from.y === to.y)) return end();
    const step = now => {
      const p = Math.min(1, (now - t0) / (MOTION.glide + 20)), e = p < .5 ? 4 * p * p * p : 1 - (-2 * p + 2) ** 3 / 2, k = from.k * (to.k / from.k) ** e;
      camera = {k, x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e}; refreshOverlay(); syncDetail();
      if (p < 1) flight = requestAnimationFrame(step); else end();
    };
    flight = requestAnimationFrame(step);
  }
  const zoomBy = (ratio, node) => { const k = clamp(camera.k * ratio, MIN_K, maxK()), r = k / camera.k, x = node ? node.x * camera.k + camera.x : width / 2, y = node ? node.y * camera.k + camera.y : height / 2; pointerAt = node ? {x, y, t: performance.now() + 1500} : null; tween({k, x: x - (x - camera.x) * r, y: y - (y - camera.y) * r}); };
  // The first click on a hub focuses it (the camera flies there and its project opens); a click on one that is already open opens the project.
  function flyToHub(n) { pointerAt = null; closeCard(); const k = Math.max(camera.k, 2.6); tween({k, x: width / 2 - n.x * k, y: height * .45 - n.y * k}); }
  function limitCamera() {
    camera.x = clamp(camera.x, -width * camera.k, width);
    camera.y = clamp(camera.y, -height * camera.k, height);
  }
  function reset() { camera = {x: 0, y: 0, k: 1}; refreshOverlay(); syncDetail(); emit('viewchange', {...camera}); }
  function fitView() {
    if (!positions.length) return reset();
    // Fit frames the compact scene (every project closed) and stays under the first level of detail: it always brings the overview back.
    const all = clustered() ? compact : positions;
    let minX = Math.min(...all.map(n => n.x - n.radius - 28)), maxX = Math.max(...all.map(n => n.x + n.radius + 28)), minY = Math.min(...all.map(n => n.y - n.radius - 28)), maxY = Math.max(...all.map(n => n.y + n.radius + 28));
    const outer = ringed() && ringsOut ? ringsOut.lanes[ringsOut.lanes.length - 1] : null;
    if (outer) { minX = Math.min(minX, centre.x - outer.rx - 8); maxX = Math.max(maxX, centre.x + outer.rx + 8); minY = Math.min(minY, centre.y - outer.ry - 8); maxY = Math.max(maxY, centre.y + outer.ry + 8); }
    const k = clamp(Math.min((width - 32) / (maxX - minX || 1), (height - 90) / (maxY - minY || 1)), MIN_K, clustered() ? OVERVIEW_MAX : 4);
    pointerAt = null; tween({k, x: width / 2 - (minX + maxX) / 2 * k, y: (height - 50) / 2 - (minY + maxY) / 2 * k});
  }
  for (const [label, text, action] of [['Zoom in', '+', () => zoomBy(1.6)], ['Zoom out', '−', () => zoomBy(1 / 1.6)], ['Fit all nodes', 'Fit', fitView]].map(([a, t, g]) => [T(a), t === 'Fit' ? T(t) : t, g])) {
    const button = element('button', '', text); button.type = 'button'; button.setAttribute('aria-label', label); button.addEventListener('click', action); controls.append(button);
  }
  function point(event) { const r = svg.getBoundingClientRect(); return {x: event.clientX - r.left, y: event.clientY - r.top}; }
  function wheel(event) { event.preventDefault(); cancelAnimationFrame(flight); const p = point(event); pointerAt = {...p, t: performance.now()}; zoom(camera.k * Math.exp(-event.deltaY * .0015), p.x, p.y); }
  let suppressClick = false;
  function startGesture() {
    const values = [...pointers.values()];
    gesture = {camera: {...camera}, center: values.length > 1 ? {x: (values[0].x + values[1].x) / 2, y: (values[0].y + values[1].y) / 2} : values[0],
      distance: values.length > 1 ? Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y) : 0};
  }
  function down(event) {
    if (event.button !== 0) return;
    if (!pointers.size) suppressClick = false;
    cancelAnimationFrame(flight); pointers.set(event.pointerId, point(event)); event.target.setPointerCapture(event.pointerId); startGesture();
  }
  function move(event) {
    if (!pointers.has(event.pointerId)) { if (event.pointerType === 'mouse') hoverAt(point(event)); return; }
    pointers.set(event.pointerId, point(event));
    const values = [...pointers.values()];
    const center = values.length > 1 ? {x: (values[0].x + values[1].x) / 2, y: (values[0].y + values[1].y) / 2} : values[0];
    const distance = values.length > 1 ? Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y) : 0;
    if (Math.hypot(center.x - gesture.center.x, center.y - gesture.center.y) > 4 || values.length > 1) suppressClick = true;
    const k = gesture.distance ? clamp(gesture.camera.k * distance / gesture.distance, MIN_K, maxK()) : gesture.camera.k;
    pointerAt = values.length > 1 ? {...center, t: performance.now()} : null;
    camera = {k, x: center.x - (gesture.center.x - gesture.camera.x) * k / gesture.camera.k, y: center.y - (gesture.center.y - gesture.camera.y) * k / gesture.camera.k};
    limitCamera(); refreshOverlay(); syncDetail();
  }
  function up(event) {
    pointers.delete(event.pointerId);
    if (pointers.size) startGesture(); else { gesture = null; syncDetail(); emit('viewchange', {...camera}); }
  }
  // Keyboard zoom: + and - step one level, 0 fits (the Fit button); Enter on a node opens it.
  host.addEventListener('keydown', event => {
    if (event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return;
    const at = positions.find(n => n.id === event.target.closest?.('.am-hit')?.dataset.nodeId);
    if (event.key === '+' || event.key === '=') { event.preventDefault(); zoomBy(1.6, at); } else if (event.key === '-' || event.key === '_') { event.preventDefault(); zoomBy(1 / 1.6, at); } else if (event.key === '0') { event.preventDefault(); fitView(); }
  });
  hits.addEventListener('focusin', event => { const id = event.target.closest('.am-hit')?.dataset.nodeId; if (id) focusNodeIfOutside(id); });
  hits.addEventListener('keydown', event => {
    const id = event.target.closest('.am-hit')?.dataset.nodeId;
    if (!id) return;
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(id); }
    else if (event.key === 'Escape') { clearTimeout(cardTimer); closeCard(); }
    else if (event.key.startsWith('Arrow')) { event.preventDefault(); const next = (ringed() && ringsOut && ringsOut.order.includes(id) ? ringStep(ringsOut, id, event.key) : null) ?? nearestNeighbour(positions, id, event.key); if (next) focusNode(next); }
  });
  // A row of the table is the list entry of a mark: on the rings a project's row flies the camera to it (its project opens), as a click on the mark does.
  body.addEventListener('click', event => {
    const id = event.target.closest('tr')?.dataset.nodeId, hub = id && ringed() && positions.find(n => n.id === id && n.hub);
    if (id && event.target.closest('button')) { if (hub) { flyToHub(hub); focusNode(id); } else { choose(id, true); focusNode(id); } }
  });
  hits.addEventListener('click', event => {
    if (suppressClick) return;
    if (!event.detail) { const id = event.target.closest('.am-hit')?.dataset.nodeId; if (id) choose(id); return; }
    const p = point(event);
    let best = null, nearest = Infinity;
    for (const n of screenNodes()) {
      const d = Math.hypot(n.x - p.x, n.y - p.y);
      if (d < hitR(n) && d < nearest) { best = n.id; nearest = d; }
    }
    const hub = best && positions.find(n => n.id === best && n.hub);
    if (hub && clustered() && (event.detail > 1 || !levels.has(hub.cluster))) flyToHub(hub); else if (best) choose(best);
  });
  svg.addEventListener('wheel', wheel, {passive: false});
  svg.addEventListener('pointerdown', down); svg.addEventListener('pointermove', move);
  svg.addEventListener('pointerup', up); svg.addEventListener('pointercancel', up); svg.addEventListener('pointerleave', () => hoverTo(null));
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
      if (!ids.has(selected) && !positions.some(n => n.id === selected)) selected = null;
      // What the open projects say in detail is part of the picture: it is read again for every change and compared with the last.
      detailData = new Map(); eventData = new Map();
      const full = JSON.stringify(graph) + [...levels].map(([id, lv]) => id + lv + (lv >= 2 ? JSON.stringify(detailFor(id)) : '') + (lv >= 3 && focusM ? JSON.stringify(eventsFor(focusM)) : '')).join('|');
      if (full === fullKey) return;
      fullKey = full; baseCache = null;
      projOf = new Map(graph.nodes.map(n => [n.id, n.project || 'unassigned'])); kidsOf = new Map();
      for (const e of graph.edges) { const kid = graph.nodes.find(n => n.id === e.to); if (kid && (kid.kind === 'Execution' || kid.kind === 'Decision')) kidsOf.set(e.from, [...(kidsOf.get(e.from) || []), kid]); }
      counts = new Map(graph.projects.map(p => [p.id, {missions: 0, ideas: p.ideaList?.length || 0, worktrees: p.worktrees?.length || 0}]));
      for (const n of graph.nodes) if (n.kind === 'Mission' && counts.has(n.project)) counts.get(n.project).missions++;
      // A project keeps the slot it got when first seen (attention first, then recent activity), so nothing already placed moves when another arrives.
      projectOf = new Map(graph.projects.map(p => [p.id, p]));
      for (const p of orderProjects(graph.projects.filter(p => !slots.has(p.id)))) slots.set(p.id, slots.size);
      const placed = layoutScene(), moved = placed.length !== positions.length || placed.some((n, i) => n.id !== positions[i].id || n.x !== positions[i].x || n.y !== positions[i].y);
      positions = placed;
      if (moved) drawCore();
      render(previous, true, moved, moved && previous.size > 0);
      emit('update', {nodes: positions.length});
    },
    setSelection: id => { if (!destroyed) choose(id, true); },
    setTheme(name) { if (!destroyed) host.dataset.theme = name; },
    setReducedMotion(bool) { reducedOverride = Boolean(bool); if (!destroyed) motion(); },
    resize, fitView,
    element: host,
    setLive(live) { options.live = live === true; if (!destroyed) motion(); },
    setAmbient(on) { playing = on === true; if (!destroyed) motion(); },
    // The e-stop (or a lost Core): the core mark goes slack with a red cross.
    setStopped(on) { if (stopped === (on === true)) return; stopped = on === true; if (!destroyed) { syncCore(); updateSummary(); } },
    pulse(id) {
      const path = edgeRecs.get(id)?.line;
      if (destroyed || !path || isReduced() || document.hidden || activePulses.size >= 8) return false;
      const marker = svgElement('path', {d: 'M0,0h0', class: 'am-marker'});
      marker.style.offsetPath = `path('${path.getAttribute('d')}')`;
      pulseLayer.append(marker); activePulses.add(marker);
      const animation = marker.animate([{offsetDistance: '0%', opacity: 0}, {offsetDistance: '10%', opacity: 1, offset: .1}, {offsetDistance: '90%', opacity: 1, offset: .9}, {offsetDistance: '100%', opacity: 0}], {duration: MOTION.travel, easing: 'linear'});
      const finish = () => { marker.remove(); activePulses.delete(marker); };
      animation.onfinish = finish; animation.oncancel = finish; emit('pulse', id); return true;
    },
    on(event, fn) { if (!listeners.has(event)) listeners.set(event, new Set()); listeners.get(event).add(fn); return () => listeners.get(event)?.delete(fn); },
    destroy() {
      if (destroyed) return;
      destroyed = true; clearTimeout(cardTimer); clearTimeout(graceTimer); clearTimeout(cardHide); observer.disconnect(); seen?.disconnect(); media.removeEventListener('change', motion); document.removeEventListener('visibilitychange', motion); document.fonts?.removeEventListener('loadingdone', refit);
      for (const animation of host.getAnimations({subtree: true})) animation.cancel();
      pointers.clear(); activePulses.clear(); listeners.clear(); host.remove();
    }
  };
  resize(); if (options.graph) api.update(options.graph); return api;
}
