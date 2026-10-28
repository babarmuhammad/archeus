import {layoutWork, workCore, placeLabels, overlaps, coversNode, nearestNeighbour, stateKey} from './geometry.js';
import {bodyMarkup, coreMarkup, coreTier} from './nodeart.js';

// The Work graph (concepts 04 and 08): the shared node art, labels and tokens of the live map on a layout of its own (layoutWork).
// Model: {nodes: [{id, kind: 'Mission'|'Decision', label, word, project, state}], edges: [{from, to}]}. Plain SVG, no camera: the graph is sparse and sits beside its list.
const NS = 'http://www.w3.org/2000/svg';
const esc = s => String(s).replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`);
const f = v => +v.toFixed(1);
const iconOf = n => (n.kind === 'Decision' || stateKey(n.state) === 'needs-you' ? 'doc-search' : stateKey(n.state) === 'done' ? 'check' : 'doc');
const insetFor = w => (w < 480 ? {top: 14, bottom: 14, left: 14, right: 14} : {top: 28, bottom: 28, left: 40, right: 40});

export function createWorkGraph(container, {t = x => x, theme = 'dark', reduced = false, label = 'Work graph', onSelect = () => {}, onReview = () => {}} = {}) {
  const host = document.createElement('div');
  host.className = 'archeus-map wg'; host.dataset.theme = theme; host.dataset.reduced = String(reduced);
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('role', 'group'); svg.setAttribute('aria-label', label);
  host.append(svg); container.append(host);
  const measureCtx = document.createElement('canvas').getContext('2d');
  let model = {nodes: [], edges: []}, selected = null, hovered = null, lit = null, size = '', pos = [], seen = new Set(), destroyed = false, drawn = '';
  const onHover = id => { if (id !== hovered) api.hover(id); host.dispatchEvent(new CustomEvent('wg-hover', {detail: id})); };

  function draw() {
    const {width, height} = host.getBoundingClientRect();
    if (destroyed || width < 2 || height < 2) return;
    const key = JSON.stringify([model, width, height, selected, theme, reduced]);
    if (key === drawn) return;
    drawn = key; size = `${width}x${height}`;
    const inset = insetFor(width), narrow = width < 480, rich = width >= 520, text = narrow ? 13 : width < 900 ? 15 : 17;
    const css = getComputedStyle(host), serif = css.getPropertyValue('--am-serif').trim() || 'serif', sans = css.getPropertyValue('--am-sans').trim() || 'sans-serif';
    pos = layoutWork(model, width, height, 'v2-live-work', inset);
    const core = workCore(width, height, inset), by = new Map(pos.map(n => [n.id, n])), kid = new Set(model.edges.map(e => e.to));
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    let out = `<g class="wg-spokes">${pos.filter(n => !kid.has(n.id)).map(n => `<path class="am-spoke" data-node-id="${esc(n.id)}" d="M${f(core.x)},${f(core.y)}L${f(n.x)},${f(n.y)}"/>`).join('')}</g><g class="am-edges">`;
    for (const e of model.edges) {
      const a = by.get(e.from), b = by.get(e.to);
      if (!a || !b) continue;
      const d = Math.hypot(b.x - a.x, b.y - a.y) || 1, ux = (b.x - a.x) / d, uy = (b.y - a.y) / d, p = [a.x + ux * a.radius, a.y + uy * a.radius, b.x - ux * b.radius, b.y - uy * b.radius].map(f);
      out += `<g class="am-edge am-edge-asks am-accent-needs-you" data-from="${esc(e.from)}" data-to="${esc(e.to)}"><path class="am-line" d="M${p[0]},${p[1]}L${p[2]},${p[3]}"/><path class="am-joint" d="M${p[0]},${p[1]}h0M${p[2]},${p[3]}h0"/></g>`;
    }
    out += `</g><g class="am-core am-state-core" transform="translate(${f(core.x)} ${f(core.y)})">${coreMarkup(core.radius, 1.5, {tier: coreTier(core.radius * 1.5)})}</g><g class="am-nodes">`;
    const fresh = [];
    for (const n of pos) {
      if (!seen.has(n.id)) fresh.push(n.id);
      out += `<g class="wg-node am-state-${stateKey(n.state)}${n.id === selected ? ' am-selected' : ''}" data-node-id="${esc(n.id)}"${n.entry ? ` data-entry="${esc(n.entry)}"` : ''} transform="translate(${f(n.x)} ${f(n.y)})">${bodyMarkup(n, iconOf(n))}<circle class="am-select-ring" r="${f(n.radius + 11)}"/></g>`;
    }
    out += '</g>';
    // The Review button goes beside the first needs-you mission (the selected one when it needs you), on the first side that clears every node.
    const need = pos.filter(n => n.kind === 'Mission' && stateKey(n.state) === 'needs-you'), lead = need.find(n => n.id === selected) || need[0];
    const keep = {x: core.x - core.keep, y: core.y - core.keep, width: core.keep * 2, height: core.keep * 2};
    const spots = lead && !narrow ? [[-56, lead.radius + 12], [-56, -lead.radius - 56], [lead.radius + 12, -22], [-lead.radius - 124, -22], [-130, lead.radius + 12], [8, lead.radius + 12], [-56, lead.radius + 40], [-56, -lead.radius - 84]]
      .map(([dx, dy]) => ({id: lead.id, x: lead.x + dx, y: lead.y + dy, width: 112, height: 44}))
      .filter(b => b.x >= 8 && b.x + b.width <= width - 8 && b.y >= 8 && b.y + b.height <= height - 8 && !overlaps(b, keep, 6) && !pos.some(o => coversNode(b, o, 2))) : [];
    const review = spots[0] || null;
    measureCtx.font = `400 ${text}px ${serif}`;
    const measureMeta = s => { measureCtx.font = `500 ${text * .68}px ${sans}`; const w = measureCtx.measureText(s).width + s.length * text * .68 * .14; measureCtx.font = `400 ${text}px ${serif}`; return w; };
    // Only missions are named on the graph; a decision is a small node on its mission's edge (the list and the node's own name say what it asks).
    const decisions = pos.filter(n => n.kind === 'Decision').map(n => ({x: n.x - n.radius - 3, y: n.y - n.radius - 3, width: n.radius * 2 + 6, height: n.radius * 2 + 6}));
    const boxes = placeLabels(pos.filter(n => n.kind !== 'Decision'), width, height, {selected, size: text, rich, budget: narrow ? 5 : 14, all: !narrow, metaOf: n => String(n.project || '').toUpperCase(), measureMeta,
      measure: s => measureCtx.measureText(s).width, obstacles: [keep, ...decisions, ...(review ? [review] : [])]});
    // A label that sits far from its node gets a hairline back to it.
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    out += '<g class="am-leaders" aria-hidden="true">' + boxes.map(b => {
      const n = by.get(b.id), ex = clamp(n.x, b.x, b.x + b.width), ey = clamp(n.y, b.y, b.y + b.height), d = Math.hypot(ex - n.x, ey - n.y);
      return d - n.radius > 30 ? `<path class="am-leader" d="M${f(n.x + (ex - n.x) / d * n.radius)},${f(n.y + (ey - n.y) / d * n.radius)}L${f(ex)},${f(ey)}"/>` : '';
    }).join('') + '</g><g class="am-labels" aria-hidden="true">';
    const fit = (s, room, px) => { measureCtx.font = `400 ${px}px ${serif}`; while (s.length > 2 && measureCtx.measureText(s).width > room) s = s.slice(0, -2) + '…'; return s; };
    for (const b of boxes) {
      const n = by.get(b.id), meta = b.size * .68, state = stateKey(n.state), word = rich && n.word ? fit(n.word, b.width, b.size * .72) : '';
      out += `<g class="am-label am-state-${state}${n.id === selected ? ' am-selected-label' : ''}" data-node-id="${esc(n.id)}">`
        + (rich && n.project ? `<text class="am-label-meta wg-project" x="${f(b.x + 2)}" y="${f(b.y + meta * 1.05)}" style="font-size:${f(meta)}px">${esc(String(n.project).toUpperCase())}</text>` : '')
        + `<text class="am-label-title" x="${f(b.x + 2)}" y="${f(rich ? b.y + meta * 1.4 + b.size : b.y + b.size)}" style="font-size:${b.size}px">${esc(b.text)}</text>`
        + (word ? `<text class="am-label-sub wg-word" x="${f(b.x + 2)}" y="${f(b.y + meta * 1.4 + b.size * 1.95)}" style="font-size:${f(b.size * .72)}px">${esc(word)}</text>` : '') + '</g>';
    }
    out += '</g>';
    if (review) out += `<g class="am-review am-state-needs-you" tabindex="0" role="button" data-key="wg-review" data-node-id="${esc(lead.id)}" aria-label="${esc(t('Review'))}: ${esc(lead.label)}" transform="translate(${f(review.x + 56)} ${f(review.y + 22)})"><rect x="-56" y="-22" width="112" height="44" rx="6"/><text x="-42" y="5" class="am-review-label">${esc(t('Review'))}</text><path d="M26 0h14m-5-5 5 5-5 5" class="am-review-arrow"/></g>`;
    out += '<g class="am-hits">' + pos.map(n => `<g class="am-hit" tabindex="0" role="button" data-key="wg-${esc(n.id)}" data-node-id="${esc(n.id)}" aria-pressed="${n.id === selected}" aria-label="${esc(`${n.label}, ${t(n.kind)}, ${n.word || t(stateKey(n.state))}${n.project ? ', ' + n.project : ''}`)}" transform="translate(${f(n.x)} ${f(n.y)})"><circle r="${f(Math.max(narrow ? 24 : 22, n.radius))}"/></g>`).join('') + '</g>';
    const had = svg.contains(document.activeElement) ? document.activeElement.dataset.key : null;
    svg.innerHTML = out;
    if (had) svg.querySelector(`[data-key="${CSS.escape(had)}"]`)?.focus({preventScroll: true});
    api.hover(hovered); applyLit();
    if (!reduced && !document.hidden) fresh.forEach((id, i) => svg.querySelector(`.wg-node[data-node-id="${CSS.escape(id)}"]`)?.animate([{opacity: 0}, {opacity: 1}], {duration: 240, delay: i * 40, easing: 'ease-out', fill: 'backwards'}));
    seen = new Set(pos.map(n => n.id));
  }
  svg.addEventListener('click', e => {
    const hit = e.target.closest('.am-hit'), rev = e.target.closest('.am-review');
    if (rev) onReview(rev.dataset.nodeId); else if (hit) onSelect(hit.dataset.nodeId);
  });
  svg.addEventListener('keydown', e => {
    const hit = e.target.closest('.am-hit'), rev = e.target.closest('.am-review');
    if (e.key === 'Enter' || e.key === ' ') { if (rev) { e.preventDefault(); onReview(rev.dataset.nodeId); } else if (hit) { e.preventDefault(); onSelect(hit.dataset.nodeId); } }
    else if (hit && e.key.startsWith('Arrow')) { e.preventDefault(); const next = nearestNeighbour(pos, hit.dataset.nodeId, e.key); if (next) svg.querySelector(`.am-hit[data-node-id="${CSS.escape(next)}"]`)?.focus(); }
  });
  const point = e => { const h = e.target.closest('.am-hit'); return h ? h.dataset.nodeId : null; };
  svg.addEventListener('pointerover', e => { const id = point(e); if (id) onHover(id); });
  svg.addEventListener('pointerout', e => { if (point(e) && !svg.contains(e.relatedTarget?.closest?.('.am-hit'))) onHover(null); });
  // Highlight: the same dim as the Overview hover (host data-hot, am-in on what stays lit, see map.css). Nothing is re-drawn: classes only, so a filter change costs a few toggles.
  const q = sel => svg.querySelectorAll(sel), rootOf = id => { const e = model.edges.find(x => x.to === id); return e ? e.from : id; };
  function applyLit() {
    if (lit === null) delete host.dataset.hot; else host.dataset.hot = 'on';
    const on = id => lit !== null && lit.has(id);
    for (const el of q('.wg-node')) { const x = on(el.dataset.nodeId); el.classList.toggle('am-in', x); el.querySelector('.am-star')?.classList.toggle('am-in', x); }
    for (const el of q('.am-label')) el.classList.toggle('am-in', on(el.dataset.nodeId));
    for (const el of q('.am-edge')) el.classList.toggle('am-in', on(el.dataset.from) && on(el.dataset.to));
    for (const el of q('.am-spoke')) el.classList.toggle('am-in', on(el.dataset.nodeId));
    markPath();
  }
  // The hovered or selected node stays readable whatever the filter says, and the path from the core to it (spoke, then its decision edge) is drawn stronger.
  function markPath() {
    const id = hovered || selected, chain = new Set(id ? [id, rootOf(id)] : []);
    for (const el of q('.wg-node')) el.classList.toggle('wg-focus', chain.has(el.dataset.nodeId) && el.dataset.nodeId === id);
    for (const el of q('.am-spoke')) el.classList.toggle('wg-path', !!id && el.dataset.nodeId === rootOf(id));
    for (const el of q('.am-edge')) el.classList.toggle('wg-path', !!id && (el.dataset.to === id || el.dataset.from === id));
  }
  svg.addEventListener('focusin', e => { const id = point(e); if (id) onHover(id); });
  svg.addEventListener('focusout', e => { if (point(e) && !svg.contains(e.relatedTarget?.closest?.('.am-hit'))) onHover(null); });
  const observer = new ResizeObserver(draw); observer.observe(host);
  const api = {
    element: host,
    update(next) { model = {nodes: next.nodes.map(n => ({...n})), edges: (next.edges || []).map(e => ({...e}))}; draw(); },
    setSelection(id) { selected = id; draw(); },
    hover(id) { hovered = id; svg.querySelector('.wg-hover')?.classList.remove('wg-hover'); if (id) svg.querySelector(`.wg-node[data-node-id="${CSS.escape(id)}"]`)?.classList.add('wg-hover'); markPath(); },
    // ids: the node ids that stay lit, or null for no highlight (everything at full colour).
    setHighlight(ids) { lit = ids ? new Set(ids) : null; applyLit(); },
    get lit() { return lit; },
    setTheme(name) { theme = name; host.dataset.theme = name; },
    setReduced(bool) { reduced = bool === true; host.dataset.reduced = String(reduced); },
    get size() { return size; },
    destroy() { destroyed = true; observer.disconnect(); host.remove(); }
  };
  return api;
}
