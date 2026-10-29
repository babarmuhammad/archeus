// Projects on a phone. One column, list first, one scroll surface: a row per project that says what Archeus did there, grouped by what asks most of the owner, so ten or a hundred projects
// are never a wall of cards. A group lists 20 and asks for more; the quiet group folds away once there are many. A project's worktrees are its children, folded under its row.
// Ideas and pinned things, which the phone Work page leaves out, sit at the bottom as folded sections. Text is plain English: i18n translates the rendered DOM.
import { h } from './dom.js';
import { icon } from './icons.js';
import { areasOf } from './areas-model.js';
import { buildOverview } from './map.js';
import * as store from './store.js';
import { stateMark, codeChip, moreButton, projectTone } from './phone-list-ui.js';
import { projectGroups, PROJECT_STEP } from './phone-lists-model.js';
import { OVERVIEW_SEARCH_ABOVE } from './phone-model.js';
import { sortProjects, sortOf, PROJECT_SORTS, relTime } from '../page-model.js';

const GROUPS = [{ key: 'needs', label: 'Needs you' }, { key: 'running', label: 'Running' }, { key: 'quiet', label: 'Quiet' }];
const GROUP_OF = { needs_you: 'needs', running: 'running' };
// A worktree that needs the owner reads as a decision, a missing one as stopped; the others as what they are.
const TREE_CLS = { active: 'active', stale: 'needs_you', missing: 'blocked', merged: 'done', abandoned: 'inactive' };
const n1 = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function worktrees(p) {
  return h('ul', { class: 'pp-trees', id: 'pp-trees-' + p.id }, ...p.worktrees.map((w) => {
    const main = [h('span', { class: 'pp-tb' }, w.branch), h('span', { class: 'pp-to' }, w.ownerWord), stateMark(TREE_CLS[w.state] || 'inactive', w.word)];
    return h('li', { class: 'pp-tree', 'data-state': w.state, 'data-key': 'pp-wt-' + w.id }, w.missionId ? h('a', { class: 'pp-tl', href: '#/work/' + w.missionId }, ...main) : h('span', { class: 'pp-tl' }, ...main));
  }));
}

function row(ctx, p, now, open) {
  const tone = projectTone(p), id = 'prj-' + p.id, trees = p.worktrees.length, shown = !!open[p.id];
  const counts = [n1(p.total, 'mission', 'missions'), p.attention ? p.attention + ' need you' : null, p.running ? p.running + ' running' : null].filter(Boolean).join(' · ');
  const last = p.last ? [h('time', { title: p.last.time }, relTime(now, p.last.at)), ' · ' + p.last.text] : 'Archeus has not acted here yet.';
  return h('li', { class: 'pp-row', 'data-state': tone.key, 'data-key': 'pp-row-' + p.id },
    h('a', { class: 'pp-main', href: '#/projects/' + id, 'data-key': 'project-plate-' + id, 'aria-current': ctx.route.id === id ? 'true' : null },
      codeChip(p.code), h('span', { class: 'pp-name' }, p.name), stateMark(tone.cls, tone.word), h('span', { class: 'pp-last' }, ...[].concat(last))),
    h('div', { class: 'pp-foot' }, h('span', { class: 'pp-counts' }, counts),
      trees ? h('button', { class: 'pp-wt', type: 'button', 'data-key': 'project-wt-' + id, 'aria-expanded': String(shown), 'aria-controls': 'pp-trees-' + p.id, onclick: () => { open[p.id] = !shown; ctx.render(); } },
        n1(trees, 'worktree', 'worktrees'), icon('chevron', 16)) : null),
    shown ? worktrees(p) : null);
}

// A heading, or a folded one when the list is long; the fold survives the re-renders the simulation causes.
function section(ctx, key, label, count, fold, body) {
  const head = [h('span', { class: 'gt' }, label), h('span', { class: 'n' }, String(count))];
  if (!fold) return h('section', { class: 'pp-sec', 'data-group': key }, h('h2', { class: 'np-h' }, ...head), body);
  return h('details', { class: 'np-sec pp-fold', 'data-group': key, open: ctx.ui['fold-' + key], ontoggle: (e) => { ctx.ui['fold-' + key] = e.currentTarget.open; } }, h('summary', { 'data-key': 'projects-fold-' + key }, ...head), h('div', { class: 'np-sec-b' }, body));
}

// Ideas and pinned things as one folded section each, shown only when there is something in them.
function extras(ctx, A, S, byId) {
  const open = (ctx.ui.ppSecs = ctx.ui.ppSecs || {}), pages = (ctx.ui.ppPages = ctx.ui.ppPages || {});
  const fold = (key, label, n, ...kids) => h('details', { class: 'np-sec', 'data-key': 'pp-sec-' + key, open: open[key], ontoggle: (e) => { open[key] = e.currentTarget.open; } },
    h('summary', null, h('span', { class: 'gt' }, label), h('span', { class: 'n' }, String(n))), h('div', { class: 'np-sec-b' }, ...kids));
  const line = (href, code, title, sub, key) => h('li', null, h('a', { class: 'pp-item', href, 'data-key': key }, code ? codeChip(code) : h('span'), h('span', { class: 'pp-it' }, title), h('span', { class: 'pp-is' }, sub)));
  const ideas = S.ideas.filter((i) => i.state === 'CAPTURED' && byId.has(i.project)), shownIdeas = ideas.slice(0, PROJECT_STEP * (1 + (pages.ideas || 0)));
  const pins = A.X.pins.map((id) => {
    if (S.missions[id]) { const m = S.missions[id], p = byId.get(m.project); return line('#/work/' + id, p && p.code, m.title, p ? p.name : '', 'pp-pin-' + id); }
    const i = S.ideas.find((x) => x.id === id), p = byId.get(i ? i.project : id.replace(/^prj-/, ''));
    return i ? line('#/projects/' + id, p && p.code, i.title, p ? p.name : '', 'pp-pin-' + id) : p ? line('#/projects/' + id, p.code, p.name, 'Project', 'pp-pin-' + id) : null;
  }).filter(Boolean);
  return [
    pins.length ? fold('pinned', 'Pinned', pins.length, h('ul', { class: 'pp-items' }, ...pins)) : null,
    ideas.length ? fold('ideas', 'Captured ideas', ideas.length, h('ul', { class: 'pp-items' }, ...shownIdeas.map((i) => line('#/projects/' + i.id, byId.get(i.project).code, i.title, byId.get(i.project).name, 'project-plate-' + i.id))),
      ideas.length > shownIdeas.length ? moreButton(Math.min(PROJECT_STEP, ideas.length - shownIdeas.length), 'projects-more-ideas', () => { pages.ideas = (pages.ideas || 0) + 1; ctx.render(); }) : null) : null
  ];
}

export function renderPhone(ctx) {
  const A = areasOf(ctx.sim), S = A.S(), ov = buildOverview(ctx.sim), now = ctx.sim.state.clock;
  const q = (ctx.ui.projQuery || '').trim().toLowerCase(), nProj = ov.projects.length, searchable = nProj > OVERVIEW_SEARCH_ABOVE, searching = searchable && !!q;
  const sort = sortOf(store.get('projsort')), pages = (ctx.ui.ppPages = ctx.ui.ppPages || {}), open = (ctx.ui.ppTrees = ctx.ui.ppTrees || {});
  const shown = sortProjects(ov.projects, sort).filter((p) => !searching || p.name.toLowerCase().includes(q) || p.code.toLowerCase() === q);
  const byId = new Map(ov.projects.map((p) => [p.id, p]));
  const groups = sort === 'attention' ? projectGroups(shown, (p) => GROUP_OF[projectTone(p).key] || 'quiet', GROUPS, { pages, many: nProj > OVERVIEW_SEARCH_ABOVE, searching })
    : projectGroups(shown, () => 'all', [{ key: 'all', label: 'All projects' }], { pages });
  const sections = groups.map((g) => section(ctx, g.key, g.label, g.count, g.fold, h('div', null,
    h('ul', { class: 'pp-list' }, ...g.rows.map((p) => row(ctx, p, now, open))),
    g.left ? moreButton(g.next, 'projects-more-' + g.key, () => { pages[g.key] = (pages[g.key] || 0) + 1; ctx.render(); }) : null)));
  const need = ov.projects.filter((p) => p.attention).length, run = ov.projects.filter((p) => p.running).length;
  const sub = nProj ? [searching ? shown.length + ' of ' + n1(nProj, 'project', 'projects') : n1(nProj, 'project', 'projects'), need ? need + ' need you' : null, run ? run + ' running' : null].filter(Boolean).join(' · ') : 'No projects yet.';
  const search = searchable ? h('input', { class: 'np-search', type: 'search', 'aria-label': 'Search projects', placeholder: 'Search projects', 'data-key': 'projects-search', autocomplete: 'off', enterkeyhint: 'search', value: ctx.ui.projQuery || '', oninput: (e) => {
    const pos = e.target.selectionStart; ctx.ui.projQuery = e.target.value; ctx.render();
    const i = document.querySelector('[data-key="projects-search"]'); if (i) { i.focus(); i.setSelectionRange(pos, pos); }
  } }) : null;
  const sorter = nProj > 1 ? h('div', { class: 'seg pp-sort', role: 'group', 'aria-label': 'Sort projects' }, ...PROJECT_SORTS.map(([id, label]) => h('button', { class: 'seg-opt', type: 'button', 'aria-pressed': String(sort === id), 'data-key': 'projects-sort-' + id, onclick: () => { store.set('projsort', id); ctx.render(); } }, label))) : null;
  return h('div', { class: 'projects-page pp' },
    h('header', { class: 'page-head' }, h('div', null, h('h1', null, 'Projects'), h('p', { class: 'sub' }, sub))),
    h('div', { class: 'view pview' }, sorter, search, ...sections,
      nProj && !shown.length ? h('p', { class: 'np-none' }, 'No project matches.') : null,
      ...extras(ctx, A, S, byId)));
}
