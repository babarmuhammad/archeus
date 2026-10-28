// The command palette (Ctrl+K or Cmd+K, or the Search button in the top bar): pages, actions and projects in one list.
// Arrow keys move, Enter runs, Esc closes and gives focus back. The terminal view keeps Ctrl+K for the shell.
import { h, clear } from './dom.js';
import { icon } from './icons.js';
import { translate, tr } from './i18n.js';
import * as store from './store.js';
import { ROUTES } from './views.js';
import { search, sections, remember } from './palette-model.js';

export function installPalette(ctx, app, { projHint }) {
  let root = null, from = null, active = 0, flat = [];
  const items = () => {
    const nav = (hash) => () => ctx.nav(hash), act = (kind) => () => ctx.act(kind), lang = store.get('lang') === 'it' ? 'en' : 'it';
    const page = (id, label, hash, pin) => ({ id: 'p-' + id, group: 'Pages', label, pin, run: nav(hash) });
    const action = (id, label, words, run, o) => Object.assign({ id: 'a-' + id, group: 'Actions', label, words, run }, o);
    return [
      ...ROUTES.map((r) => page(r.id, r.id === 'now' ? 'Overview' : r.label, '#/' + r.id, r.id === 'now' || r.id === 'work')),
      page('terminal', 'Terminal view', '#/terminal'), page('projects', 'Projects', '#/projects'),
      action('stop', 'Stop all', 'emergency halt end every mission', ctx.stop, { pin: true }),
      action('pause', 'Pause all', 'hold wait running missions', act('pause_all')), action('resume', 'Resume all', 'continue paused missions', act('resume_all')),
      action('tell', 'Tell Archeus', 'say ask chat message', ctx.tell, { pin: true }),
      action('safety', 'Settings: Safety', 'open pause resume emergency stop', nav('#/settings/safety')),
      action('appearance', 'Settings: Appearance', 'open theme motion language notes', nav('#/settings/appearance')),
      action('prototype', 'Settings: Prototype', 'open device simulation controls', nav('#/settings/prototype')),
      action('lang', lang === 'it' ? 'Language: Italiano' : 'Language: English', 'switch italian english lingua', () => ctx.setLang(lang)),
      action('keys', 'Keyboard shortcuts', 'help keys ?', () => ctx.openHelp()),
      ...ctx.sim.state.projects.map((p) => ({ id: 'j-' + p.id, group: 'Projects', label: p.name, words: 'project', hint: projHint(p), run: () => { ctx.ui.workProject = p.id; ctx.nav('#/work'); } }))
    ].map((i) => Object.assign(i, { words: (i.words || '') + ' ' + i.label, label: tr(i.label) })); // a label is searched in the language shown and in English
  };
  let all = [];
  const recent = () => ctx.ui.palRecent || [];

  function close() {
    if (!root) return;
    root.remove(); root = null;
    if (from && from.isConnected) from.focus({ preventScroll: true });
    from = null;
  }
  function run(item) {
    ctx.ui.palRecent = remember(recent(), item.id);
    close();
    item.run();
  }
  function paint(input, list) {
    const shown = search(all, input.value, recent()), secs = sections(shown, input.value, recent());
    flat = secs.flatMap(([, rows]) => rows);
    active = Math.min(active, Math.max(0, flat.length - 1));
    clear(list);
    let n = 0;
    secs.forEach(([name, rows]) => list.append(h('div', { class: 'pal-grp', role: 'group', 'aria-label': name }, h('div', { class: 'pal-gh', 'aria-hidden': 'true' }, name),
      ...rows.map((item) => { const i = n++; return h('div', { class: 'pal-row', role: 'option', id: 'pal-o' + i, 'data-i': i, 'aria-selected': i === active ? 'true' : 'false', onclick: () => run(item), onpointermove: () => { if (active !== i) { active = i; mark(input, list); } } },
        h('span', { class: 'pal-l' }, item.label), item.hint ? h('span', { class: 'pal-r' }, item.hint) : null); }))));
    if (!flat.length) list.append(h('p', { class: 'pal-none' }, 'Nothing matches. Try a page, an action or a project name.'));
    input.setAttribute('aria-activedescendant', flat.length ? 'pal-o' + active : '');
    translate(list);
  }
  function mark(input, list) {
    list.querySelectorAll('.pal-row').forEach((r) => r.setAttribute('aria-selected', Number(r.dataset.i) === active ? 'true' : 'false'));
    input.setAttribute('aria-activedescendant', flat.length ? 'pal-o' + active : '');
    const cur = list.querySelector('#pal-o' + active); if (cur) cur.scrollIntoView({ block: 'nearest' });
  }
  function open() {
    if (root || app.querySelector('.helpscrim')) return;
    from = document.activeElement; all = items(); active = 0;
    const input = h('input', { class: 'pal-q', type: 'text', role: 'combobox', 'aria-expanded': 'true', 'aria-controls': 'pal-list', 'aria-autocomplete': 'list', 'aria-label': 'Search pages, actions and projects', placeholder: 'Search or run a command', autocomplete: 'off', spellcheck: 'false', 'data-key': 'pal-q' });
    const list = h('div', { class: 'pal-list', id: 'pal-list', role: 'listbox', 'aria-label': 'Results' });
    input.addEventListener('input', () => { active = 0; paint(input, list); });
    input.addEventListener('keydown', (e) => {
      const last = flat.length - 1, to = { ArrowDown: active >= last ? 0 : active + 1, ArrowUp: active <= 0 ? Math.max(0, last) : active - 1, Home: 0, End: Math.max(0, last) }[e.key];
      if (to != null) { e.preventDefault(); active = to; mark(input, list); } else if (e.key === 'Enter') { e.preventDefault(); if (flat[active]) run(flat[active]); } else if (e.key === 'Tab') e.preventDefault();
    });
    root = h('div', { class: 'pal-scrim', onclick: (e) => { if (e.target === root) close(); } },
      h('section', { class: 'pal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Command palette' },
        h('div', { class: 'pal-in' }, icon('search', 18), input, h('kbd', { class: 'pal-esc', 'aria-hidden': 'true' }, 'Esc')), list,
        h('p', { class: 'pal-foot', 'aria-hidden': 'true' }, h('kbd', null, '↑'), h('kbd', null, '↓'), ' move ', h('kbd', null, 'Enter'), ' run ', h('kbd', null, 'Esc'), ' close')));
    app.append(root); paint(input, list); translate(root); input.focus();
  }
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k' && ctx.route.name !== 'terminal') { e.preventDefault(); e.stopImmediatePropagation(); if (root) close(); else open(); return; }
    if (root && e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close(); }
  }, true);
  return { open, close, isOpen: () => !!root };
}
