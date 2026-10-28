// Work: one page for what is happening and what waits on you, as a list with a detail pane (the graph, js/constellation/workgraph.js, is the second layout).
// The address carries the state: #/work?view=running&project=notes&as=graph. Saved views, the project filter, the counts and the rows come from page-model.js.
// List and pane show the same missions and decisions; hover, focus and j/k fill the pane, a click opens the mission (inspector) as before.
import { h } from './dom.js';
import { picker } from './picker.js';
import { present } from '../core-words.js';
import { tr, translate } from './i18n.js';
import * as store from './store.js';
import { clockLabel } from '../sim.js';
import { panel, dnote, empty, badge, attentionItem, projName, word } from './views.js';
import { spineRow, spineCard } from './spine.js';
import { icon } from './icons.js';
import { STATE, themeOf } from './map.js';
import { createWorkGraph } from './constellation/workgraph.js';
import { WORK_VIEWS, workQuery, workHref, filterWork, workCounts, countLine, relTime, vocabOf, viewOfCls } from '../page-model.js';

const LEGEND = [['needs-you', 'Needs you'], ['running', 'Running'], ['blocked', 'Blocked'], ['done', 'Done']];
const MAX_NODES = 12, CAP = 8, CHIPS = 6;
const EMPTY = {
  needs: ['Nothing waits on you.', 'See what is running', 'running'], running: ['Nothing is running.', 'Tell Archeus what to do', 'tell'],
  blocked: ['Nothing is stuck.', 'See what is running', 'running'], done: ['Nothing has finished yet.', 'See what is running', 'running'], all: ['No work yet.', 'Tell Archeus what to do', 'tell']
};
let graph = null;

// The graph survives the re-renders the simulation causes; app.js destroys it when the route leaves Work.
export function leave() { if (graph) graph.destroy(); graph = null; }

function modelOf(sim, pf) {
  const st = sim.state, rank = (m) => ({ needs_you: 0, active: 1, verifying: 1, reviewing: 1, blocked: 2, failed: 2, done: 4 })[present('mission', m.state).cls] ?? 3;
  const all = Object.values(st.missions).filter((m) => !pf || m.project === pf).sort((a, b) => rank(a) - rank(b)), ms = all.slice(0, MAX_NODES);
  const nodes = ms.map((m) => ({ id: m.id, kind: 'Mission', label: m.title, word: tr(word('mission', m.state)), project: projName(sim, m.project), state: STATE[present('mission', m.state).cls] || 'idle' }));
  const asks = Object.values(st.approvals).filter((a) => a.state === 'PENDING' && ms.some((m) => m.id === a.mission));
  for (const a of asks) nodes.push({ id: a.id, kind: 'Decision', label: tr(a.kind === 'plan' ? 'Approve plan' : 'Allow action'), word: tr('Needs you'), project: projName(sim, a.project), state: 'needs-you' });
  return { nodes, edges: asks.map((a) => ({ from: a.mission, to: a.id })), hidden: all.length - ms.length };
}

export function render(ctx) {
  const sim = ctx.sim, st = sim.state, now = st.clock, ids = st.projects.map((p) => p.id);
  const q = workQuery(ctx.route.q || {}, ids);
  if (location.hash.includes('?')) ctx.ui.workProject = q.project; else q.project = ids.includes(ctx.ui.workProject) ? ctx.ui.workProject : null; // a bare #/work keeps the filter another page set
  const sel = ctx.route.id, pf = q.project, pn = pf && st.projects.find((p) => p.id === pf), asGraph = q.as === 'graph';
  const mine = (id) => !pn || id === pf, qs = location.hash.includes('?') ? location.hash.slice(location.hash.indexOf('?')) : '';
  const att = sim.attention(), cards = new Set(att.filter((a) => a.mission_id).map((a) => a.mission_id));
  const lastAt = new Map(); for (const e of st.events) if (e.mission) lastAt.set(e.mission, e.at);

  // Every entry is a mission row or a decision card; the same list feeds the counts, the filter and the groups.
  const entries = [
    ...att.map((a) => ({ id: a.id, kind: 'card', a, project: a.project_id, cls: a.group === 'Unblock' ? 'blocked' : 'needs_you', at: a.since })),
    ...Object.values(st.missions).filter((m) => !cards.has(m.id)).map((m) => ({ id: m.id, kind: 'row', m, project: m.project, cls: present('mission', m.state).cls, at: lastAt.get(m.id) || m.updated_at || 0 }))
  ];
  const counts = workCounts(entries, pf), shown = filterWork(entries, { view: q.view, project: pf });
  counts.by = {}; for (const e of entries) if (e.project) counts.by[e.project] = (counts.by[e.project] || 0) + 1;
  const model = asGraph ? modelOf(sim, pf) : null, gids = new Set(model ? model.nodes.map((n) => n.id) : []);

  // The row or card the route points at carries aria-current; data-link ties it to the graph.
  const link = (el, ...keys) => {
    const own = keys.filter(Boolean), node = own.find((k) => gids.has(k));
    el.dataset.link = own.join(' ');
    if (sel && own.includes(sel)) el.setAttribute('aria-current', 'true');
    if (node) { el.addEventListener('pointerenter', () => graph.hover(node)); el.addEventListener('pointerleave', () => graph.hover(null)); }
    return el;
  };
  const rowOf = (e) => {
    const m = e.m, p = present('mission', m.state), x = Object.values(st.executions).find((z) => z.mission === m.id && (z.state === 'RUNNING' || z.state === 'LOST'));
    const meta = [projName(sim, m.project), m.branch, m.reason || (x ? sim.reading(x) : null)].filter(Boolean).join(' · ');
    return link(h('a', { class: 'mrow wk-row', href: '#/work/' + m.id, 'data-key': 'm-' + m.id, 'data-peek-id': e.id, 'data-vocab': vocabOf(p.cls) },
      h('span', { class: 't' }, badge('mission', m.state), h('span', { class: 'name' }, m.title)), h('span', { class: 'm' }, meta, x ? h('span', { class: 'vh' }, ' ') : null),
      h('time', { class: 'mrow-time', title: clockLabel(e.at) }, relTime(now, e.at)), h('span', { class: 'sp' }, spineRow(m.state, m.held_from))), m.id);
  };
  const cardOf = (e) => h('div', { class: 'panel', 'data-peek-id': e.id }, link(attentionItem(ctx, e.a), e.a.ref, e.a.mission_id));
  const open = (ctx.ui.workMore = ctx.ui.workMore || {});
  // A long group shows its first rows and one button for the rest; the choice survives re-renders.
  const capped = (key, items, draw, wrap) => {
    const more = open[key] || items.length <= CAP + 2 ? items : items.slice(0, CAP);
    return [wrap(...more.map(draw)), items.length > more.length ? h('button', { class: 'btn quiet wk-more', type: 'button', 'data-key': 'work-more-' + key, onclick: () => { open[key] = true; ctx.render(); } }, 'Show all ' + items.length) : null];
  };
  const stack = (...k) => h('div', { class: 'stack' }, ...k), attRows = (...k) => h('div', { class: 'att-rows' }, ...k);
  const body = (key, items) => {
    const cs = items.filter((e) => e.kind === 'card').sort((a, b) => a.at - b.at), rs = items.filter((e) => e.kind === 'row').sort((a, b) => b.at - a.at);
    return [...(cs.length ? capped(key + 'c', cs, cardOf, attRows) : []), ...(rs.length ? capped(key, rs, rowOf, stack) : [])];
  };
  const of = (v) => shown.filter((e) => viewOfCls(e.cls) === v);

  // ---- the toolbar: saved views (address), project filter, layout ----
  const views = h('nav', { class: 'tabs wk-tabs', 'aria-label': 'Saved views' }, ...WORK_VIEWS.map(([v, label]) => h('a', { class: 'tab wk-tab', href: workHref({ view: v, project: pf, as: q.as }), 'aria-current': q.view === v ? 'true' : null, 'data-key': 'work-view-' + v }, h('span', { class: 'gt' }, label), h('span', { class: 'tn' }, String(counts[v])))));
  const setProject = (id) => { ctx.ui.workProject = id; ctx.nav(workHref({ view: q.view, project: id, as: q.as })); };
  const chip = (key, label, on, go) => h('button', { class: 'chip', type: 'button', 'aria-pressed': String(on), 'data-key': key, onclick: go }, label);
  const allChip = chip('work-all', pn ? 'Show all projects' : 'All projects', !pn, () => setProject(null));
  // Past six projects the chips give way to the shared searchable picker, with the count per project beside each name.
  const pick = st.projects.length > CHIPS ? picker({ key: 'work-project', label: tr('Project filter'), cls: 'pick', value: pf || '', onPick: (v) => setProject(v || null),
    items: [{ value: '', label: tr('All projects'), meta: String(counts.all) }].concat(st.projects.map((p) => ({ value: p.id, label: p.name, meta: String(counts.by[p.id] || 0) }))) }) : null;
  const filter = st.projects.length > CHIPS ? h('div', { class: 'wk-filter' }, pick, pn ? allChip : null)
    : h('div', { class: 'chips', role: 'group', 'aria-label': 'Project filter' }, allChip, ...st.projects.map((p) => chip('work-p-' + p.id, p.name, pf === p.id, () => setProject(pf === p.id ? null : p.id))));
  const layoutOpt = (as, label) => h('a', { class: 'seg-opt', href: workHref({ view: q.view, project: pf, as }), 'aria-current': q.as === as ? 'true' : null, 'data-key': 'work-as-' + as }, label);
  const total = entries.length, need = counts.needs;
  const sub = h('p', { class: 'sub wk-sub', 'data-key': 'work-count' }, shown.length === total ? total + ' missions and decisions' : 'Showing ' + countLine(shown.length, total), need ? h('span', { class: 'wk-need' }, need + (need === 1 ? ' needs you' : ' need you')) : null);

  // ---- the list ----
  const none = () => {
    const [text, label, to] = pn && !counts.all ? ['No work in ' + pn.name + ' yet.', 'Show all projects', 'all'] : EMPTY[q.view];
    const go = to === 'tell' ? h('button', { class: 'btn', type: 'button', 'data-key': 'work-empty-action', onclick: () => document.querySelector('[data-key="tell"]')?.click() }, label)
      : h('a', { class: 'btn', href: workHref({ view: to === 'all' ? 'all' : to }), 'data-key': 'work-empty-action', onclick: () => { if (to === 'all') ctx.ui.workProject = null; } }, label);
    return h('div', { class: 'wk-empty' }, h('p', { class: 'empty' }, text), go);
  };
  const fold = (key, label, n, kids) => h('details', { class: 'panel wk-fold', open: open['fold-' + key], ontoggle: (e) => { open['fold-' + key] = e.currentTarget.open; } }, h('summary', { 'data-key': 'work-fold-' + key }, h('span', { class: 'gt' }, label), h('span', { class: 'n' }, String(n))), ...kids);
  let list;
  if (q.view === 'all') {
    const needs = of('needs'), run = of('running'), stuck = of('blocked'), done = of('done');
    list = h('div', { class: 'work-list' },
      h('section', { class: 'panel work-need' }, h('h2', null, h('span', { class: 'gt' }, 'Needs you'), h('span', { class: 'n' }, String(needs.length))), needs.length ? body('need', needs) : empty('Nothing waits on you.', 'clear')),
      run.length ? panel('Running', run.length, ...body('active', run)) : null,
      stuck.length ? panel('Blocked', stuck.length, ...body('stuck', stuck)) : null,
      done.length ? fold('done', 'Done', done.length, body('done', done)) : null,
      panel('Ideas', st.ideas.filter((i) => mine(i.project)).length));
  } else list = h('div', { class: 'work-list' }, shown.length ? h('section', { class: 'panel wk-one' }, ...body(q.view, shown)) : none());

  // ---- the detail pane: what Archeus did and for which project, for the row under the pointer or focus ----
  if (qs) list.querySelectorAll('a[href^="#/work/"]').forEach((a) => a.setAttribute('href', a.getAttribute('href') + qs)); // opening a row and closing it again keeps the view
  const pane = h('aside', { class: 'wk-pane', 'aria-label': 'Selected work', 'data-key': 'work-pane' });
  const evLine = (e) => (e.type === 'approval.requested' ? 'Asked you to decide' : word('mission', e.payload.to));
  // A pause lands a few seconds after the request, and only a paused mission can resume: Undo waits for the halt, up to 15 s.
  const undoPause = (id, tries = 0) => { if (st.missions[id].state === 'PAUSED') ctx.act('resume', id); else if (tries < 30) setTimeout(() => undoPause(id, tries + 1), 500); };
  const paint = (id) => {
    const e = entries.find((x) => x.id === id);
    ctx.ui.workPeek = e ? e.id : null;
    document.querySelectorAll('[data-peek-id]').forEach((n) => { if (e && n.dataset.peekId === e.id) n.setAttribute('data-peek', 'true'); else n.removeAttribute('data-peek'); });
    pane.replaceChildren();
    if (!e) { pane.append(h('p', { class: 'empty' }, 'Select a row to see what Archeus did.')); translate(pane); return; }
    if (e.kind === 'card' && !e.a.mission_id) { pane.append(h('p', { class: 'ax-eyebrow' }, projName(sim, e.project) || 'Archeus'), attentionItem(ctx, e.a)); translate(pane); return; }
    const m = e.m || st.missions[e.a.mission_id], p = present('mission', m.state), proj = st.projects.find((x) => x.id === m.project);
    const evs = st.events.filter((x) => x.mission === m.id && (x.type === 'mission.state_changed' || x.type === 'approval.requested')).slice(-4).reverse();
    const x = Object.values(st.executions).find((z) => z.mission === m.id && (z.state === 'RUNNING' || z.state === 'LOST')), reading = x ? sim.reading(x) : null;
    const approval = m.approval && st.approvals[m.approval] && st.approvals[m.approval].state === 'PENDING' ? m.approval : null;
    const pause = m.state === 'EXECUTING' ? h('button', { class: 'btn', type: 'button', 'data-key': 'work-pause', onclick: () => { const r = ctx.act('pause', m.id); if (r.ok) ctx.toast('Pausing “' + m.title + '”.', { action: { label: 'Undo', run: () => undoPause(m.id) } }); } }, 'Pause')
      : m.state === 'PAUSED' ? h('button', { class: 'btn', type: 'button', onclick: () => ctx.act('resume', m.id) }, 'Resume') : null;
    const why = e.kind === 'card' ? e.a.reason : m.reason || reading;
    pane.append(
      h('p', { class: 'ax-eyebrow' }, proj ? proj.name : 'Archeus'),
      h('h2', { class: 'wk-pane-t' }, m.title),
      h('p', { class: 'wk-pane-s' }, badge('mission', m.state), h('span', { class: 'wk-pane-v' }, vocabOf(p.cls)), h('time', { title: clockLabel(e.at) }, relTime(now, e.at))),
      why ? h('p', { class: 'wk-pane-r' }, why) : null,
      spineCard(m.state, m.held_from),
      h('h3', { class: 'wk-pane-h' }, 'What Archeus did'),
      evs.length ? h('ol', { class: 'wk-did' }, ...evs.map((v) => h('li', null, h('span', null, evLine(v)), h('time', { title: clockLabel(v.at) }, relTime(now, v.at))))) : h('p', { class: 'empty' }, 'Nothing recorded yet.'),
      h('div', { class: 'actions wk-pane-a' },
        approval ? h('a', { class: 'btn primary', href: '#/work/' + approval, 'data-key': 'work-pane-decide' }, 'Open decision') : h('a', { class: 'btn primary', href: '#/work/' + m.id, 'data-key': 'work-pane-open' }, 'Open mission'),
        h('a', { class: 'btn', href: '#/replay/' + m.id }, 'Open Replay'), pause));
    translate(pane);
  };
  if (!asGraph) {
    const idOf = (t) => { const n = t.closest && t.closest('[data-peek-id]'); return n ? n.dataset.peekId : null; };
    const go = (t) => { const k = idOf(t); if (k && k !== ctx.ui.workPeek) paint(k); };
    let dwell = 0;
    list.addEventListener('focusin', (e) => go(e.target));
    list.addEventListener('pointerover', (e) => { if (e.pointerType === 'mouse') { clearTimeout(dwell); dwell = setTimeout(() => go(e.target), 120); } });
    list.addEventListener('pointerleave', () => clearTimeout(dwell));
    const first = shown.find((e) => e.cls === 'needs_you') || shown[0], keep = shown.find((e) => e.id === ctx.ui.workPeek);
    ctx.mounts.push(() => paint(keep ? keep.id : first && first.id));
  }

  // ---- the graph layout keeps the earlier structure ----
  if (asGraph) {
    if (!graph) {
      graph = createWorkGraph(h('div'), { t: tr, theme: themeOf(), reduced: store.reducedMotion(), label: tr('Work graph: missions and decisions grouped by what they wait on. The list below has the same content.'),
        onSelect: (id) => ctx.nav(ctx.route.id === id ? workHref(q) : '#/work/' + id + qs),
        onReview: (id) => { const a = Object.values(sim.state.approvals).find((x) => x.state === 'PENDING' && x.mission === id); ctx.nav('#/work/' + (a ? a.id : id)); } });
      graph.element.addEventListener('wg-hover', (e) => document.querySelectorAll('[data-link]').forEach((x) => x.classList.toggle('is-linked', !!e.detail && x.dataset.link.split(' ').includes(e.detail))));
    }
    graph.setTheme(themeOf()); graph.setReduced(store.reducedMotion()); graph.update(model); graph.setSelection(gids.has(sel) ? sel : null);
  } else leave();

  const split = asGraph
    ? h('div', { class: 'work-split' },
      h('section', { class: 'work-graph', 'aria-label': tr('Work graph') }, graph.element, h('ul', { class: 'work-legend', 'aria-hidden': 'true' }, ...LEGEND.map(([s, w]) => h('li', { 'data-s': s }, h('span', { class: 'wl-dot' }), w)), model.hidden > 0 ? h('li', { class: 'wl-more' }, 'Graph shows the first ' + MAX_NODES + ' of ' + (MAX_NODES + model.hidden) + ' missions, the list has all') : null)), list)
    : h('div', { class: 'work-master' }, list, pane);
  return h('div', { class: 'work-page' },
    h('header', { class: 'page-head wk-head' }, h('div', null, h('h1', null, 'Work'), sub), h('nav', { class: 'seg', 'aria-label': 'Layout' }, layoutOpt('list', 'List'), layoutOpt('graph', 'Graph'))),
    h('div', { class: 'view work-view', 'data-as': q.as },
      h('div', { class: 'wk-bar' }, views, filter),
      split,
      dnote('E03', 'One page for Work and Attention: missions and decisions grouped by what they wait on, as a list with a detail pane and as a graph. The spine shows where each mission is (A13); an obligation is a 12 % amber tint with its state in words (B09).')));
}
