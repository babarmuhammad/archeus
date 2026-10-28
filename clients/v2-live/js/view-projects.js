// Projects: every project as a cell that says what Archeus did there, grouped by what needs attention, so ten or a hundred projects still read at a glance.
// The groups, the count line and the search keep the page short; the quiet group folds away once there are many.
// Text is plain English: i18n translates the rendered DOM.
import {h} from './dom.js';
import {areasOf} from './areas-model.js';
import {present} from '../core-words.js';
import {buildOverview} from './map.js';
import {orderProjects, leadMission} from './constellation/territories.js';

export function projectState(missions) {
  const cls = missions.map(m => present('mission', m.state).cls);
  if (cls.some(c => ['needs_you', 'blocked', 'failed', 'reviewing'].includes(c))) return 'waiting';
  if (cls.some(c => ['active', 'planning', 'verifying'].includes(c))) return 'active';
  return missions.length && missions.every(m => m.state === 'COMPLETED') ? 'verified' : 'idle';
}

const WORD = {waiting: 'Waiting', active: 'Active', verified: 'Verified', idle: 'Quiet'};
const GROUPS = [['waiting', 'Needs you'], ['active', 'Running'], ['quiet', 'Quiet']];
const MANY = 12;
const MWORD = {'needs-you': 'Needs you', running: 'Running', done: 'Done', blocked: 'Blocked', idle: 'Quiet', paused: 'Paused', thinking: 'Planning'};
const n1 = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function cell(ctx, p, state) {
  const lead = leadMission(p), id = 'prj-' + p.id, selected = ctx.route.id === id;
  const counts = [n1(p.total, 'mission', 'missions'), p.attention ? p.attention + ' needs you' : null, p.running ? p.running + ' running' : null, p.ideas ? n1(p.ideas, 'idea', 'ideas') : null].filter(Boolean).join(' · ');
  return h('li', {class: 'pcell', 'data-state': state, 'aria-current': selected ? 'true' : null},
    h('div', {class: 'pc-top'}, h('span', {class: 'pc-code', 'aria-hidden': 'true'}, p.code), h('a', {class: 'pc-open', href: '#/projects/' + id, 'data-key': 'project-plate-' + id, 'aria-current': selected ? 'true' : null}, p.name),
      h('span', {class: 'pc-state'}, h('i', {class: 'pc-dot', 'aria-hidden': 'true'}), WORD[state])),
    h('p', {class: 'pc-last'}, p.last ? [h('time', null, p.last.time), ' ' + p.last.text] : lead ? lead.title + ' · ' + MWORD[lead.state] : 'Archeus has not acted here yet.'),
    h('div', {class: 'pc-foot'}, h('span', {class: 'pc-counts'}, counts),
      h('a', {class: 'pc-work', href: '#/work', 'data-key': 'project-work-' + p.id, onclick: e => { e.preventDefault(); ctx.ui.workProject = p.id; ctx.nav('#/work'); }}, 'Open work')));
}

const ideaRow = (ctx, i, p) => h('li', {class: 'pidea'},
  h('a', {href: '#/projects/' + i.id, 'data-key': 'project-plate-' + i.id, 'aria-current': ctx.route.id === i.id ? 'true' : null},
    h('span', {class: 'pc-code', 'aria-hidden': 'true'}, p.code), h('b', null, i.title), h('span', {class: 'pidea-meta'}, p.name + ' · Captured')));

// A heading, or a folded one when the list is long (the fold survives re-renders in ctx.ui).
function group(ctx, key, label, count, fold, body) {
  const head = [h('span', {class: 'gt'}, label), h('span', {class: 'n'}, String(count))];
  if (!fold) return h('section', {class: 'pgroup', 'data-group': key}, h('h2', null, ...head), body);
  return h('details', {class: 'pgroup', 'data-group': key, open: ctx.ui['fold-' + key], ontoggle: e => { ctx.ui['fold-' + key] = e.currentTarget.open; }}, h('summary', {'data-key': 'projects-fold-' + key}, ...head), body);
}

export function render(ctx) {
  const S = areasOf(ctx.sim).S(), ov = buildOverview(ctx.sim), q = (ctx.ui.projQuery || '').trim().toLowerCase();
  const state = new Map(ov.projects.map(p => [p.id, projectState(Object.values(S.missions).filter(m => m.project === p.id))]));
  const shown = orderProjects(ov.projects).filter(p => !q || p.name.toLowerCase().includes(q) || p.code.toLowerCase() === q);
  const nProj = ov.projects.length, many = nProj > MANY && !q;
  const byId = new Map(ov.projects.map(p => [p.id, p]));
  const ideas = S.ideas.filter(i => i.state === 'CAPTURED' && byId.has(i.project) && (!q || byId.get(i.project).name.toLowerCase().includes(q) || i.title.toLowerCase().includes(q)));
  const sections = GROUPS.map(([key, label]) => {
    const list = shown.filter(p => (key === 'quiet' ? !['waiting', 'active'].includes(state.get(p.id)) : state.get(p.id) === key));
    return list.length ? group(ctx, key, label, list.length, key === 'quiet' && many, h('ul', {class: 'pgrid'}, ...list.map(p => cell(ctx, p, state.get(p.id))))) : null;
  });
  const search = nProj > 8 ? h('input', {class: 'psearch', type: 'search', 'aria-label': 'Search projects', placeholder: 'Search projects', 'data-key': 'projects-search', value: ctx.ui.projQuery || '', oninput: e => {
    const pos = e.target.selectionStart; ctx.ui.projQuery = e.target.value; ctx.render();
    const i = document.querySelector('[data-key="projects-search"]'); if (i) { i.focus(); i.setSelectionRange(pos, pos); }
  }}) : null;
  const need = ov.projects.filter(p => p.attention).length, run = ov.projects.filter(p => p.running).length;
  const sub = nProj ? [n1(nProj, 'project', 'projects'), need ? need + ' need you' : null, run ? run + ' running' : null].filter(Boolean).join(' · ') : 'No projects yet.';
  return h('div', {class: 'projects-page'},
    h('header', {class: 'page-head'}, h('div', null, h('h1', null, 'Projects'), h('p', {class: 'sub'}, sub)), search),
    h('div', {class: 'view pview'}, ...sections,
      nProj && !shown.length ? h('p', {class: 'empty'}, 'No project matches.') : null,
      ideas.length ? group(ctx, 'ideas', 'Captured ideas', ideas.length, ideas.length > 6 && !q, h('ul', {class: 'pgrid pideas'}, ...ideas.map(i => ideaRow(ctx, i, byId.get(i.project))))) : null));
}
