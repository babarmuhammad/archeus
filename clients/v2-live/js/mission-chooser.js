// The Replay mission chooser: a trigger that shows the mission you are on, and a panel (popover on a desktop, full sheet on a phone) to find another one.
// Search, a project scope, the Work states with counts, recents, and sections that stop at 20 rows until you ask for more, so 240 missions are never a wall.
// The model (filter, count, rank, cap) is mission-chooser-model.js; this file draws it. Keys: type to filter, arrows, PageUp/PageDown, Enter, Esc.
import { h, clear } from './dom.js';
import { icon, glyph } from './icons.js';
import * as store from './store.js';
import { translate } from './i18n.js';
import { openPopup, closePopup } from './picker.js';
import { openSheet } from './sheet.js';
import { isPhone } from './viewport.js';
import { badge, word } from './views.js';
import { present } from '../core-words.js';
import { relTime, viewOfCls as viewOf } from '../page-model.js';
import { recordedSteps } from '../replay-model.js';
import { FACETS, CAP, TOP_PROJECTS, filterRows, facetCounts, projectCounts, rankProjects, sections, pushRecent, recentRows, remembered, stops } from '../mission-chooser-model.js';

const T = (en, it) => (store.get('lang') === 'it' ? it : en);
let uid = 0;

function rowsOf(sim) {
  const st = sim.state, last = new Map(), steps = recordedSteps(st.events), names = new Map(st.projects.map((p) => [p.id, p.name]));
  for (const e of st.events) if (e.mission) last.set(e.mission, e.at);
  return Object.values(st.missions).map((m) => {
    const cls = present('mission', m.state).cls;
    return { id: m.id, title: m.title, project: m.project, projectName: names.get(m.project) || m.project, branch: m.branch || '', state: m.state, cls, facet: viewOf(cls), at: last.get(m.id) || m.updated_at || 0, steps: steps.get(m.id) || 0 };
  });
}

// ctx: the app context. current: the mission on screen. onPick(id) goes there. Returns the trigger button.
export function missionChooser(ctx, { current, onPick, key = 'rp-mission' }) {
  const st = ctx.sim.state, rows = rowsOf(ctx.sim), projects = st.projects, now = st.clock;
  const here = rows.find((r) => r.id === current.id), recent = store.get('rprecent');
  if (here && recent[0] !== here.id) store.set('rprecent', pushRecent(recent, here.id)); // the last five missions replayed, by being on one
  const pr = projects.find((p) => p.id === current.project);

  const trigger = h('button', { class: 'pk mc-trigger', type: 'button', 'data-key': key, 'aria-haspopup': 'dialog', 'aria-expanded': document.querySelector('.mc-pop, .mc-sheet') ? 'true' : 'false',
    'aria-label': T('Mission', 'Missione') + ': ' + current.title + ', ' + (pr ? pr.name + ', ' : '') + word('mission', current.state),
    onclick: () => { if (document.querySelector('.mc-pop')) closePopup(true); else open(); } },
  h('span', { class: 'mc-tg', 'data-role': present('mission', current.state).cls, 'aria-hidden': 'true' }, glyph(present('mission', current.state).cls, 16)),
  h('span', { class: 'mc-ts' }, h('span', { class: 'mc-tt' }, current.title), h('span', { class: 'mc-tm' }, [pr && pr.name, word('mission', current.state)].filter(Boolean).join(' · '))),
  h('span', { class: 'pk-v' }, icon('chevron', 16)));

  function open() {
    const pick = (id, close) => { close(true); if (id !== current.id) onPick(id); else store.set('rprecent', pushRecent(store.get('rprecent'), id)); };
    if (isPhone()) {
      const sheet = openSheet({ id: 'rp-chooser', title: T('Replay a mission', 'Rivedi una missione'), detents: ['full'], initial: 'full', content: null });
      const p = panel((id) => pick(id, () => sheet.close()), false);
      sheet.el.querySelector('.sheet-body').append(p.el); sheet.el.classList.add('mc-sheet'); translate(p.el);
      return;
    }
    openPopup({ key, trigger, label: T('Choose a mission', 'Scegli una missione'), build: (pop, close) => {
      pop.classList.add('mc-pop'); const p = panel((id) => pick(id, close), true); pop.append(p.el);
      const fit = () => { if (!pop.isConnected) { removeEventListener('scroll', fit, true); return; } const w = pop.offsetWidth, l = parseFloat(pop.style.left) || 0, room = innerWidth - 8 - w; if (l > room) pop.style.left = Math.max(8, room) + 'px'; };
      requestAnimationFrame(fit); addEventListener('scroll', fit, true);
      return p.focus;
    } });
  }

  // The panel is the same on both surfaces. `choose(id)` closes it and goes.
  function panel(choose, auto) {
    const id = 'mc' + (++uid), saved = remembered(store.get('rpchooser'), projects), ranked = rankProjects(rows, projects);
    const f = { q: '', project: saved.project, facet: saved.facet, history: false }, caps = {};
    let act = 0, list = [], moreOpen = false, pq = '';
    const remember = () => store.set('rpchooser', { project: f.project, facet: f.facet });

    const q = h('input', { type: 'search', class: 'mc-q', 'data-key': 'mc-q', role: 'combobox', 'aria-expanded': 'true', 'aria-controls': id + '-l', 'aria-autocomplete': 'list', autocomplete: 'off', spellcheck: 'false',
      placeholder: T('Search title, project, branch or id', 'Cerca titolo, progetto, ramo o id'), 'aria-label': T('Search missions', 'Cerca missioni'), autofocus: auto ? '' : null });
    const scope = h('div', { class: 'mc-scope', role: 'group', 'aria-label': T('Project', 'Progetto') });
    const pmBox = h('div', { class: 'mc-pmbox' });
    const facets = h('div', { class: 'mc-facets', role: 'group', 'aria-label': T('State', 'Stato') });
    const box = h('div', { class: 'mc-list', role: 'listbox', id: id + '-l', 'aria-label': T('Missions', 'Missioni') });
    const live = h('p', { class: 'mc-live', role: 'status' });
    const el = h('div', { class: 'mc', 'data-key': 'mc' }, h('div', { class: 'mc-top' }, q, scope, pmBox, facets), box, live);

    const chip = (label, n, on, onclick, k, zero) => h('button', { class: 'chip s', type: 'button', 'aria-pressed': String(on), 'data-key': k, 'data-zero': zero ? '' : null, onclick },
      h('span', { class: 'mc-cl' }, label), n == null ? null : h('span', { class: 'tn' }, String(n)));
    const setAct = (n, scroll = true) => {
      const opts = box.querySelectorAll('[role=option]');
      if (!opts.length) { q.removeAttribute('aria-activedescendant'); return; }
      act = (n + opts.length) % opts.length;
      opts.forEach((o, i) => { if (i === act) o.setAttribute('data-act', ''); else o.removeAttribute('data-act'); });
      q.setAttribute('aria-activedescendant', opts[act].id);
      if (scroll) opts[act].scrollIntoView({ block: 'nearest' });
    };
    const rowEl = (r, i, prefix) => h('div', { class: 'mc-o', role: 'option', id: id + '-o' + i, 'aria-selected': String(r.id === current.id), 'data-value': r.id, 'data-key': 'mc-o-' + prefix + r.id,
      onmousedown: (e) => e.preventDefault(), onclick: () => choose(r.id) },
    h('span', { class: 'mc-ot' }, r.title), h('span', { class: 'mc-on' }, r.steps ? (r.steps === 1 ? T('1 step', '1 passo') : T(r.steps + ' steps', r.steps + ' passi')) : T('no steps', 'nessun passo')),
    h('span', { class: 'mc-om' }, badge('mission', r.state), h('span', null, [r.projectName, r.branch].filter(Boolean).join(' · ')), h('time', null, relTime(now, r.at))),
    r.id === current.id ? h('span', { class: 'mc-oc', 'aria-hidden': 'true' }, icon('check', 18)) : null);

    function drawScope() {
      clear(scope); clear(pmBox);
      const pc = projectCounts(rows, f), top = ranked.slice(0, TOP_PROJECTS), extra = f.project && !top.some((p) => p.id === f.project) ? ranked.find((p) => p.id === f.project) : null;
      const set = (p) => () => { f.project = p; moreOpen = false; remember(); draw(); };
      scope.append(chip(T('All projects', 'Tutti i progetti'), pc.all, !f.project, set(null), 'mc-p-all'),
        ...[...top, ...(extra ? [extra] : [])].map((p) => chip(p.name, pc.by.get(p.id) || 0, f.project === p.id, set(p.id), 'mc-p-' + p.id, !pc.by.get(p.id) && f.project !== p.id)));
      if (ranked.length > TOP_PROJECTS + 1) {
        scope.append(h('button', { class: 'chip s mc-moreb', type: 'button', 'aria-expanded': String(moreOpen), 'data-key': 'mc-more-projects', onclick: () => { moreOpen = !moreOpen; pq = ''; drawScope(); if (moreOpen) pmBox.querySelector('.mc-pq')?.focus(); else q.focus(); } },
          T('More projects', 'Altri progetti'), h('span', { class: 'tn' }, String(ranked.length - TOP_PROJECTS))));
        if (moreOpen) {
          const rest = ranked.slice(TOP_PROJECTS).filter((p) => !pq || p.name.toLowerCase().includes(pq.toLowerCase())), shown = rest.slice(0, CAP);
          const inp = h('input', { type: 'search', class: 'mc-pq', 'data-key': 'mc-pq', placeholder: T('Find a project', 'Cerca un progetto'), 'aria-label': T('Find a project', 'Cerca un progetto'), autocomplete: 'off', value: pq,
            oninput: (e) => { pq = e.target.value; const pos = pq.length; drawScope(); const n = pmBox.querySelector('.mc-pq'); n.focus(); n.setSelectionRange(pos, pos); },
            onkeydown: (e) => { if (e.key === 'Escape' && moreOpen) { e.preventDefault(); e.stopPropagation(); moreOpen = false; drawScope(); scope.querySelector('.mc-moreb').focus(); } } });
          pmBox.append(h('div', { class: 'mc-pm' }, inp, h('div', { class: 'mc-pl' }, ...shown.map((p) => h('button', { class: 'mc-pi', type: 'button', 'aria-pressed': String(f.project === p.id), 'data-key': 'mc-p-' + p.id, onclick: set(p.id) },
            h('span', null, p.name), h('span', { class: 'tn' }, String(pc.by.get(p.id) || 0)))), rest.length > shown.length ? h('p', { class: 'mc-pn' }, T('Type to narrow ' + (rest.length - shown.length) + ' more', 'Scrivi per restringere altri ' + (rest.length - shown.length))) : null, !rest.length ? h('p', { class: 'mc-pn' }, T('No project by that name.', 'Nessun progetto con quel nome.')) : null)));
        }
      }
    }
    function drawFacets() {
      clear(facets);
      const c = facetCounts(rows, f), set = (v) => () => { f.facet = v; remember(); draw(); };
      facets.append(chip(T('All', 'Tutte'), c.all, f.facet === 'all', set('all'), 'mc-f-all'),
        ...FACETS.map(([v, label]) => chip(label, c[v], f.facet === v, set(v), 'mc-f-' + v, !c[v] && f.facet !== v)),
        chip(T('With steps', 'Con passi'), null, f.history, () => { f.history = !f.history; draw(); }, 'mc-history'));
    }
    function draw() {
      drawScope(); drawFacets(); clear(box);
      const plain = !f.q && !f.project && f.facet === 'all' && !f.history, recents = plain ? recentRows(rows, store.get('rprecent')): [], secs = sections(rows, f, caps);
      list = stops(recents, secs);
      let i = 0;
      const group = (title, n, kids) => { const gid = id + '-g' + i; box.append(h('div', { role: 'group', 'aria-labelledby': gid }, h('div', { class: 'mc-gh', id: gid }, h('span', { class: 'gt' }, title), n != null ? h('span', { class: 'n' }, String(n)) : null), ...kids)); };
      if (recents.length) group(T('Recent', 'Recenti'), null, recents.map((r) => rowEl(r, i++, 'r-')));
      for (const s of secs) {
        const kids = s.rows.map((r) => rowEl(r, i++, ''));
        if (s.more) kids.push(h('div', { class: 'mc-more', role: 'option', id: id + '-o' + i++, 'data-key': 'mc-more-' + s.facet, onmousedown: (e) => e.preventDefault(),
          onclick: () => { caps[s.facet] = (caps[s.facet] || 0) + CAP; const at = list.findIndex((x) => x.type === 'more' && x.facet === s.facet); draw(); setAct(at); } },
        T('Show ' + Math.min(CAP, s.more) + ' more', 'Mostra altre ' + Math.min(CAP, s.more)), h('span', { class: 'n' }, T(s.more + ' not shown', s.more + ' non mostrate'))));
        group(s.title, s.total, kids);
      }
      const total = filterRows(rows, f).length;
      if (!total) box.append(h('div', { class: 'mc-none' }, h('p', null, T('No mission matches.', 'Nessuna missione corrisponde.')),
        h('button', { class: 'btn s', type: 'button', 'data-key': 'mc-clear', onclick: () => { f.q = ''; f.project = null; f.facet = 'all'; f.history = false; q.value = ''; remember(); draw(); q.focus(); } }, T('Clear filters', 'Azzera i filtri'))));
      live.textContent = total ? T(total + ' of ' + rows.length + ' missions', total + ' di ' + rows.length + ' missioni') : T('No mission matches', 'Nessuna missione corrisponde');
      translate(el);
      const cur = list.findIndex((x) => x.type === 'row' && x.row.id === current.id && !x.recent);
      setAct(f.q ? 0 : cur < 0 ? 0 : cur, !f.q);
    }
    const pickAt = () => { const s = list[act]; if (!s) return; if (s.type === 'row') choose(s.row.id); else box.querySelectorAll('[role=option]')[act]?.click(); };
    q.addEventListener('input', () => { f.q = q.value; for (const k of Object.keys(caps)) delete caps[k]; draw(); });
    q.addEventListener('keydown', (e) => {
      const k = e.key;
      if (k === 'ArrowDown') { e.preventDefault(); setAct(act + 1); }
      else if (k === 'ArrowUp') { e.preventDefault(); setAct(act - 1); }
      else if (k === 'PageDown') { e.preventDefault(); setAct(Math.min(list.length - 1, act + 8)); }
      else if (k === 'PageUp') { e.preventDefault(); setAct(Math.max(0, act - 8)); }
      else if (k === 'Enter') { e.preventDefault(); pickAt(); }
    });
    draw();
    return { el, focus: q };
  }
  return trigger;
}
