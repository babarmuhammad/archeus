// The Overview on a phone. One column and one scroll surface, list first: what is true (the state sentence, the ledger, the counts), the first decision with its Review button where the thumb
// is, the projects that need you most, then the detail in folded sections. There is no map on a phone: the list is the Overview.
import { h } from './dom.js';
import { present } from '../core-words.js';
import { clockLabel } from '../sim.js';
import { word, missionRow, projName } from './views.js';
import { stateMark, codeChip, projectTone } from './phone-list-ui.js';
import { openTell } from './chat.js';
import { overviewProjects } from './phone-model.js';
import { workHref } from '../page-model.js';

const LIVE_CAP = 5; // a hundred projects can run dozens of missions; the rest is one tap away in Work
const n1 = (n, one, many) => `${n} ${n === 1 ? one : many}`;
// The count chips open Work on that state. Verifying and a zero stopped count stay out of sight, as before.
function counters(ctx) {
  const sim = ctx.sim, ms = Object.values(sim.state.missions);
  const c = (n, label, role, view) => h('a', { class: 'ctr', 'data-role': role, 'data-zero': String(n === 0), href: workHref({ view }) }, h('b', null, String(n)), h('span', null, label));
  return h('nav', { class: 'counters', 'aria-label': 'Counts' },
    c(sim.attention().filter((i) => i.kind !== 'knowledge').length, 'needs you', 'needs_you', 'needs'), c(sim.liveWork().length, 'running', 'active', 'running'),
    c(ms.filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED').length, 'stopped', 'blocked', 'blocked'), c(ms.filter((m) => present('mission', m.state).cls === 'verifying').length, 'verifying', 'verifying', 'running'));
}

// The first thing that waits on the owner: project, title, what, why, and one 48 px Review button. Two more as compact rows, then the way to the rest.
function needsYou(ctx, att) {
  const sim = ctx.sim, st = sim.state, need = att.filter((a) => a.kind !== 'knowledge' && (a.group === 'Decide' || a.group === 'Review'));
  if (!need.length) return null;
  const to = (a) => (a.kind === 'approval' ? '#/work/' + a.ref : '#/work/' + a.mission_id), mission = (a) => (a.mission_id ? st.missions[a.mission_id] : null);
  const first = need[0], fm = mission(first), ap = first.kind === 'approval' ? st.approvals[first.ref] : null, chip = projName(sim, first.project_id);
  const more = need.slice(1, 3);
  return h('section', { class: 'np-need', 'aria-label': 'Needs you' },
    h('article', { class: 'np-card', 'data-key': 'pn-card' },
      h('p', { class: 'np-card-top' }, chip ? h('span', { class: 'np-pill' }, chip) : null, stateMark('needs_you', 'Needs you')),
      h('h2', { class: 'np-card-t' }, fm ? fm.title : first.reason),
      h('p', { class: 'np-kv' }, h('b', null, 'What'), ap ? ap.presented.what : first.reason),
      ap ? h('p', { class: 'np-kv' }, h('b', null, 'Why'), ap.presented.why) : null,
      h('a', { class: 'pn-review', href: to(first) }, 'Review')),
    ...more.map((a) => { const m = mission(a); return h('a', { class: 'np-row', href: to(a), 'data-key': 'np-' + a.id }, stateMark('needs_you', 'Needs you'), h('span', { class: 'np-row-t' }, m ? m.title : a.reason), h('span', { class: 'np-row-p' }, projName(sim, a.project_id))); }),
    need.length > 1 ? h('a', { class: 'np-all', href: workHref({ view: 'needs' }), 'data-key': 'np-all-need' }, 'All ' + need.length + ' in Work') : null);
}

function projectsList(ctx, ov) {
  const q = ctx.ui.nowQuery || '', model = overviewProjects({ projects: ov.projects, stateOf: (p) => projectTone(p).key, query: q });
  const row = (p) => {
    const tone = projectTone(p), bits = [n1(p.total, 'mission', 'missions'), p.attention ? p.attention + ' needs you' : p.running ? p.running + ' running' : null, p.last ? p.last.time : null].filter(Boolean).join(' · ');
    return h('a', { class: 'np-proj', href: workHref({ project: p.id }), 'data-key': 'np-proj-' + p.id, onclick: () => { ctx.ui.workProject = p.id; } },
      codeChip(p.code), h('span', { class: 'np-pn' }, h('span', { class: 'np-pname' }, p.name), h('span', { class: 'np-pmeta' }, bits)), stateMark(tone.cls, tone.word));
  };
  const search = model.searchable ? h('input', { class: 'np-search', type: 'search', 'aria-label': 'Search projects', placeholder: 'Search projects', 'data-key': 'np-search', autocomplete: 'off', enterkeyhint: 'search', value: q, oninput: (e) => {
    const pos = e.target.selectionStart; ctx.ui.nowQuery = e.target.value; ctx.render();
    const i = document.querySelector('[data-key="np-search"]'); if (i) { i.focus(); i.setSelectionRange(pos, pos); }
  } }) : null;
  return h('section', { class: 'np-projects', 'aria-label': 'Projects' },
    h('h2', { class: 'np-h' }, h('span', null, 'Projects'), h('span', { class: 'n' }, String(model.total))),
    search,
    model.rows.length ? h('div', { class: 'np-plist' }, ...model.rows.map(row)) : h('p', { class: 'np-none' }, (q ? 'No project matches.' : 'No projects yet.')),
    model.more > 0 || (model.total > model.rows.length) ? h('a', { class: 'np-all', href: '#/projects', 'data-key': 'np-all-projects' }, 'All ' + model.total + ' projects') : null);
}

// Happening now and Recent are folded until asked for, with the count in the summary; the fold survives the re-renders the simulation causes.
function details(ctx) {
  const st = ctx.sim.state, open = (ctx.ui.nowSecs = ctx.ui.nowSecs || {});
  const live = Object.values(st.missions).filter((m) => ['active', 'verifying', 'reviewing'].includes(present('mission', m.state).cls));
  const recent = st.events.filter((e) => /state_changed$/.test(e.type) && e.subject.kind === 'mission').slice(-6).reverse();
  const sec = (key, label, n, ...kids) => h('details', { class: 'np-sec', 'data-key': 'np-sec-' + key, open: open[key], ontoggle: (e) => { open[key] = e.currentTarget.open; } },
    h('summary', null, h('span', { class: 'gt' }, label), h('span', { class: 'n' }, String(n))), h('div', { class: 'np-sec-b now-panels' }, ...kids));
  return [
    sec('live', 'Happening now', live.length, live.length ? [...live.slice(0, LIVE_CAP).map((m) => missionRow(ctx, m, 'now')), live.length > LIVE_CAP ? h('a', { class: 'np-all', href: workHref({ view: 'running' }), 'data-key': 'np-all-live' }, 'All ' + live.length + ' in Work') : null] : h('p', { class: 'np-none' }, 'Nothing is running.')),
    sec('recent', 'Recent', recent.length, recent.length ? recent.map((e) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, (st.missions[e.subject.id] || { title: e.subject.id }).title, ': ', word('mission', e.payload.from), ' to ', word('mission', e.payload.to)), h('span', { class: 'b' }, clockLabel(e.at) + (e.actor === 'device' ? ' · you' : ' · Core')))) : h('p', { class: 'np-none' }, 'Nothing has changed yet.'))
  ];
}

// o: { ov, calm, sentence(text) -> nodes, ledger } from view-now.js, which owns the words both layouts share.
export function renderPhone(ctx, o) {
  const sim = ctx.sim, att = sim.attention();
  return h('div', { class: 'view np', 'data-calm': String(o.calm) },
    h('section', { class: 'np-hero' },
      h('h1', { class: 'state-sentence' + (o.calm ? ' calm' : ''), 'data-key': 'sentence' }, ...(o.calm ? ['Nothing running. Tell Archeus what to do.'] : o.sentence(sim.sentence()))),
      h('p', { class: 'ledger', 'data-key': 'ledger' }, o.ledger(o.ov.ledger)),
      o.calm ? h('button', { class: 'btn primary l np-tell', type: 'button', 'data-key': 'np-tell', onclick: () => openTell(ctx) }, 'Tell Archeus') : counters(ctx)),
    o.calm ? null : needsYou(ctx, att),
    projectsList(ctx, o.ov),
    o.calm ? null : details(ctx));
}
