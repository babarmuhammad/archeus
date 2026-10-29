import {clamp, stateKey, driftOf, INSET} from './geometry.js';
import {bodyMarkup, corePaths, coreTier, ICONS} from './nodeart.js';
import {orderProjects, leadMission} from './order.js';

const NS = 'http://www.w3.org/2000/svg';
const f = v => +v.toFixed(1);
const words = {'needs-you': 'Needs you', running: 'Running', done: 'Done', blocked: 'Blocked', idle: 'Quiet', paused: 'Paused', thinking: 'Planning'};
const RANK = {'needs-you': 5, running: 4, blocked: 3, paused: 2, thinking: 2, done: 1, idle: 0};
const ICON = {done: 'check', 'needs-you': 'doc-search'};
const svgEl = (tag, attrs = {}, text) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text !== undefined) e.textContent = text; return e; };
const htmlEl = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };

// A grid of cells with a gutter down the middle for the core and its wordmark: an even number of columns, any number of rows.
// The pick is the grid whose cells come closest to 3:2 at the largest size the cell cap allows; on a tie the smaller grid wins, so three projects get four big cells, not twelve small ones.
const CELL_MAX = {w: 420, h: 280};
export function pickGrid(count, aw, ah, gap, gutter) {
  let best = null;
  for (const rows of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]) for (const cols of [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]) {
    if (cols * rows < count) continue;
    const cw = (aw - gutter - gap * (cols - 2)) / cols, ch = (ah - gap * (rows - 1)) / rows, score = Math.min(Math.min(cw, CELL_MAX.w) / 1.5, Math.min(ch, CELL_MAX.h));
    if (!best || score > best.score + .5 || (Math.abs(score - best.score) <= .5 && cols * rows < best.cols * best.rows)) best = {cols, rows, cw, ch, score};
  }
  return best || {cols: 20, rows: 13, cw: (aw - gutter - gap * 18) / 20, ch: (ah - gap * 12) / 13, score: 0};
}
export const levelOf = (w, h) => (w >= 210 && h >= 140 ? 'full' : w >= 128 && h >= 84 ? 'compact' : 'mark');
// Cells in slot order: the ones beside the core first, so a few projects stay close to it and the rest grow outwards.
export function layoutTerritories(count, width, height, inset = INSET) {
  const gap = count > 30 ? 6 : 12, aw = Math.max(40, width - inset.left - inset.right), ah = Math.max(40, height - inset.top - inset.bottom);
  const radius = clamp(Math.min(aw, ah) * .07, 16, 38), gutter = Math.max(120, radius * 2.6);
  const g = pickGrid(Math.max(1, count), aw, ah, gap, gutter), cw = Math.max(24, Math.min(g.cw, CELL_MAX.w)), ch = Math.max(24, Math.min(g.ch, CELL_MAX.h)); // a narrow scene (the Details sheet open on a small window) never gives a negative size
  const bw = g.cols * cw + gap * (g.cols - 2) + gutter, bh = g.rows * ch + gap * (g.rows - 1), x0 = inset.left + (aw - bw) / 2, y0 = inset.top + (ah - bh) / 2;
  const half = g.cols / 2, ri = (g.rows - 1) / 2, level = levelOf(cw, ch), slots = [];
  for (let r = 0; r < g.rows; r++) for (let c = 0; c < g.cols; c++) {
    const right = c >= half, x = x0 + c * (cw + gap) + (right ? gutter - gap : 0);
    slots.push({col: c, row: r, x, y: y0 + r * (ch + gap), w: cw, h: ch, level, rank: (right ? c - half : half - 1 - c) * .8 + Math.abs(r - ri)});
  }
  slots.sort((a, b) => a.rank - b.rank || a.row - b.row || a.col - b.col);
  return {core: {x: x0 + bw / 2, y: y0 + bh / 2, radius}, cells: slots, cols: g.cols, rows: g.rows, level, gutter};
}
// The point where the line from a cell's centre to the core leaves the cell, so a spoke ends on the outline.
export function edgePoint(cell, to) {
  const cx = cell.x + cell.w / 2, cy = cell.y + cell.h / 2, dx = to.x - cx, dy = to.y - cy;
  const t = Math.min(dx ? (cell.w / 2) / Math.abs(dx) : Infinity, dy ? (cell.h / 2) / Math.abs(dy) : Infinity, 1);
  return {x: cx + dx * t, y: cy + dy * t};
}

export function createTerritoryMap(container, options = {}) {
  const T = options.t || (x => x);
  const host = htmlEl('div', 'archeus-map am-territories');
  host.dataset.theme = options.theme || 'dark'; host.dataset.calm = 'false';
  host.setAttribute('role', 'group'); host.setAttribute('aria-label', options.label || 'Projects and missions');
  const svg = svgEl('svg', {role: 'img'});
  const world = svgEl('g', {class: 'am-world', 'aria-hidden': 'true'}), spokeLayer = svgEl('g', {class: 'am-spokes'}), cellLayer = svgEl('g', {class: 'am-cells'}), core = svgEl('g', {class: 'am-core am-state-core'}), pulseLayer = svgEl('g', {class: 'am-pulses'});
  const coreMark = svgEl('g', {'data-core': 'static'}), wordmark = svgEl('text', {class: 'am-wordmark', 'text-anchor': 'middle'}, 'ARCHEUS'), runningText = svgEl('text', {class: 'am-running', 'text-anchor': 'middle'});
  core.append(coreMark, wordmark, runningText);
  world.append(spokeLayer, cellLayer, core, pulseLayer);
  const hits = svgEl('g', {class: 'am-hits'}), ring = svgEl('circle', {class: 'am-select-ring'});
  svg.append(world, hits);
  const card = htmlEl('div', 'am-card'); card.hidden = true; card.setAttribute('role', 'status');
  const equivalent = htmlEl('div', 'am-equivalent am-sr'), status = htmlEl('p', 'am-sr'); status.setAttribute('role', 'status');
  const panel = htmlEl('section', 'am-focus'); panel.hidden = true;
  host.append(svg, panel, card, status, equivalent); container.append(host);

  let model = {projects: []}, width = 1, height = 1, inset = INSET, destroyed = false, selected = null, playing = options.playing === true, visible = true, hot = null, cardTimer = 0, focused = null, stopped = false, coreTierNow = 'full';
  let reducedOverride = options.reducedMotion, layout = null, serif = 'serif', sans = 'sans-serif';
  const slotOf = new Map(), cellRecs = new Map(), listeners = new Map(), markers = new Set();
  const media = matchMedia('(prefers-reduced-motion: reduce)'), canvas = document.createElement('canvas'), ctx2d = canvas.getContext('2d');
  const emit = (event, detail) => { for (const fn of listeners.get(event) || []) fn(detail); };
  const isReduced = () => reducedOverride === true || (reducedOverride === undefined && media.matches);
  const isLive = () => options.live === true && model.projects.some(p => p.running);
  const ambientOn = () => playing && visible && !isReduced() && !document.hidden;
  const fit = (text, max, font) => {
    if (!ctx2d) return text;
    ctx2d.font = font;
    let s = String(text);
    if (ctx2d.measureText(s).width <= max) return s;
    while (s.length > 1 && ctx2d.measureText(s + '…').width > max) s = s.slice(0, -1);
    return s.trimEnd() + '…';
  };
  const stateOf = p => (p.attention ? 'needs-you' : p.running ? 'running' : p.stopped ? 'blocked' : p.total ? 'done' : 'idle');
  const wordOf = state => T(words[state] || state);
  const driftVars = (e, id) => { const d = driftOf(options.seed, id); e.style.setProperty('--dx', d.dx + 'px'); e.style.setProperty('--dy', d.dy + 'px'); e.style.setProperty('--dp', d.period + 'ms'); e.style.setProperty('--dd', d.delay + 'ms'); };
  const crystal = (m, r) => { const holder = svgEl('g'); const st = stateKey(m.state); holder.innerHTML = bodyMarkup({id: m.id, kind: 'Mission', state: st, radius: r}, ICON[st] || 'doc'); const star = holder.firstElementChild; driftVars(star, m.id); return star; };
  const motion = () => {
    host.dataset.reduced = String(isReduced()); host.dataset.ambient = ambientOn() ? 'on' : 'off';
    coreMark.dataset.core = isLive() && !document.hidden && !isReduced() ? 'breath' : 'static';
    const running = model.projects.reduce((t, p) => t + p.running, 0);
    runningText.textContent = isLive() && isReduced() ? T(`${running} running`) : '';
    if (isReduced() || document.hidden) { for (const a of host.getAnimations({subtree: true})) if (a.animationName !== 'core-breath') a.cancel(); for (const m of markers) m.remove(); markers.clear(); }
  };
  // Motion: a cell glides to its new slot, a new one rises in, a gone one fades, a changed one takes a single tint. transform and opacity on the cell group, finite, nothing under Reduced motion.
  const tok = (name, fallback) => parseFloat(getComputedStyle(host).getPropertyValue(name)) || fallback;
  const curve = name => getComputedStyle(host).getPropertyValue(name).trim() || 'cubic-bezier(.23, 1, .32, 1)';
  const canMove = () => !isReduced() && !document.hidden && typeof Element.prototype.animate === 'function';
  const at = (x, y, dy = 0) => `translate(${f(x)}px, ${f(y + dy)}px)`;
  const glideCell = (g, was, now) => g.animate([{transform: at(was.x, was.y)}, {transform: at(now.x, now.y)}], {duration: tok('--dur-3', 200), easing: curve('--ease-move')});
  const riseCell = (g, cell) => g.animate([{opacity: 0, transform: at(cell.x, cell.y, 6)}, {opacity: 1, transform: at(cell.x, cell.y)}], {duration: tok('--dur-2', 160), easing: curve('--ease-out'), fill: 'backwards'});
  const fadeCell = g => { const a = g.animate([{opacity: 1}, {opacity: 0}], {duration: tok('--dur-1', 100), easing: curve('--ease-out'), fill: 'forwards'}); a.onfinish = a.oncancel = () => g.remove(); };
  const tintCell = g => {
    const outline = g.querySelector('.am-cell-outline'); if (!outline) return;
    const t = svgEl('path', {class: 'am-cell-tint', d: outline.getAttribute('d')}); g.prepend(t);
    const a = t.animate([{opacity: 1}, {opacity: 0}], {duration: tok('--dur-2', 160), easing: curve('--ease-out')}); a.onfinish = a.oncancel = () => t.remove();
  };
  const lineOf = (p, state) => (p.last ? `${p.last.time} · ${p.last.text}` : state === 'idle' ? T('No missions yet') : '');

  function cellSig(p, cell) {
    return [cell.x, cell.y, cell.w, cell.h, cell.level, p.name, p.code, p.attention, p.running, p.stopped, p.total, p.ideas, p.last && p.last.text, p.last && p.last.time, (p.worktrees || []).length, p.missions.map(m => m.id + m.state + m.title).join(',')].join('|');
  }
  function drawCell(p, cell) {
    const state = stateOf(p), g = svgEl('g', {class: `am-cell am-cell-${cell.level} am-state-${state}`, 'data-project': p.id, transform: `translate(${f(cell.x)} ${f(cell.y)})`});
    const {w, h} = cell, cut = cell.level === 'mark' ? 6 : 10;
    g.append(svgEl('path', {class: 'am-cell-outline', d: `M${cut},0H${w}V${h - cut}L${w - cut},${h}H0V${cut}Z`}));
    const hitsOf = [];
    const code = p.code;
    if (cell.level === 'mark') {
      g.append(svgEl('text', {class: 'am-cell-code am-cell-code-big', x: w / 2, y: h / 2 - 2, 'text-anchor': 'middle'}, code));
      const my = h / 2 + 14;
      if (state === 'needs-you') g.append(svgEl('path', {class: 'am-diamond', d: `M${w / 2},${my - 6}l6,6l-6,6l-6,-6Z`}));
      else if (state === 'running') g.append(svgEl('circle', {class: 'am-cell-dot am-hollow', cx: w / 2, cy: my, r: 4.5}));
      else if (state === 'blocked') g.append(svgEl('path', {class: 'am-cross', d: `M${w / 2 - 4},${my - 4}l8,8m0,-8l-8,8`}));
      else g.append(svgEl('circle', {class: 'am-cell-dot', cx: w / 2, cy: my, r: 2.5}));
      return {g, hitsOf};
    }
    g.append(svgEl('rect', {class: 'am-cell-chip', x: 10, y: 9, width: 30, height: 20, rx: 4}), svgEl('text', {class: 'am-cell-code', x: 25, y: 23, 'text-anchor': 'middle'}, code));
    const stateWord = wordOf(state).toUpperCase(), nameMax = w - 48 - (cell.level === 'full' ? 86 : 12);
    g.append(svgEl('text', {class: 'am-cell-name', x: 48, y: 24}, fit(p.name, nameMax, `400 17px ${serif}`)));
    if (cell.level === 'full') g.append(svgEl('text', {class: 'am-cell-state', x: w - 12, y: 23, 'text-anchor': 'end'}, stateWord));
    else if (state === 'needs-you') g.append(svgEl('path', {class: 'am-diamond', d: `M${w - 18},${12}l6,6l-6,6l-6,-6Z`}));
    const ms = [...p.missions].sort((a, b) => RANK[stateKey(b.state)] - RANK[stateKey(a.state)] || (b.at || 0) - (a.at || 0) || String(a.id).localeCompare(String(b.id)));
    // A project's worktrees are counted in a small chip (never as projects of their own); the focus panel lists them.
    const wts = (p.worktrees || []).length, chipW = 24 + String(wts).length * 7, chipOn = wts > 0 && (cell.level === 'full' || (h >= 100 && w >= 150)), reserve = chipOn ? chipW + 8 : 0;
    if (cell.level === 'full') {
      const bodyH = h - 76, cy = 40 + bodyH / 2, lead = ms[0];
      if (lead) {
        const R = clamp(bodyH / 2 - 4, 16, 44), cx = 14 + R, star = crystal(lead, R);
        star.setAttribute('transform', `translate(${f(cx)} ${f(cy)})`); g.append(star); hitsOf.push({id: lead.id, kind: 'Mission', x: cell.x + cx, y: cell.y + cy, r: Math.max(22, R), label: lead.title, state: stateKey(lead.state)});
        const lx = cx + R + 14, lw = w - lx - 12;
        g.append(svgEl('text', {class: 'am-cell-lead', x: lx, y: cy - 4}, fit(lead.title, lw, `400 15px ${serif}`)));
        g.append(svgEl('text', {class: `am-cell-sub am-state-${stateKey(lead.state)}`, x: lx, y: cy + 14}, wordOf(stateKey(lead.state))));
        const rest = ms.slice(1), room = Math.max(0, Math.floor((lw - 6) / 26)), shown = rest.slice(0, rest.length > room ? Math.max(0, room - 1) : room);
        shown.forEach((m, i) => { const mx = lx + 8 + i * 26, my = cy + 38, s = crystal(m, 9); s.setAttribute('transform', `translate(${f(mx)} ${f(my)})`); g.append(s); hitsOf.push({id: m.id, kind: 'Mission', x: cell.x + mx, y: cell.y + my, r: 13, label: m.title, state: stateKey(m.state)}); });
        if (rest.length > shown.length) g.append(svgEl('text', {class: 'am-cell-more', x: lx + 8 + shown.length * 26 - 8, y: cy + 42}, `+${rest.length - shown.length}`));
      } else if (p.ideas) g.append(svgEl('text', {class: 'am-cell-quiet', x: 14, y: cy + 5}, T(`${p.ideas} ${p.ideas === 1 ? 'idea' : 'ideas'} captured`)));
      const line = lineOf(p, state);
      if (line) g.append(svgEl('text', {class: 'am-cell-last', x: 12, y: h - 12}, fit(line, w - 24 - reserve, `400 12px ${sans}`)));
    } else {
      const line = h >= 100 && w >= 150 ? lineOf(p, state) : '';
      if (line) g.append(svgEl('text', {class: 'am-cell-last', x: 12, y: h - 12}, fit(line, w - 24 - reserve, `400 12px ${sans}`)));
      const room = Math.max(1, Math.floor((w - 28) / 24)), shown = ms.slice(0, ms.length > room ? room - 1 : room), cy = h - (line ? 38 : 28);
      shown.forEach((m, i) => { const mx = 22 + i * 24, s = crystal(m, 9); s.setAttribute('transform', `translate(${f(mx)} ${f(cy)})`); g.append(s); hitsOf.push({id: m.id, kind: 'Mission', x: cell.x + mx, y: cell.y + cy, r: 13, label: m.title, state: stateKey(m.state)}); });
      if (ms.length > shown.length) g.append(svgEl('text', {class: 'am-cell-more', x: 22 + shown.length * 24 - 8, y: cy + 4}, `+${ms.length - shown.length}`));
    }
    if (chipOn) {
      const cx = w - 12 - chipW, label = T(`${wts} ${wts === 1 ? 'worktree' : 'worktrees'}`), chip = svgEl('g', {class: 'am-cell-wt', transform: `translate(${f(cx)} ${h - 28})`});
      chip.append(svgEl('title', {}, label), svgEl('rect', {class: 'am-cell-wt-box', width: chipW, height: 18, rx: 4}), svgEl('path', {class: 'am-cell-wt-icon', d: ICONS.branch, transform: 'translate(4 3) scale(.5)'}), svgEl('text', {class: 'am-cell-wt-n', x: chipW - 6, y: 13, 'text-anchor': 'end'}, String(wts)));
      g.append(chip);
    }
    return {g, hitsOf};
  }
  const describe = p => `${p.name}, ${p.code}, ${wordOf(stateOf(p))}${p.attention ? `, ${p.attention} ${T('need you')}` : ''}${(p.worktrees || []).length ? `, ${T(`${p.worktrees.length} ${p.worktrees.length === 1 ? 'worktree' : 'worktrees'}`)}` : ''}${p.last ? `, ${p.last.text}` : ''}`;

  let graceTimer = 0, hideTimer = 0, over = null;
  // The card fades out over 120 ms; the dim holds a 120 ms grace so moving from one cell to the next cross-fades instead of flashing back to full.
  const closeCard = () => { clearTimeout(hideTimer); card.classList.remove('am-on'); hideTimer = setTimeout(() => { card.hidden = true; }, isReduced() ? 0 : 120); };
  function showCard(info, at) {
    clearTimeout(cardTimer);
    if (!card.hidden) card.classList.remove('am-on');
    const open = () => {
      card.replaceChildren(htmlEl('p', 'am-card-kind', info.kind), htmlEl('p', 'am-card-name', info.title), htmlEl('p', `am-card-state am-state-${info.state}`, info.stateWord), ...(info.project ? [htmlEl('p', 'am-card-line', info.project)] : []), ...(info.line ? [htmlEl('p', 'am-card-last', info.line)] : []), htmlEl('p', 'am-card-act', info.action));
      clearTimeout(hideTimer); card.classList.remove('am-on'); card.hidden = false;
      const cw = card.offsetWidth, ch = card.offsetHeight, top = Math.max(8, inset.top), bottom = Math.max(top + ch, height - inset.bottom), gap = 16;
      // Beside the hovered cell (right, left, below, above), never over its code chip or name; inside its lower right only when no side has room.
      const sides = [[at.x + at.w + gap, clamp(at.y, top, bottom - ch)], [at.x - cw - gap, clamp(at.y, top, bottom - ch)], [clamp(at.x, 8, width - cw - 8), at.y + at.h + gap], [clamp(at.x, 8, width - cw - 8), at.y - ch - gap]];
      const [x, y] = sides.find(([x, y]) => x >= 8 && x + cw <= width - 8 && y >= top && y + ch <= bottom) || [clamp(at.x + at.w - cw - 8, 8, Math.max(8, width - cw - 8)), clamp(at.y + at.h - ch - 8, at.y + 44, Math.max(at.y + 44, bottom - ch))];
      card.style.left = f(x) + 'px'; card.style.top = f(clamp(y, 8, Math.max(8, height - ch - 8))) + 'px';
      card.style.setProperty('--tx', f(x < at.x ? 4 : x >= at.x + at.w ? -4 : 0) + 'px'); card.style.setProperty('--ty', f(y < at.y ? 4 : y >= at.y + at.h ? -4 : 0) + 'px');
      void card.offsetWidth; card.classList.add('am-on');
    };
    if (at.now) open(); else cardTimer = setTimeout(open, 180);
  }
  const hideCard = () => { clearTimeout(cardTimer); clearTimeout(graceTimer); graceTimer = setTimeout(() => { setHot(null); closeCard(); }, 120); };
  function setHot(id) {
    hot = id;
    if (id) host.dataset.hot = id; else delete host.dataset.hot;
    for (const [pid, rec] of cellRecs) { rec.g.classList.toggle('am-hot', pid === id); rec.spoke?.classList.toggle('am-spoke-hot', pid === id); }
  }
  function bindHit(el, info, project, at) {
    // The element last entered owns the card: a late leave from the one before (a mission mark sits on its cell) must not close it.
    const enter = now => { over = el; clearTimeout(graceTimer); setHot(project.id); showCard(info, {...at, now}); };
    const leave = () => { if (over === el) { over = null; hideCard(); } };
    el.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') enter(false); });
    el.addEventListener('pointerleave', leave);
    el.addEventListener('focus', () => { if (el.matches(':focus-visible')) enter(true); });
    el.addEventListener('blur', leave);
  }
  function select(id) { selected = id; paintSelection(); emit('select', id); }
  function focus(id) {
    const closing = !id && !panel.hidden && canMove() ? {ghost: panel.cloneNode(true), box: {x: panel.offsetLeft, y: panel.offsetTop, w: panel.offsetWidth, h: panel.offsetHeight}, rec: cellRecs.get(lastFocused)} : null;
    focused = id; clearTimeout(graceTimer); closeCard(); setHot(null); renderFocus(true);
    if (id && canMove()) expandFrom(cellRecs.get(id));
    if (closing) collapseTo(closing);
    if (id) panel.querySelector('.am-focus-back').focus({preventScroll: true});
    else { const c = [...hits.querySelectorAll('.am-chit:not(.am-chit-mission)')].find(n => n.dataset.nodeId === lastFocused); c?.focus({preventScroll: true}); }
    if (id) lastFocused = id;
    emit('focus', id);
  }
  let lastFocused = null;
  // The clicked cell becomes the panel: it grows from the cell's box (transform only; the words are not shown until it is most of the way there) and shrinks back into it.
  const boxFrom = (cell, b) => `translate(${f(cell.x - b.x)}px, ${f(cell.y - b.y)}px) scale(${f(cell.w / b.w)}, ${f(cell.h / b.h)})`;
  function expandFrom(rec) {
    if (!rec) return;
    const b = {x: panel.offsetLeft, y: panel.offsetTop, w: panel.offsetWidth, h: panel.offsetHeight}; if (!b.w || !b.h) return;
    panel.style.transformOrigin = '0 0';
    panel.animate([{opacity: 0, transform: boxFrom(rec.cell, b), offset: 0}, {opacity: 1, offset: .5}, {opacity: 1, transform: 'none', offset: 1}], {duration: tok('--dur-3', 200), easing: curve('--ease-move'), fill: 'backwards'});
  }
  function collapseTo({ghost, box, rec}) {
    ghost.inert = true; ghost.setAttribute('aria-hidden', 'true'); ghost.hidden = false;
    Object.assign(ghost.style, {inset: 'auto', left: box.x + 'px', top: box.y + 'px', width: box.w + 'px', height: box.h + 'px', transformOrigin: '0 0', pointerEvents: 'none'});
    host.append(ghost);
    const to = rec ? boxFrom(rec.cell, box) : 'scale(.98)';
    const a = ghost.animate([{opacity: 1, transform: 'none'}, {opacity: 0, transform: to}], {duration: tok('--dur-2', 160), easing: curve('--ease-move'), fill: 'forwards'});
    a.onfinish = a.oncancel = () => ghost.remove();
  }
  let focusSig = '';
  function renderFocus(force) {
    const p = focused && model.projects.find(x => x.id === focused);
    if (focused && !p) { focused = null; }
    const sig = p ? JSON.stringify([p, T('x')]) : '';
    if (!force && sig === focusSig) return;
    focusSig = sig;
    host.dataset.focus = focused ? 'on' : 'off';
    panel.hidden = !focused;
    if (!p) { panel.replaceChildren(); return; }
    const state = stateOf(p), btn = (cls, text, fn) => { const b = htmlEl('button', cls, text); b.type = 'button'; b.addEventListener('click', fn); return b; };
    const head = htmlEl('header', 'am-focus-head'), title = htmlEl('div', 'am-focus-title');
    title.append(htmlEl('span', 'am-focus-code', p.code), htmlEl('h2', 'am-focus-name', p.name), htmlEl('span', `am-focus-state am-state-${state}`, wordOf(state)));
    head.append(btn('am-focus-back', '← ' + T('All projects'), () => focus(null)), title, btn('am-focus-open', T('Open work'), () => select(p.id)));
    const list = htmlEl('ul', 'am-focus-list'), ms = [...p.missions].sort((a, b) => RANK[stateKey(b.state)] - RANK[stateKey(a.state)] || (b.at || 0) - (a.at || 0) || String(a.id).localeCompare(String(b.id)));
    for (const m of ms) {
      const st = stateKey(m.state), li = htmlEl('li', 'am-focus-item'), row = htmlEl('button', `am-focus-row am-state-${st}`);
      row.type = 'button'; row.dataset.nodeId = m.id; row.addEventListener('click', () => select(m.id));
      const art = svgEl('svg', {class: 'am-focus-art', width: 30, height: 30, viewBox: '-15 -15 30 30', 'aria-hidden': 'true'}); art.append(crystal(m, 11));
      const text = htmlEl('span', 'am-focus-text'); text.append(htmlEl('span', 'am-focus-mission', m.title), htmlEl('span', `am-focus-word am-state-${st}`, wordOf(st) + (m.time ? ' · ' + m.time : '')));
      row.append(art, text); li.append(row);
      if (st === 'needs-you') li.append(btn('am-focus-review', T('Review'), () => emit('review', m.id)));
      list.append(li);
    }
    const wl = (p.worktrees || []).length ? htmlEl('section', 'am-focus-wts') : null;
    if (wl) {
      wl.append(htmlEl('h3', 'am-focus-wt-head', T('Worktrees')));
      const rows = htmlEl('ul', 'am-focus-wt-list');
      for (const w of p.worktrees) {
        const li = htmlEl('li', `am-focus-wt am-state-${w.tone}`);
        li.append(htmlEl('span', 'am-focus-wt-branch', w.branch), htmlEl('span', 'am-focus-wt-owner', T(w.ownerWord)), htmlEl('span', `am-focus-wt-state am-state-${w.tone}`, T(w.word)), htmlEl('span', 'am-focus-wt-mission', w.mission || T('No mission')));
        rows.append(li);
      }
      wl.append(rows);
    }
    const kids = [head];
    if (p.last) kids.push(htmlEl('p', 'am-focus-last', `${p.last.time} · ${p.last.text}`));
    kids.push(ms.length ? list : htmlEl('p', 'am-focus-empty', p.ideas ? T(`${p.ideas} ${p.ideas === 1 ? 'idea' : 'ideas'} captured, no missions yet`) : T('No missions yet')));
    if (wl) kids.push(wl);
    panel.replaceChildren(...kids);
  }
  function paintSelection() {
    ring.remove();
    for (const rec of cellRecs.values()) rec.g.classList.toggle('am-selected-cell', rec.p.id === selected);
    if (!selected) return;
    for (const rec of cellRecs.values()) { const h = rec.hitsOf.find(x => x.id === selected); if (h) { const star = rec.g.querySelector(`[data-node-id="${CSS.escape(selected)}"]`); if (star) { ring.setAttribute('r', h.r - 4 + 8); star.append(ring); } } }
  }
  function build(animate = false) {
    if (destroyed || !layout) return;
    const animated = animate && cellRecs.size > 0 && canMove();
    let moved = false;
    const ordered = [...model.projects].sort((a, b) => (slotOf.get(a.id) ?? 1e9) - (slotOf.get(b.id) ?? 1e9));
    const cells = ordered.map((p, i) => ({p, cell: layout.cells[i] || layout.cells[layout.cells.length - 1]}));
    const seen = new Set(), spokes = [], hitNodes = [];
    for (const {p, cell} of cells) {
      seen.add(p.id);
      let rec = cellRecs.get(p.id);
      const sig = cellSig(p, cell), was = rec && rec.cell, wasState = rec && stateOf(rec.p);
      if (!rec || rec.sig !== sig) {
        const {g, hitsOf} = drawCell(p, cell);
        if (rec) rec.g.replaceWith(g);
        rec = Object.assign(rec || {}, {g, hitsOf, sig, p, cell}); cellRecs.set(p.id, rec);
        cellLayer.append(g);
        if (animated) {
          if (!was) riseCell(g, cell);
          else if (was.x !== cell.x || was.y !== cell.y) { glideCell(g, was, cell); moved = true; }
          else tintCell(g, wasState);
        }
      } else { rec.p = p; rec.cell = cell; }
      const state = stateOf(p), active = state === 'needs-you' || state === 'running';
      if (active || cells.length <= 24) {
        const e = edgePoint(cell, layout.core), dx = e.x - layout.core.x, dy = e.y - layout.core.y, d = Math.hypot(dx, dy) || 1, r0 = layout.core.radius * 1.5;
        spokes.push({id: p.id, state, d: `M${f(layout.core.x + dx / d * r0)},${f(layout.core.y + dy / d * r0)}L${f(e.x)},${f(e.y)}`, x0: f(layout.core.x + dx / d * r0), y0: f(layout.core.y + dy / d * r0), x1: f(e.x), y1: f(e.y)});
      }
      hitNodes.push({p, cell, rec});
    }
    for (const [id, rec] of cellRecs) if (!seen.has(id)) { if (animated) fadeCell(rec.g); else rec.g.remove(); rec.spoke?.remove(); cellRecs.delete(id); }
    spokeLayer.replaceChildren();
    // the spokes are redrawn at once, so while cells travel they stay out and then fade in: no line ever points at an empty slot
    if (moved) spokeLayer.animate([{opacity: 0}, {opacity: 0, offset: .55}, {opacity: 1}], {duration: tok('--dur-3', 200), easing: 'linear'});
    for (const s of spokes) {
      const path = svgEl('path', {class: `am-spoke am-spoke-${s.state}`, d: s.d}); spokeLayer.append(path); cellRecs.get(s.id).spoke = path; cellRecs.get(s.id).spokeD = s;
      if (s.state === 'running') { const m = svgEl('circle', {class: 'am-travel', r: 2.6}); const t = driftOf(options.seed, s.id); m.style.setProperty('--tp', Math.round(t.period / 2.4) + 'ms'); m.style.setProperty('--td', Math.round(t.delay / 2.4) + 'ms'); for (const [k, v] of [['--x0', s.x0], ['--y0', s.y0], ['--x1', s.x1], ['--y1', s.y1]]) m.style.setProperty(k, v + 'px'); spokeLayer.append(m); }
    }
    hits.replaceChildren();
    for (const {p, cell, rec} of hitNodes) {
      const info = {kind: T('Project'), title: p.name, state: stateOf(p), stateWord: wordOf(stateOf(p)), project: `${p.code}${p.total ? ' · ' + T(`${p.total} ${p.total === 1 ? 'mission' : 'missions'}`) : ''}`, line: p.last ? `${p.last.time} · ${p.last.text}` : '', action: T('Show missions')};
      const hit = svgEl('g', {class: 'am-chit', tabindex: 0, role: 'button', 'data-node-id': p.id, 'aria-label': describe(p)});
      hit.append(svgEl('rect', {x: f(cell.x), y: f(cell.y), width: f(cell.w), height: f(cell.h)}));
      bindHit(hit, info, p, {x: cell.x, y: cell.y, w: cell.w, h: cell.h}); hits.append(hit);
      for (const m of rec.hitsOf) {
        const mi = {kind: T('Mission'), title: m.label, state: m.state, stateWord: wordOf(m.state), project: p.name, line: p.last ? `${p.last.time} · ${p.last.text}` : '', action: T('Open mission')};
        const mh = svgEl('g', {class: 'am-chit am-chit-mission', tabindex: -1, 'aria-hidden': 'true', 'data-node-id': m.id});
        mh.append(svgEl('circle', {cx: f(m.x), cy: f(m.y), r: f(m.r)})); bindHit(mh, mi, p, {x: cell.x, y: cell.y, w: cell.w, h: cell.h}); hits.append(mh);
      }
    }
    core.setAttribute('transform', `translate(${f(layout.core.x)} ${f(layout.core.y)})`);
    drawCore();
    const ws = clamp(layout.core.radius * .32, 9, 14);
    wordmark.style.fontSize = ws + 'px'; wordmark.setAttribute('y', f(layout.core.radius * 1.6 + ws * 1.9)); runningText.style.fontSize = ws * .9 + 'px'; runningText.setAttribute('y', f(layout.core.radius * 1.6 + ws * 3.6));
    const needs = model.projects.reduce((t, p) => t + p.attention, 0);
    status.textContent = T(`${model.projects.length} projects. ${needs} need you.`);
    equivalent.replaceChildren(...(() => { const ul = htmlEl('ul'); for (const p of ordered) { const li = htmlEl('li'), b = htmlEl('button', '', describe(p)); b.type = 'button'; b.dataset.nodeId = p.id; li.append(b); ul.append(li); } return [ul]; })());
    renderFocus(); paintSelection(); motion();
  }
  // The current core (M3): its tier follows the core's size on screen, its marks follow the work and the emergency stop.
  function drawCore() {
    const needsYou = model.projects.some(p => p.attention > 0), running = model.projects.some(p => p.running > 0), R = layout.core.radius;
    coreTierNow = coreTier(R * 1.6, coreTierNow);
    coreMark.replaceChildren(...corePaths(R, 1.6, {tier: coreTierNow, stopped, needsYou, running}).map(q => {
      const el = svgEl(q.t || 'path', q.t ? {class: q.c, r: q.r} : {class: q.c, d: q.d});
      if (q.x1 !== undefined) for (const [k, v] of [['--x0', 0], ['--y0', 0], ['--x1', q.x1], ['--y1', q.y1]]) el.style.setProperty(k, v + 'px');
      return el;
    }));
    coreMark.dataset.state = stopped ? 'stopped' : running ? 'working' : needsYou ? 'needs-you' : 'calm'; coreMark.dataset.needs = String(needsYou && !stopped);
  }
  // The headline above the map can change height (a wrapped chip row, a late font) without the map's own box changing, so update() reads the inset again.
  function readInset(w, h) {
    inset = {...INSET, ...(typeof options.inset === 'function' ? options.inset(w, h) : options.inset)};
    panel.style.inset = `${f(inset.top)}px ${f(inset.right)}px ${f(inset.bottom)}px ${f(inset.left)}px`;
  }
  function relayout() {
    if (destroyed) return;
    const r = host.getBoundingClientRect(), w = Math.max(1, r.width), h = Math.max(1, r.height), step = Math.abs(w - width) + Math.abs(h - height) > 120 && cellRecs.size > 0;
    readInset(w, h);
    width = w; height = h; svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    const css = getComputedStyle(host); serif = css.getPropertyValue('--am-serif').trim() || 'serif'; sans = css.getPropertyValue('--am-sans').trim() || 'sans-serif';
    layout = layoutTerritories(Math.max(1, model.projects.length), w, h, inset);
    for (const rec of cellRecs.values()) rec.sig = '';
    build(step);
  }
  const open = chit => (chit.classList.contains('am-chit-mission') ? select : focus)(chit.dataset.nodeId);
  hits.addEventListener('click', e => { const c = e.target.closest('.am-chit'); if (c) open(c); });
  hits.addEventListener('keydown', e => {
    const id = e.target.closest('.am-chit')?.dataset.nodeId;
    if (!id) return;
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(e.target.closest('.am-chit')); }
    else if (e.key === 'Escape') { closeCard(); }
    else if (e.key.startsWith('Arrow')) {
      e.preventDefault();
      const nodes = [...hits.querySelectorAll('.am-chit:not(.am-chit-mission)')], cur = nodes.find(n => n.dataset.nodeId === id) || e.target.closest('.am-chit');
      const box = n => { const b = n.firstElementChild; return {x: +b.getAttribute('x') + +b.getAttribute('width') / 2, y: +b.getAttribute('y') + +b.getAttribute('height') / 2}; };
      if (!cur || !cur.firstElementChild.getAttribute('width')) return;
      const [ux, uy] = ({ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]})[e.key], from = box(cur);
      let best = null, score = Infinity;
      for (const n of nodes) { if (n === cur) continue; const b = box(n), dx = b.x - from.x, dy = b.y - from.y, fwd = dx * ux + dy * uy; if (fwd <= 0) continue; const v = Math.hypot(dx, dy) * (1 + Math.abs(dx * uy - dy * ux) / fwd); if (v < score) { score = v; best = n; } }
      best?.focus({preventScroll: true});
    }
  });
  equivalent.addEventListener('click', e => { const id = e.target.closest('button')?.dataset.nodeId; if (id) focus(id); });
  const onKey = e => { if (e.key !== 'Escape') return; if (card.classList.contains('am-on')) closeCard(); else if (focused && host.contains(document.activeElement)) focus(null); };
  document.addEventListener('keydown', onKey);
  media.addEventListener('change', motion); document.addEventListener('visibilitychange', motion);
  const observer = new ResizeObserver(relayout); observer.observe(host);
  const settle = () => { if (!destroyed && JSON.stringify(inset) !== JSON.stringify({...INSET, ...(typeof options.inset === 'function' ? options.inset(width, height) : options.inset)})) relayout(); };
  document.fonts?.addEventListener('loadingdone', settle);
  const seenObs = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries => { visible = entries[entries.length - 1].isIntersecting; motion(); }) : null; seenObs?.observe(host);
  const api = {
    update(next) {
      if (destroyed) return;
      model = next;
      readInset(width, height);
      const fresh = orderProjects(model.projects.filter(p => !slotOf.has(p.id)));
      for (const p of fresh) slotOf.set(p.id, slotOf.size);
      layout = layoutTerritories(Math.max(1, model.projects.length), width, height, inset);
      build(true);
    },
    setSelection: id => { if (!destroyed) { selected = id; paintSelection(); } },
    setTheme(name) { if (!destroyed) host.dataset.theme = name; },
    setReducedMotion(b) { reducedOverride = Boolean(b); if (!destroyed) motion(); },
    resize: relayout, fitView() {},
    element: host,
    setLive(b) { options.live = b === true; if (!destroyed) motion(); },
    setAmbient(on) { playing = on === true; if (!destroyed) motion(); },
    setStopped(on) { if (stopped !== (on === true)) { stopped = on === true; if (!destroyed && layout) drawCore(); } },
    pulse(edge) {
      if (destroyed || isReduced() || document.hidden || markers.size >= 6) return false;
      const [a, b] = String(edge).split(':')[0].split('->'), pid = model.projects.find(p => p.id === a || p.missions.some(m => m.id === a || m.id === b))?.id, s = cellRecs.get(pid)?.spokeD;
      if (!s) return false;
      const m = svgEl('circle', {r: 3, class: 'am-marker'});
      m.style.offsetPath = `path('${s.d}')`; pulseLayer.append(m); markers.add(m);
      const anim = m.animate([{offsetDistance: '0%', opacity: 0}, {offsetDistance: '10%', opacity: 1, offset: .1}, {offsetDistance: '90%', opacity: 1, offset: .9}, {offsetDistance: '100%', opacity: 0}], {duration: 900, easing: 'linear'});
      const done = () => { m.remove(); markers.delete(m); };
      anim.onfinish = done; anim.oncancel = done; emit('pulse', edge); return true;
    },
    on(event, fn) { if (!listeners.has(event)) listeners.set(event, new Set()); listeners.get(event).add(fn); return () => listeners.get(event)?.delete(fn); },
    destroy() {
      if (destroyed) return;
      destroyed = true; document.fonts?.removeEventListener('loadingdone', settle); observer.disconnect(); seenObs?.disconnect(); media.removeEventListener('change', motion); document.removeEventListener('visibilitychange', motion); document.removeEventListener('keydown', onKey); clearTimeout(cardTimer); clearTimeout(graceTimer); clearTimeout(hideTimer);
      for (const a of host.getAnimations({subtree: true})) a.cancel();
      markers.clear(); listeners.clear(); host.remove();
    }
  };
  relayout();
  return api;
}
