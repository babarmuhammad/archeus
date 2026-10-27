// V2 Live shell: toolbar (tool chrome), device frame, app shell, router, simulation loop.
import { h, clear } from './dom.js';
import { icon } from './icons.js';
import { lockup, wordmark } from './brand.js';
import { createSim, clockLabel } from '../sim.js';
import * as store from './store.js';
import { THEMES, DEVICES } from './store.js';
import { ROUTES, BOTTOM, simControls, controlBody } from './views.js';
import * as vNow from './view-now.js';
import * as vWork from './view-work.js';
import * as vAttention from './view-attention.js';
import * as vMap from './view-map.js';
import * as vReplay from './view-replay.js';
import * as vSettings from './view-settings.js';
import { viewMore } from './views2.js';
import { viewChat, mountDock } from './chat.js';
import { viewSecurity, viewHealth, viewUsage, viewAccounts, viewExtensions, decorate } from './areas.js';
import { inspectorFor } from './inspectors.js';
import { areasOf } from './areas-model.js';
import { translate } from './i18n.js';
import { viewTerminal } from './terminal.js';
import { pruneMaps, syncLive, notePulse } from './map.js';
import { installKeys } from './keys.js';

store.apply();
const q = new URLSearchParams(location.search);
// An embedded frame (the All devices view) shares the parent's simulation instance, so all devices show one story.
const embed = q.get('embed') === '1';
const shared = embed && window.parent !== window && window.parent.v2live && window.parent.v2live.sim;
const sim = shared || createSim({ seed: q.get('seed') ? Number(q.get('seed')) : undefined, story: q.get('story') || undefined });
if (embed) document.body.dataset.embed = '1';
if (!shared) {
  if (q.get('sim') !== 'paused') sim.play();
  if (q.get('speed')) sim.setSpeed(Number(q.get('speed')));
  if (q.get('advance')) sim.advance(Number(q.get('advance')) * 1000);
}

const ui = { tab: 'outcome', replaySel: null, draft: '', term: null };
const ctx = { sim, ui, route: { name: 'now', id: null }, mounts: [], nav, act, toast, render, closeInsp, setDevice, setLang, setNotes };

// ---------- shell ----------
const toolbar = document.getElementById('toolbar');
const stage = document.getElementById('stage');
const device = document.getElementById('device');
const framenote = document.getElementById('framenote');
let app, page, rail, bottom, dock, topbar, inspector, scrim, toastEl, menu = null, menuName = null, toastTimer = 0;

const navLabel = (r) => (r.id === 'now' ? 'Overview' : r.label);
const navItem = (r, cls) => h('a', { class: cls, href: '#/' + r.id, 'data-route': r.id, 'aria-label': cls === 'nav-item' ? null : navLabel(r) },
  icon(r.icon, cls === 'nav-item' ? 20 : 24), h('span', { class: cls === 'nav-item' ? 'nl' : '' }, navLabel(r)), cls === 'nav-item' || r.id === 'attention' ? h('span', { class: 'count', 'data-count': r.id, hidden: true }) : null);

function buildShell() {
  rail = h('nav', { class: 'rail', 'aria-label': 'Main' },
    h('div', { class: 'rail-head' }, h('button', { class: 'rail-toggle', type: 'button', 'aria-label': 'Expand or collapse the navigation', onclick: () => { app.dataset.rail = app.dataset.rail === 'open' ? '' : 'open'; } }, icon('menu')), h('span', { class: 'brand' }, wordmark())),
    ...ROUTES.flatMap((r) => [navItem(r, 'nav-item'), ['chat', 'extensions'].includes(r.id) ? h('div', { class: 'rail-sep' }) : null]),
    h('a', { class: 'nav-item', href: '#/terminal', 'data-route': 'terminal' }, icon('terminal', 20), h('span', { class: 'nl' }, 'Terminal view')),
    h('div', { class: 'rail-sep' }), h('p', { class: 'eyebrow rail-eye' }, 'Projects'), h('div', { class: 'rail-proj', id: 'railproj' }));
  topbar = h('header', { class: 'topbar' });
  page = h('main', { class: 'main-col', id: 'page', tabindex: '-1' });
  bottom = h('nav', { class: 'bottombar', 'aria-label': 'Main' }, ...BOTTOM.map((id) => navItem(ROUTES.find((r) => r.id === id), 'bb-item')), navItem({ id: 'more', label: 'More', icon: 'menu' }, 'bb-item'));
  dock = h('div', { class: 'chatdock', id: 'chatdock', hidden: true });
  inspector = h('aside', { class: 'inspector', 'aria-label': 'Details', id: 'inspector' });
  scrim = h('div', { class: 'scrim', 'aria-hidden': 'true', onclick: closeInsp });
  toastEl = h('div', { class: 'toast', role: 'status', hidden: true });
  app = h('div', { class: 'app', id: 'app', 'data-rail': '', 'data-insp': '' }, rail, h('div', { class: 'main-wrap' }, topbar, page), dock, bottom, scrim, inspector, toastEl);
  clear(device).append(app);
}

// ---------- routing ----------
// The one place that maps a route to the function that renders it: render(ctx) returns the page node.
const VIEWS = { now: vNow.render, work: vWork.render, attention: vAttention.render, map: vMap.render, replay: vReplay.render, chat: viewChat, settings: vSettings.render, security: viewSecurity, health: viewHealth, usage: viewUsage, accounts: viewAccounts, extensions: viewExtensions, more: viewMore };
function parse() {
  const m = /^#\/([a-z]+)(?:\/([\w-]+))?/.exec(location.hash) || [];
  const name = [...ROUTES.map((r) => r.id), 'terminal', 'more'].includes(m[1]) ? m[1] : 'now';
  return { name, id: m[2] || null };
}
function nav(hash) { if (location.hash === hash) render(); else location.hash = hash; }
function closeInsp() { nav('#/' + ctx.route.name); }

function render() {
  if (ctx.route.name === 'terminal' && parse().name === 'terminal' && ctx.termRoute && app.querySelector('.tui')) { ctx.route = parse(); ctx.termRoute(ctx.route); return; } // the terminal view redraws itself and keeps its state
  const keep = { top: page.scrollTop, itop: inspector.scrollTop, key: document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.key : null, was: document.activeElement };
  const prev = ctx.route;
  ctx.route = parse();
  if (prev.name !== ctx.route.name || prev.id !== ctx.route.id) { keep.top = 0; keep.itop = 0; if (prev.id !== ctx.route.id) ui.tab = 'outcome'; if (prev.name !== ctx.route.name) { ui.tellOpen = ui.safetyOpen = false; ui.confirm = null; ui.estopAsk = ui.rearmAsk = false; if (ctx.route.name !== 'work') ui.workProject = null; } }
  ctx.mounts = []; ctx.ticks = [];
  const r = ctx.route, term = r.name === 'terminal';
  app.dataset.term = term ? 'true' : 'false';
  document.title = 'V2 Live \u00b7 ' + (term ? 'Terminal' : r.name === 'more' ? 'More' : navLabel(ROUTES.find((x) => x.id === r.name)));

  let content;
  if (term) content = viewTerminal(ctx);
  else content = VIEWS[r.name](ctx);
  if (r.name === 'now') content.prepend(h('h1', { class: 'vh' }, 'Overview'));
  app.dataset.hero = ['now', 'map'].includes(r.name) ? '1' : '';
  if (!term) content = decorate(ctx, content);
  if (term) { clear(page); page.hidden = true; const old = app.querySelector('.term-wrap'); if (old) old.remove(); app.append(content); } else { page.hidden = false; const old = app.querySelector('.term-wrap'); if (old) old.remove(); clear(page).append(content); }

  // inspector
  let insp = null;
  if (!term && ['now', 'work', 'map', 'attention', 'security', 'health', 'usage', 'accounts', 'extensions'].includes(r.name) && r.id) insp = inspectorFor(ctx);
  clear(inspector); if (insp) inspector.append(insp);
  const wasOpen = app.dataset.insp === 'open';
  app.dataset.insp = insp ? 'open' : '';

  // navigation state and counts
  const inMore = ['more', 'map', 'replay', 'security', 'health', 'usage', 'accounts', 'extensions', 'settings'].includes(r.name);
  app.querySelectorAll('[data-route]').forEach((a) => { const here = a.dataset.route === r.name || (a.dataset.route === 'more' && inMore); if (here) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  const n = sim.attention().filter((a) => a.group === 'Decide' || a.group === 'Review').length;
  app.querySelectorAll('[data-count="attention"]').forEach((c) => { c.hidden = !n; c.textContent = String(n); c.setAttribute('aria-label', n + ' need you'); });

  mountTell(term);
  syncTopbar(); syncRail();
  ctx.mounts.forEach((f) => f());
  pruneMaps(['now', 'map'].includes(r.name) ? r.name : null);
  translate(app);
  syncCore(); if (!embed) syncToolbar();
  page.scrollTop = keep.top; inspector.scrollTop = keep.itop;
  if (keep.key) { const el = app.querySelector('[data-key="' + keep.key + '"]'); if (el && el !== document.activeElement) el.focus({ preventScroll: true }); }
  if (insp && !wasOpen) { const hd = inspector.querySelector('h2'); if (hd) { hd.setAttribute('tabindex', '-1'); hd.focus({ preventScroll: true }); } }
}

// ---------- the one allowed loop: the core breath on the map's core mark (ADR-0055), switched by syncLive ----------
function syncCore() { syncLive(sim); }
function patchLive() {
  const t = clockLabel(sim.state.clock);
  document.querySelectorAll('[data-live="clock"]').forEach((e) => { if (e.textContent !== t) e.textContent = t; });
  syncCore(); (ctx.ticks || []).forEach((f) => f());
}

// ---------- actions ----------
const SAY = { approve: 'Approved (simulated). Nothing was run.', reject: 'Rejected (simulated).', accept: 'Accepted (simulated).', changes: 'Changes requested (simulated).', unblock: 'Unblocked (simulated).', resume: 'Resumed (simulated).', replan: 'Replanning (simulated).', cancel: 'Cancelled (simulated).', pause: 'Pausing (simulated).', pause_all: 'Pausing every running mission (simulated).', resume_all: 'Resuming every paused mission (simulated).', estop: 'Emergency stop: every running mission stopped, new dispatch blocked until re-armed (simulated).', rearm: 'Re-armed: new work can start again (simulated).', confirm: 'Remembered (simulated).', retract: 'Not remembered (simulated).', enable: 'Enabled (simulated).' };
function act(kind, id) {
  let r = { ok: true }, msg = SAY[kind];
  if (kind === 'play-sim') { sim.play(); msg = 'Simulation running.'; } else if (kind === 'pause-sim') { sim.pause(); msg = 'Simulation paused.'; }
  else if (kind === 'speed') { sim.setSpeed(Number(id)); msg = 'Speed x' + id + '.'; }
  else if (kind === 'trigger-approval') { if (areasOf(sim).hookAllows('h-1')) { r = sim.triggerApproval(); msg = 'A running execution asked for a decision.'; } else { r = { ok: true }; msg = 'The hook "ask before git push" is switched off, so the execution did not ask.'; } }
  else if (kind === 'inject-failure') { r = sim.injectFailure('execution'); msg = 'An execution failed (injected).'; }
  else if (kind === 'inject-spawn') { r = sim.injectFailure('spawn'); msg = 'Spawn failures tripped the harness breaker (injected).'; }
  else if (kind === 'offline-toggle') { const A = areasOf(sim); r = A.isOffline() ? A.reconnect() : A.goOffline(); msg = A.isOffline() ? 'Offline: showing what this client kept.' : 'Reconnected.'; }
  else if (kind === 'reset') { sim.reset(); ui.replaySel = null; msg = 'Simulation reset.'; if (ctx.route.id) { nav('#/' + ctx.route.name); } }
  else if (kind === 'say') { r = sim.say(id); msg = null; }
  else r = sim.act(kind, id);
  if (!r.ok) toast('Not done: ' + r.reason); else if (msg) toast(msg, kind === 'estop' ? { action: { label: 'Open Settings', href: '#/settings' } } : null);
  if (kind === 'approve' || kind === 'reject' || kind === 'plan_changes') { if (ctx.route.name === 'attention' && ctx.route.id) closeInsp(); }
  render(); if (!embed) refreshMenu();
  return r;
}
// Info toasts leave after 4.5 s. An error, or a toast that carries an action, stays until Dismiss.
function toast(text, o) {
  const err = !!(o && o.error) || /^(Not done|Non fatto)/.test(text), keep = err || !!(o && o.action);
  clearTimeout(toastTimer); clear(toastEl);
  toastEl.dataset.kind = err ? 'error' : 'info'; toastEl.setAttribute('role', err ? 'alert' : 'status');
  toastEl.append(h('span', { class: 'tt' }, text), ...(o && o.action ? [h('a', { class: 'btn', href: o.action.href, onclick: dismissToast }, o.action.label)] : []), h('button', { class: 'btn quiet', type: 'button', 'data-key': 'toast-x', onclick: dismissToast }, 'Dismiss'));
  translate(toastEl); toastEl.hidden = false;
  if (!keep) toastTimer = setTimeout(dismissToast, 4500);
}
function dismissToast() { clearTimeout(toastTimer); toastEl.hidden = true; }

// ---------- top bar: safety cluster (status popover, Tell, Stop) ----------
const isPhone = () => app.clientWidth < 600;
function closeSafety() { if (ui.safetyOpen) { ui.safetyOpen = false; ui.estopAsk = ui.rearmAsk = false; render(); } }
function stopClick() { ui.safetyOpen = true; ui.tellOpen = false; if (sim.state.estop.engaged) ui.rearmAsk = true; else ui.estopAsk = true; render(); const k = app.querySelector('[data-key="' + (sim.state.estop.engaged ? 'rearm-yes' : 'estop-yes') + '"]'); if (k) k.focus(); }
function tellClick() {
  if (ctx.route.name === 'chat') { const i = page.querySelector('input.cinput'); if (i) i.focus(); return; }
  ui.tellOpen = !ui.tellOpen; ui.safetyOpen = false; render();
  if (ui.tellOpen) { const i = dock.querySelector('input.cinput'); if (i) i.focus(); }
}
function syncTopbar() {
  const eng = sim.state.estop.engaged, open = !!ui.safetyOpen;
  clear(topbar).append(
    h('span', { class: 'tb-lock' }, lockup()),
    h('div', { class: 'safety', 'data-state': eng ? 'stopped' : 'ok' },
      h('button', { class: 'safety-btn', type: 'button', 'data-key': 'safety', 'aria-haspopup': 'true', 'aria-expanded': open ? 'true' : 'false', onclick: () => { if (open) closeSafety(); else { ui.safetyOpen = true; ui.tellOpen = false; render(); } } },
        h('span', { class: 'sdot', 'aria-hidden': 'true' }), h('span', { class: 'stext' }, eng ? 'Stopped' : 'Not stopped'), h('span', { class: 'sep', 'aria-hidden': 'true' }, '·'), h('span', { class: 'sx' }, eng ? 'new work blocked' : 'accepts new work')),
      open ? h('div', { class: 'safety-pop', role: 'group', 'aria-label': 'Pause, resume and emergency stop' }, controlBody(ctx, true)) : null),
    h('button', { class: 'btn tell-btn', type: 'button', 'data-key': 'tell', 'aria-expanded': ui.tellOpen ? 'true' : 'false', onclick: tellClick }, 'Tell'),
    h('button', { class: 'btn danger stop-btn', type: 'button', 'data-key': 'stop', onclick: stopClick }, eng ? 'Re-arm' : 'Stop'));
}
// The composer is an overlay on desktop, not an always-on dock; the phone keeps its tell bar until the phone slice replaces it.
function mountTell(term) {
  if (term) { app.dataset.dock = ''; dock.hidden = true; return; }
  const phone = isPhone(), open = !phone && ui.tellOpen && ctx.route.name !== 'chat';
  dock.classList.toggle('tell', !phone);
  mountDock(phone ? ctx : Object.assign({}, ctx, { route: { name: open ? 'now' : 'none' } }), dock, app);
  if (!phone) {
    app.dataset.dock = '';
    if (open) dock.append(h('button', { class: 'btn quiet tell-x', type: 'button', 'aria-label': 'Close', onclick: () => { ui.tellOpen = false; render(); const b = app.querySelector('[data-key="tell"]'); if (b) b.focus(); } }, icon('close', 18)));
  }
}

// ---------- sidebar: PROJECTS with a state dot ----------
const PSTATE = { needs_you: 'decision waiting', running: 'work running', done: 'all verified', idle: 'nothing running' };
function projState(p) {
  const ms = Object.values(sim.state.missions).filter((m) => m.project === p.id);
  if (sim.attention().some((a) => a.project_id === p.id && (a.group === 'Decide' || a.group === 'Review'))) return 'needs_you';
  if (ms.some((m) => m.state === 'EXECUTING')) return 'running';
  return ms.length && ms.every((m) => m.state === 'COMPLETED') ? 'done' : 'idle';
}
function syncRail() {
  const box = rail.querySelector('#railproj');
  clear(box).append(...sim.state.projects.map((p) => { const st = projState(p), here = ctx.route.name === 'work' && ui.workProject === p.id;
    return h('a', { class: 'proj-item', href: '#/work', 'data-proj': p.id, 'aria-current': here ? 'page' : null, onclick: (e) => { e.preventDefault(); ui.workProject = p.id; nav('#/work'); } },
      h('span', { class: 'pdot', 'data-s': st, 'aria-hidden': 'true' }), h('span', { class: 'nl' }, p.name), h('span', { class: 'vh' }, PSTATE[st])); }));
}

// ---------- toolbar and menus ----------
function buildToolbar() {
  clear(toolbar);
  const open = store.get('tools') === 'open';
  toolbar.dataset.open = open ? '1' : '0';
  const tools = h('button', { class: 'tb-btn', type: 'button', 'data-tb': 'tools', 'aria-label': 'Prototype tools', 'aria-expanded': open ? 'true' : 'false', onclick: toggleTools }, icon('settings'), h('span', { class: 'tb-label' }, 'Tools'));
  toolbar.append(
    h('span', { class: 'sim-badge', role: 'note' }, h('span', { class: 'g', 'aria-hidden': 'true' }, '◆'), 'SIMULATED', h('span', { class: 'long' }, 'no Core connected')),
    h('span', { class: 'tb-spacer' }), tools,
    h('div', { class: 'tb-tray', hidden: !open }, tbBtn('device', 'Device', 'Device preview'), tbBtn('theme', 'Theme', 'Theme'), tbBtn('motion', 'Motion', 'Reduced motion'), tbBtn('lang', 'EN', 'Language'), tbBtn('sim', 'Sim', 'Simulation'), tbBtn('notes', 'Notes', 'Decision notes on the Overview and Map')));
  translate(toolbar);
}
function toggleTools() { closeMenu(); store.set('tools', store.get('tools') === 'open' ? 'closed' : 'open'); buildToolbar(); syncToolbar(); const b = toolbar.querySelector('[data-tb="tools"]'); if (b) b.focus(); fit(); }
function tbBtn(id, label, aria) {
  const b = h('button', { class: 'tb-btn', type: 'button', 'data-tb': id, 'aria-label': aria, onclick: () => (id === 'motion' ? toggleMotion() : id === 'notes' ? setHeroNotes() : id === 'lang' ? setLang(store.get('lang') === 'it' ? 'en' : 'it') : toggleMenu(id, b)) }, icon(id === 'sim' ? 'sim' : id === 'lang' ? 'lang' : id === 'notes' ? 'note' : id), h('span', { class: id === 'lang' ? 'tb-label tb-always' : 'tb-label' }, label));
  if (id === 'lang' || id === 'motion' || id === 'notes') b.classList.add('tb-opt');
  if (id !== 'motion' && id !== 'lang' && id !== 'notes') { b.setAttribute('aria-haspopup', 'true'); b.setAttribute('aria-expanded', 'false'); }
  return b;
}
function syncToolbar() {
  const tb = (id) => toolbar.querySelector('[data-tb="' + id + '"]');
  const dev = DEVICES.find((d) => d.id === store.get('device')), th = THEMES.find((t) => t.id === store.get('theme'));
  tb('device').querySelector('.tb-label').textContent = dev.label; tb('theme').querySelector('.tb-label').textContent = th.label.replace(', high contrast', ' HC').replace(' (simulated)', '');
  const red = store.reducedMotion(); const m = tb('motion'); m.setAttribute('aria-pressed', red ? 'true' : 'false'); m.querySelector('.tb-label').textContent = red ? 'Quiet' : 'Motion';
  tb('notes').setAttribute('aria-pressed', store.get('heronotes') === 'on' ? 'true' : 'false');
  tb('lang').querySelector('.tb-label').textContent = store.get('lang') === 'it' ? 'IT' : 'EN'; tb('lang').setAttribute('aria-pressed', store.get('lang') === 'it' ? 'true' : 'false');
  const sb = tb('sim'); sb.querySelector('.tb-label').textContent = sim.state.playing ? 'x' + sim.state.speed : 'Paused';
  translate(toolbar);
}
function setLang(id) { store.set('lang', id); buildToolbar(); syncToolbar(); render(); refreshMenu(); broadcast(); }
function setHeroNotes() { store.set('heronotes', store.get('heronotes') === 'on' ? 'off' : 'on'); syncToolbar(); broadcast(); }
function setNotes(id) { store.set('notes', id); refreshMenu(); render(); broadcast(); }
function toggleMotion() { store.set('motion', store.reducedMotion() ? 'full' : 'reduced'); syncCore(); syncToolbar(); toast(store.reducedMotion() ? 'Reduced motion on: the core mark is still.' : 'Motion on: the core mark breathes while work is live.'); render(); refreshMenu(); broadcast(); }
function closeMenu() { if (menu) { menu.remove(); menu = null; } toolbar.querySelectorAll('[aria-expanded="true"]').forEach((b) => b.setAttribute('aria-expanded', 'false')); menuName = null; }
function toggleMenu(name, btn) { if (menuName === name) { closeMenu(); return; } closeMenu(); menuName = name; btn.setAttribute('aria-expanded', 'true'); buildMenu(); }
function refreshMenu() { if (menuName) buildMenu(); }
function buildMenu() {
  if (menu) menu.remove();
  const item = (label, checked, on, hint, dev) => h('button', { class: 'menu-item', type: 'button', 'data-device': dev, role: 'menuitemradio', 'aria-checked': checked ? 'true' : 'false', onclick: on }, h('span', { class: 'tick', 'aria-hidden': 'true' }, checked ? '✓' : ''), label, hint ? h('span', { class: 'hint' }, hint) : null);
  let kids;
  if (menuName === 'device') kids = [h('h2', null, 'Device preview'), ...DEVICES.map((d) => item(d.label, store.get('device') === d.id, () => { setDevice(d.id); closeMenu(); }, d.note, d.id)),
    h('p', { class: 'menu-note' }, 'A frame shows the real app at that width inside this page. If the window is narrower, the frame is scaled down to fit.')];
  else if (menuName === 'theme') kids = [h('h2', null, 'Theme'), ...THEMES.map((t) => item(t.label, store.get('theme') === t.id, () => { store.set('theme', t.id); syncToolbar(); refreshMenu(); render(); })),
    h('div', { class: 'menu-sep' }),
    h('button', { class: 'menu-item', type: 'button', role: 'menuitemcheckbox', 'aria-checked': store.reducedMotion() ? 'true' : 'false', onclick: toggleMotion }, h('span', { class: 'tick', 'aria-hidden': 'true' }, store.reducedMotion() ? '\u2713' : ''), 'Reduced motion', h('span', { class: 'hint' }, 'Quiet')),
    h('button', { class: 'menu-item', type: 'button', role: 'menuitemcheckbox', 'aria-checked': store.get('lang') === 'it' ? 'true' : 'false', onclick: () => setLang(store.get('lang') === 'it' ? 'en' : 'it') }, h('span', { class: 'tick', 'aria-hidden': 'true' }, store.get('lang') === 'it' ? '\u2713' : ''), 'Language', h('span', { class: 'hint' }, 'Italiano')),
    h('button', { class: 'menu-item', type: 'button', role: 'menuitemcheckbox', 'aria-checked': store.get('notes') === 'on' ? 'true' : 'false', onclick: () => setNotes(store.get('notes') === 'on' ? 'off' : 'on') }, h('span', { class: 'tick', 'aria-hidden': 'true' }, store.get('notes') === 'on' ? '\u2713' : ''), 'Decision notes', h('span', { class: 'hint' }, store.get('notes') === 'on' ? 'On' : 'Off')),
    h('p', { class: 'menu-note' }, 'System follows the OS (including high contrast). Forced colours is a simulation; the real forced-colors mode is also honoured.')];
  else kids = [h('h2', null, 'Simulation'), simControls(Object.assign({}, ctx, { where: 'menu' }))];
  menu = h('div', { class: 'menu', role: 'menu', 'aria-label': menuName }, ...kids);
  translate(menu);
  document.body.append(menu);
  menu.style.top = toolbar.offsetHeight + 2 + 'px';
}
document.addEventListener('click', (e) => { if (ui.safetyOpen && !e.target.closest('.safety, .safety-pop, .stop-btn')) closeSafety(); if (menu && !menu.contains(e.target) && !toolbar.contains(e.target)) closeMenu(); });
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (menu) { const n = menuName; closeMenu(); const b = toolbar.querySelector('[data-tb="' + n + '"]'); if (b) b.focus(); } else if (ui.safetyOpen) { closeSafety(); const b = app.querySelector('[data-key="safety"]'); if (b) b.focus(); } else if (ui.estopAsk || ui.rearmAsk) { ui.estopAsk = ui.rearmAsk = false; render(); } else if (ui.tellOpen) { ui.tellOpen = false; render(); const b = app.querySelector('[data-key="tell"]'); if (b) b.focus(); } else if (app.dataset.insp === 'open') closeInsp();
});

// ---------- device frames ----------
function setDevice(id) {
  const was = store.get('device');
  if (was === 'all' && id !== 'all') leaveAll();
  store.set('device', id);
  if (id === 'terminal') ctx.nav('#/terminal'); else if (was === 'terminal' && ctx.route.name === 'terminal') nav('#/now');
  fit(); syncToolbar();
}
const FRAME_H = { phone: 844, tablet: 1180 };
function fit() {
  const d = DEVICES.find((x) => x.id === store.get('device'));
  if (d && d.id === 'all') { fitAll(); return; }
  if (stage.dataset.frame === 'all') leaveAll();
  if (!d || !d.w) { delete stage.dataset.frame; device.removeAttribute('style'); framenote.hidden = true; return; }
  stage.dataset.frame = d.id;
  framenote.hidden = false;
  const availW = stage.clientWidth - 24, availH = stage.clientHeight - 16;
  const k = Math.min(1, availW / d.w);
  const hgt = Math.min(FRAME_H[d.id] || 1e9, availH / k);
  device.style.width = d.w + 'px'; device.style.height = hgt + 'px'; device.style.top = '8px';
  device.style.transform = 'translateX(-50%) scale(' + k + ')';
  framenote.textContent = d.label + ' frame, ' + d.w + ' px wide, shown at ' + Math.round(k * 100) + '%' + (k < 1 ? '. Scaled down to fit this window, so controls look smaller than they are.' : '.');
  render();
}

// ---------- boot ----------
if (!embed) buildToolbar();
buildShell();
ctx.openHelp = installKeys(ctx, app, page).openHelp;
const unsub = sim.subscribe((e) => {
  if (e.type === 'clock' || e.type === 'execution.progress' || e.type === 'usage.observed') { if (e.type === 'execution.progress') notePulse(sim, e); patchLive(); if (ctx.redrawTerm && ctx.route.name === 'terminal') ctx.redrawTerm(); return; }
  if (e.type === 'sim.play' || e.type === 'sim.pause' || e.type === 'sim.speed') { syncCore(); if (!embed) syncToolbar(); return; }
  notePulse(sim, e);
  clearTimeout(boot.t); boot.t = setTimeout(() => { render(); if (!embed) refreshMenu(); }, 120);
});
const boot = { t: 0 };
window.addEventListener('pagehide', unsub);
window.addEventListener('hashchange', () => { closeMenu(); render(); });
window.addEventListener('resize', () => { if (store.get('device') === 'all' || (store.get('device') !== 'auto' && store.get('device') !== 'terminal')) fit(); else if (ctx.redrawTerm && ctx.route.name === 'terminal') ctx.redrawTerm(); else document.dispatchEvent(new Event('v2live:resize')); });
document.addEventListener('visibilitychange', syncCore);
if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => { if (ctx.route.name !== 'terminal') ctx.mounts.forEach((f) => f()); }).observe(device);
let last = performance.now();
if (!embed) setInterval(() => { const n = performance.now(); if (!document.hidden) sim.tickReal(n - last); last = n; }, 250);
if (store.get('device') === 'terminal' && !location.hash) location.hash = '#/terminal';
window.v2live = { sim, ui, store, setPrefs, areas: areasOf(sim), help: () => ctx.openHelp(), toast };

// ---------- the All devices view: phone, tablet, desktop and terminal at once, one shared simulation ----------
const ALL = [{ id: 'phone', label: 'Phone', w: 390, h: 844, hash: '#/now' }, { id: 'tablet', label: 'Tablet', w: 820, h: 1100, hash: '#/work' }, { id: 'desktop', label: 'Desktop', w: 1440, h: 900, hash: '#/now' }, { id: 'terminal', label: 'Terminal', w: 640, h: 800, hash: '#/terminal' }];
let allView = null;
function prefsQuery() { return 'embed=1&sim=paused&theme=' + store.get('theme') + '&lang=' + store.get('lang') + '&notes=' + store.get('notes') + '&motion=' + store.get('motion'); }
function fitAll() {
  stage.dataset.frame = 'all'; framenote.hidden = false;
  if (!allView) { allView = h('div', { class: 'allview', id: 'allview' }); stage.append(allView); }
  const availW = stage.clientWidth - 24, availH = stage.clientHeight - 24, gap = 16, cap = 34;
  const layouts = [[['phone', 'tablet', 'desktop', 'terminal']], [['phone', 'desktop'], ['tablet', 'terminal']], [['phone', 'tablet', 'terminal'], ['desktop']]];
  let best = null;
  layouts.forEach((rows) => {
    const widest = Math.max(...rows.map((r) => r.reduce((a, id) => a + ALL.find((d) => d.id === id).w, 0)));
    const gapW = Math.max(...rows.map((r) => gap * (r.length - 1)));
    const tall = rows.reduce((a, r) => a + Math.max(...r.map((id) => ALL.find((d) => d.id === id).h)), 0);
    const fixedH = rows.length * (cap + gap);
    const k = Math.max(0.05, Math.min(1, (availW - gapW) / widest, (availH - fixedH) / tall));
    if (!best || k > best.k) best = { k, rows };
  });
  const sig = JSON.stringify(best.rows);
  if (allView.dataset.sig !== sig) { // moving an iframe reloads it, so panes are only re-parented when the arrangement changes
    allView.dataset.sig = sig; clear(allView);
    best.rows.forEach((r) => { const row = h('div', { class: 'allrow' }); r.forEach((id) => row.append(paneFor(ALL.find((d) => d.id === id)))); allView.append(row); });
  }
  ALL.forEach((d) => { const f = paneCache[d.id]; const box = f.querySelector('.pane-box'); box.style.width = Math.round(d.w * best.k) + 'px'; box.style.height = Math.round(d.h * best.k) + 'px'; f.querySelector('iframe').style.transform = 'scale(' + best.k + ')'; });
  framenote.textContent = 'All devices: one simulation drives every pane. Shown at ' + Math.round(best.k * 100) + '%; each pane is laid out at its own real width.' + (best.k < 1 ? ' Controls look smaller than they are.' : '');
  translate(framenote);
}
const paneCache = {};
function paneFor(d) {
  return paneCache[d.id] || (paneCache[d.id] = h('figure', { class: 'pane', 'data-pane': d.id }, h('figcaption', null, d.label + ' · ' + d.w + ' px'), h('div', { class: 'pane-box' }, h('iframe', { title: d.label + ' preview', src: 'index.html?' + prefsQuery() + d.hash, width: d.w, height: d.h }))));
}
function leaveAll() {
  if (allView) { allView.remove(); allView = null; }
  Object.keys(paneCache).forEach((k) => delete paneCache[k]);
  delete stage.dataset.frame;
}
function broadcast() {
  document.querySelectorAll('iframe').forEach((f) => { try { f.contentWindow.v2live.setPrefs({ theme: store.get('theme'), lang: store.get('lang'), notes: store.get('notes'), motion: store.get('motion') }); } catch (e) { /* frame not ready */ } });
}
function setPrefs(o) { Object.keys(o).forEach((k) => { if (store.get(k) !== o[k]) store.set(k, o[k]); }); render(); }

// first draw, last: fit() reads the All devices declarations above, which a stored 'all' device would hit too early
if (embed) render(); else { fit(); if (store.get('device') === 'auto' || store.get('device') === 'terminal') render(); }
