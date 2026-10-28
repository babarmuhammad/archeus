// Work on a phone. List first: one compact header (state chips, a project picker, List | Graph), then sections with sticky heads that stop at 20 rows each.
// The graph is a view of its own that fills the space between the bars (js/workgraph.js); the address carries the state, as on the desktop: #/work?view=running&project=notes&as=graph.
import { h } from './dom.js';
import { present } from '../core-words.js';
import { clockLabel } from '../sim.js';
import { picker } from './picker.js';
import { icon } from './icons.js';
import { spineRow } from './spine.js';
import { edgeRow } from './phone-pages.js';
import { stateMark, codeChip, moreButton } from './phone-list-ui.js';
import { projectCodes } from './project-code.js';
import { createPhoneGraph } from './workgraph.js';
import { STATE } from './map.js';
import { workChips, workSections, rankProjects, phoneGraphPick } from './phone-lists-model.js';
import { workHref, relTime } from '../page-model.js';

let graph = null;
export function leavePhone() { if (graph) graph.destroy(); graph = null; }

const RANK = { needs_you: 0, active: 1, verifying: 1, reviewing: 1, blocked: 2, failed: 2, done: 4 };
const LEGEND = [['needs', 'Needs you', 'needs-you'], ['running', 'Running', 'running'], ['blocked', 'Blocked', 'blocked'], ['done', 'Done', 'done']];

// What one entry (a mission row or a decision card) says on a phone: its words, where it opens, and the one action a card carries.
function describe(ctx, e) {
  const st = ctx.sim.state;
  if (e.kind === 'row') {
    const m = e.m, p = present('mission', m.state);
    return { title: m.title, cls: p.cls, word: p.label, href: '#/work/' + m.id, act: null, m, ids: [m.id] };
  }
  const a = e.a, m = a.mission_id ? st.missions[a.mission_id] : null, need = a.group === 'Decide' || a.group === 'Review';
  const p = ['approval', 'verification', 'mission'].includes(a.kind) ? present('mission', m ? m.state : 'APPROVAL_REQUIRED') : { cls: need ? 'needs_you' : 'blocked', label: need ? 'Needs you' : 'Blocked' };
  const go = (label, href) => ({ label, href }), run = (label, fn) => ({ label, run: fn });
  const act = a.kind === 'approval' ? go('Open decision', '#/work/' + a.ref) : a.kind === 'verification' ? go('Open review', '#/work/' + m.id) : a.kind === 'mission' ? go('Open', '#/work/' + m.id)
    : a.kind === 'worktree' ? go('Open project', '#/projects/prj-' + a.project_id) : a.kind === 'account' ? go('Open Settings', '#/settings')
    : a.kind === 'knowledge' ? run('Remember', () => ctx.act('confirm', a.ref)) : run(a.state === 'SUSPENDED' ? 'Re-enable' : 'Approve', () => ctx.act('enable', a.ref));
  return { title: m ? m.title : a.reason, cls: p.cls, word: p.label, href: act.href || (m ? '#/work/' + m.id : null), act, m, ids: [a.ref, a.mission_id, e.id].filter(Boolean) };
}

export function renderPhone(ctx, d) {
  const { q, pf, pn, qs, entries, counts, shown } = d, st = ctx.sim.state, now = st.clock, sel = ctx.route.id;
  const names = new Map(st.projects.map((p) => [p.id, p.name])), codes = new Map(st.projects.map((p, i) => [p.id, projectCodes(st.projects.map((x) => x.name))[i]]));
  const keep = { view: q.view, project: pf }, hrefOf = (o) => workHref({ ...keep, ...o });
  const setProject = (id) => { ctx.ui.workProject = id; ctx.nav(workHref({ view: q.view, project: id, as: q.as })); };

  // The project picker is the shared bottom sheet (search above 12, 48 px options); projects that ask most of you come first.
  const ranked = rankProjects(entries.map((e) => ({ project: e.project, cls: e.cls })), st.projects);
  const projectPick = picker({ key: 'work-project', label: 'Project filter', cls: 'wp-pick', value: pf || '', text: pn ? pn.name : 'All projects', onPick: (v) => setProject(v || null),
    items: [{ value: '', label: 'All projects', meta: String(counts.all) }, ...ranked.map(({ p, all }) => ({ value: p.id, label: p.name, meta: String(all) }))] });
  const chipsFor = workChips(counts, q.view);
  const chip = (c) => h('a', { class: 'chip wp-chip', href: hrefOf({ view: c.id, as: q.as }), 'aria-current': c.on ? 'true' : null, 'data-key': 'work-view-' + c.id }, h('span', null, c.label), h('span', { class: 'tn' }, String(c.n)));
  const morePick = picker({ key: 'work-more-states', label: 'More states', cls: 'wp-more', value: q.view, text: 'More', onPick: (v) => ctx.nav(hrefOf({ view: v, as: q.as })),
    items: chipsFor.more.map((c) => ({ value: c.id, label: c.label, meta: String(c.n) })) });
  const seg = h('nav', { class: 'seg wp-seg', 'aria-label': 'Layout' }, ...[['list', 'List'], ['graph', 'Graph']].map(([as, label]) => h('a', { class: 'seg-opt', href: hrefOf({ as }), 'aria-current': q.as === as ? 'true' : null, 'data-key': 'work-as-' + as }, label)));
  const filtered = q.view !== 'all' || !!pf;

  if (q.as === 'graph') return graphView(ctx, { q, pf, pn, entries, counts, shown, filtered, hrefOf, projectPick, describe: (e) => ({ ...describe(ctx, e), project: names.get(e.project) || '' }) });

  leavePhone();
  const row = (e) => {
    const x = describe(ctx, e), id = x.m ? x.m.id : e.id, here = sel && (x.ids.includes(sel));
    const main = [h('span', { class: 'wr-title' }, x.title), h('span', { class: 'wr-meta' }, stateMark(x.cls, x.word), names.get(e.project) ? h('span', { class: 'wr-proj' }, codeChip(codes.get(e.project)), h('span', { class: 'vh' }, names.get(e.project))) : null,
      e.at ? h('time', { class: 'wr-time', title: clockLabel(e.at) }, relTime(now, e.at)) : null, x.m && !x.act ? h('span', { class: 'sp' }, spineRow(x.m.state, x.m.held_from)) : null)];
    const body = x.href ? h('a', { class: 'wr-main', href: x.href + (x.href.startsWith('#/work/') ? qs : ''), 'data-key': e.kind === 'row' ? 'm-' + id : e.a.id, 'aria-current': here ? 'true' : null }, ...main) : h('div', { class: 'wr-main', 'data-key': e.a.id }, ...main);
    const act = x.act && (x.act.href ? h('a', { class: 'btn l wr-act', href: x.act.href + (x.act.href.startsWith('#/work/') ? qs : ''), 'data-key': 'wr-act-' + e.id }, x.act.label) : h('button', { class: 'btn l wr-act', type: 'button', 'data-key': 'wr-act-' + e.id, onclick: x.act.run }, x.act.label));
    return h('li', { class: 'wr', 'data-view': e.cls }, body, act);
  };
  const pages = (ctx.ui.workPages = ctx.ui.workPages || {});
  const rows = shown.map((e) => ({ id: e.id, cls: e.cls, at: e.at, e }));
  const sections = workSections(rows, pages).map((s) => h('section', { class: 'wr-sec', 'data-key': 'work-sec-' + s.key, 'aria-label': s.label },
    h('h2', { class: 'wr-head' }, h('span', { class: 'gt' }, s.label), h('span', { class: 'n' }, String(s.count))),
    h('ul', { class: 'wr-list' }, ...s.rows.map((r) => row(r.e))),
    s.left ? moreButton(s.next, 'work-more-' + s.key, () => { pages[s.key] = (pages[s.key] || 0) + 1; ctx.render(); }) : null));
  const none = h('div', { class: 'wk-empty' }, h('p', { class: 'empty' }, pn && !counts.all ? 'No work in ' + pn.name + ' yet.' : 'Nothing here.'),
    h('a', { class: 'btn l', href: workHref({ view: 'all' }), 'data-key': 'work-empty-action', onclick: () => { ctx.ui.workProject = null; } }, 'Show everything'));
  return h('div', { class: 'work-page' }, h('div', { class: 'view wkp' },
    h('header', { class: 'wp-head' },
      edgeRow(h('div', { class: 'wp-chips', role: 'group', 'aria-label': 'Show' }, ...chipsFor.chips.map(chip), morePick)),
      h('div', { class: 'wp-tools' }, projectPick, seg),
      filtered ? h('p', { class: 'wp-count', 'data-key': 'work-count' }, 'Showing ' + shown.length + ' of ' + entries.length) : null),
    sections.length ? h('div', { class: 'wr-secs' }, ...sections) : none));
}

// ---------- the graph view ----------
function graphView(ctx, g) {
  const { q, pf, entries, counts, shown, filtered, hrefOf, projectPick, describe: about } = g;
  if (!graph) graph = createPhoneGraph({ onSelect: (id) => { ctx.ui.wgSel = ctx.ui.wgSel === id ? null : id; ctx.render(); } });
  const { picked, more } = phoneGraphPick(entries, shown, filtered, (e) => RANK[e.cls] ?? 3, ctx.ui.wgDrawn || []);
  ctx.ui.wgDrawn = picked.map((e) => e.id);
  const nodes = picked.map((e) => { const x = about(e); return { id: e.id, cls: x.cls, state: STATE[x.cls] || 'idle', title: x.title, word: x.word, project: x.project, x }; });
  const on = nodes.find((n) => n.id === ctx.ui.wgSel) || null;
  graph.update({ nodes, selected: on ? on.id : null, label: 'Work graph: missions and decisions as nodes round the core. The list has the same content.' });

  const legend = edgeRow(h('div', { class: 'wg-chips', role: 'group', 'aria-label': 'Filter by state' }, projectPick,
    ...LEGEND.map(([v, label, s]) => h('button', { class: 'chip s wg-chip', type: 'button', 'data-s': s, 'data-key': 'work-legend-' + v, 'aria-pressed': String(q.view === v), onclick: () => ctx.nav(hrefOf({ view: q.view === v ? 'all' : v, as: 'graph' })) },
      h('span', { class: 'wl-dot' }), h('span', null, label), h('span', { class: 'tn' }, String(counts[v]))))));
  const open = on && (on.x.act || { label: 'Open', href: on.x.href });
  const dock = h('div', { class: 'wg-dock', 'data-key': 'wg-dock' }, on
    ? [h('div', { class: 'wg-card' }, h('p', { class: 'wg-card-m' }, stateMark(on.cls, on.word), on.project ? h('span', { class: 'wg-card-p' }, on.project) : null), h('p', { class: 'wg-card-t' }, on.title)),
      open.href ? h('a', { class: 'btn primary l wg-open', href: open.href, 'data-key': 'wg-open' }, open.label) : h('button', { class: 'btn primary l wg-open', type: 'button', 'data-key': 'wg-open', onclick: open.run }, open.label)]
    : [h('p', { class: 'wg-hint' }, nodes.length ? 'Tap a node to see the mission.' : ''), more > 0 ? h('a', { class: 'btn l wg-more', href: hrefOf({ as: 'list' }), 'data-key': 'work-graph-more' }, '+' + more + ' more in the list') : null]);
  return h('div', { class: 'work-page wkg' }, h('div', { class: 'view wkgv' },
    h('header', { class: 'wg-bar' }, legend, h('a', { class: 'btn l wg-done', href: hrefOf({ as: 'list' }), 'data-key': 'work-as-list' }, 'Done')),
    h('div', { class: 'wg-stage' },
      h('div', { class: 'wg-area' }, graph.el,
        nodes.length ? h('button', { class: 'btn l wg-fit', type: 'button', 'data-key': 'wg-fit', onclick: () => graph.fit() }, icon('expand', 18), 'Fit')
          : h('div', { class: 'wg-empty', 'data-key': 'work-graph-empty' }, h('p', null, 'Nothing matches this filter.'), h('a', { class: 'btn l', href: workHref({ as: 'graph' }), 'data-key': 'work-clear-filter', onclick: () => { ctx.ui.workProject = null; } }, 'Clear filter'))),
      dock)));
}
