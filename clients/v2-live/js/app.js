// V2 Live shell: toolbar (tool chrome), device frame, app shell, router, simulation loop.
import { h, clear } from './dom.js';
import { icon } from './icons.js';
import { createSim, clockLabel } from '../sim.js';
import * as store from './store.js';
import { THEMES, DEVICES } from './store.js';
import { ROUTES, BOTTOM, viewNow, viewWork, viewAttention, viewMap, viewSettings, viewAccounts, inspectorMission, inspectorApproval, simControls } from './views.js';
import { viewSecurity, viewHealth, viewMore } from './views2.js';
import { viewChat, mountDock } from './chat.js';
import { viewReplay } from './replay.js';
import { translate } from './i18n.js';
import { viewTerminal } from './terminal.js';

store.apply();
const q = new URLSearchParams(location.search);
// An embedded frame (the All devices view) shares the parent's simulation instance, so all devices show one story.
const embed = q.get('embed') === '1';
const shared = embed && window.parent !== window && window.parent.v2live && window.parent.v2live.sim;
const sim = shared || createSim({ seed: q.get('seed') ? Number(q.get('seed')) : undefined });
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
let app, page, rail, bottom, dock, inspector, scrim, toastEl, menu = null, menuName = null, toastTimer = 0;

const navItem = (r, cls) => h('a', { class: cls, href: '#/' + r.id, 'data-route': r.id, 'aria-label': cls === 'nav-item' ? null : r.label },
  icon(r.icon, cls === 'nav-item' ? 22 : 24), h('span', { class: cls === 'nav-item' ? 'nl' : '' }, r.label), cls === 'nav-item' || r.id === 'attention' ? h('span', { class: 'count', 'data-count': r.id, hidden: true }) : null);

function buildShell() {
  rail = h('nav', { class: 'rail', 'aria-label': 'Main' },
    h('div', { class: 'rail-head' }, h('button', { class: 'rail-toggle', type: 'button', 'aria-label': 'Expand or collapse the navigation', onclick: () => { app.dataset.rail = app.dataset.rail === 'open' ? '' : 'open'; } }, icon('menu')), h('span', { class: 'brand' }, 'archeus')),
    ...ROUTES.map((r) => navItem(r, 'nav-item')), h('div', { class: 'rail-sep' }),
    h('a', { class: 'nav-item', href: '#/terminal', 'data-route': 'terminal' }, icon('terminal', 22), h('span', { class: 'nl' }, 'Terminal view')),
    h('p', { class: 'rail-foot' }, 'V2 Live prototype. Simulated. No Core is connected.'));
  page = h('main', { class: 'main-col', id: 'page', tabindex: '-1' });
  bottom = h('nav', { class: 'bottombar', 'aria-label': 'Main' }, ...BOTTOM.map((id) => navItem(ROUTES.find((r) => r.id === id), 'bb-item')), navItem({ id: 'more', label: 'More', icon: 'menu' }, 'bb-item'));
  dock = h('div', { class: 'chatdock', id: 'chatdock', hidden: true });
  inspector = h('aside', { class: 'inspector', 'aria-label': 'Details', id: 'inspector' });
  scrim = h('div', { class: 'scrim', 'aria-hidden': 'true', onclick: closeInsp });
  toastEl = h('div', { class: 'toast', role: 'status', hidden: true });
  app = h('div', { class: 'app', id: 'app', 'data-rail': '', 'data-insp': '' }, rail, page, dock, bottom, scrim, inspector, toastEl);
  clear(device).append(app);
}

// ---------- routing ----------
function parse() {
  const m = /^#\/([a-z]+)(?:\/([\w-]+))?/.exec(location.hash) || [];
  const name = [...ROUTES.map((r) => r.id), 'terminal', 'more'].includes(m[1]) ? m[1] : 'now';
  return { name, id: m[2] || null };
}
function nav(hash) { if (location.hash === hash) render(); else location.hash = hash; }
function closeInsp() { nav('#/' + ctx.route.name); }

function render() {
  const keep = { top: page.scrollTop, itop: inspector.scrollTop, key: document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.key : null, was: document.activeElement };
  const prev = ctx.route;
  ctx.route = parse();
  if (prev.name !== ctx.route.name || prev.id !== ctx.route.id) { keep.top = 0; keep.itop = 0; if (prev.id !== ctx.route.id) ui.tab = 'outcome'; }
  ctx.mounts = [];
  const r = ctx.route, term = r.name === 'terminal';
  app.dataset.term = term ? 'true' : 'false';
  document.title = 'V2 Live \u00b7 ' + (term ? 'Terminal' : r.name === 'more' ? 'More' : ROUTES.find((x) => x.id === r.name).label);

  let content;
  if (term) content = viewTerminal(ctx);
  else content = ({ now: viewNow, work: viewWork, attention: viewAttention, map: viewMap, replay: viewReplay, chat: viewChat, settings: viewSettings, security: viewSecurity, health: viewHealth, accounts: viewAccounts, more: viewMore })[r.name](ctx);
  if (r.name === 'now') content.prepend(headNow());
  if (term) { clear(page); page.hidden = true; const old = app.querySelector('.term-wrap'); if (old) old.remove(); app.append(content); } else { page.hidden = false; const old = app.querySelector('.term-wrap'); if (old) old.remove(); clear(page).append(content); }

  // inspector
  let insp = null;
  if (!term && ['now', 'work', 'map', 'attention'].includes(r.name) && r.id) {
    const ap = sim.state.approvals[r.id], m = sim.state.missions[r.id];
    if (ap) insp = inspectorApproval(ctx, ap); else if (m) insp = inspectorMission(ctx, m);
  }
  clear(inspector); if (insp) inspector.append(insp);
  const wasOpen = app.dataset.insp === 'open';
  app.dataset.insp = insp ? 'open' : '';

  // navigation state and counts
  const inMore = ['more', 'map', 'replay', 'security', 'health', 'accounts', 'settings'].includes(r.name);
  app.querySelectorAll('[data-route]').forEach((a) => { const here = a.dataset.route === r.name || (a.dataset.route === 'more' && inMore); if (here) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  const n = sim.attention().filter((a) => a.group === 'Decide' || a.group === 'Review').length;
  app.querySelectorAll('[data-count="attention"]').forEach((c) => { c.hidden = !n; c.textContent = String(n); c.setAttribute('aria-label', n + ' need you'); });

  if (term) { app.dataset.dock = ''; dock.hidden = true; } else mountDock(ctx, dock, app);
  ctx.mounts.forEach((f) => f());
  translate(app);
  syncCore(); if (!embed) syncToolbar();
  page.scrollTop = keep.top; inspector.scrollTop = keep.itop;
  if (keep.key) { const el = app.querySelector('[data-key="' + keep.key + '"]'); if (el && el !== document.activeElement) el.focus({ preventScroll: true }); }
  if (insp && !wasOpen) { const hd = inspector.querySelector('h2'); if (hd) { hd.setAttribute('tabindex', '-1'); hd.focus({ preventScroll: true }); } }
}

function headNow() {
  const st = sim.state;
  return h('header', { class: 'page-head', style: 'padding:0' }, h('div', null, h('h1', null, 'Now'),
    h('p', { class: 'sub' }, h('span', { class: 'sim-tag' }, 'SIMULATED'), ' Fixture data, nothing is connected to a Core. Simulated time ', h('span', { 'data-live': 'clock' }, clockLabel(st.clock)), st.playing ? ' (running, x' + st.speed + ')' : ' (paused)')));
}

// ---------- the one allowed loop: the core breath (ADR-0055) ----------
function syncCore() {
  const live = sim.liveWork().length;
  const breathe = live > 0 && !store.reducedMotion() && !document.hidden;
  document.querySelectorAll('.core').forEach((c) => { c.dataset.core = breathe ? 'breath' : live ? 'still' : 'idle'; c.dataset.live = live ? 'true' : 'false'; const t = c.querySelector('.core-txt'); if (t) t.textContent = live + ' running'; });
}
function patchLive() {
  const t = clockLabel(sim.state.clock);
  document.querySelectorAll('[data-live="clock"]').forEach((e) => { if (e.textContent !== t) e.textContent = t; });
  syncCore();
}

// ---------- actions ----------
const SAY = { approve: 'Approved (simulated). Nothing was run.', reject: 'Rejected (simulated).', accept: 'Accepted (simulated).', changes: 'Changes requested (simulated).', unblock: 'Unblocked (simulated).', resume: 'Resumed (simulated).', replan: 'Replanning (simulated).', cancel: 'Cancelled (simulated).', pause: 'Pausing (simulated).', confirm: 'Remembered (simulated).', retract: 'Not remembered (simulated).', enable: 'Enabled (simulated).' };
function act(kind, id) {
  let r = { ok: true }, msg = SAY[kind];
  if (kind === 'play-sim') { sim.play(); msg = 'Simulation running.'; } else if (kind === 'pause-sim') { sim.pause(); msg = 'Simulation paused.'; }
  else if (kind === 'speed') { sim.setSpeed(Number(id)); msg = 'Speed x' + id + '.'; }
  else if (kind === 'trigger-approval') { r = sim.triggerApproval(); msg = 'A running execution asked for a decision.'; }
  else if (kind === 'inject-failure') { r = sim.injectFailure('execution'); msg = 'An execution failed (injected).'; }
  else if (kind === 'inject-spawn') { r = sim.injectFailure('spawn'); msg = 'Spawn failures tripped the harness breaker (injected).'; }
  else if (kind === 'reset') { sim.reset(); ui.replaySel = null; msg = 'Simulation reset.'; if (ctx.route.id) { nav('#/' + ctx.route.name); } }
  else if (kind === 'say') { r = sim.say(id); msg = null; }
  else if (kind === 'card') { const [mid, what] = id.split('|'); r = sim.cardAction(mid, what); msg = what === 'confirm' ? 'Confirmed (simulated).' : 'Dismissed.'; }
  else r = sim.act(kind, id);
  if (!r.ok) toast('Not done: ' + r.reason); else if (msg) toast(msg);
  if (kind === 'approve' || kind === 'reject') { if (ctx.route.name === 'attention' && ctx.route.id) closeInsp(); }
  render(); if (!embed) refreshMenu();
  return r;
}
function toast(text) {
  toastEl.textContent = text; translate(toastEl); toastEl.hidden = false; clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.hidden = true; }, 4500);
}

// ---------- toolbar and menus ----------
function buildToolbar() {
  clear(toolbar);
  toolbar.append(
    h('span', { class: 'tb-brand' }, 'V2 Live'),
    h('span', { class: 'sim-badge', role: 'note' }, h('span', { class: 'g', 'aria-hidden': 'true' }, '◆'), 'SIMULATED', h('span', { class: 'long' }, 'no Core connected')),
    h('span', { class: 'tb-spacer' }),
    tbBtn('device', 'Device', 'Device preview'), tbBtn('theme', 'Theme', 'Theme'), tbBtn('motion', 'Motion', 'Reduced motion'), tbBtn('lang', 'EN', 'Language'), tbBtn('sim', 'Sim', 'Simulation'));
  translate(toolbar);
}
function tbBtn(id, label, aria) {
  const b = h('button', { class: 'tb-btn', type: 'button', 'data-tb': id, 'aria-label': aria, onclick: () => (id === 'motion' ? toggleMotion() : id === 'lang' ? setLang(store.get('lang') === 'it' ? 'en' : 'it') : toggleMenu(id, b)) }, icon(id === 'sim' ? 'sim' : id === 'lang' ? 'lang' : id), h('span', { class: id === 'lang' ? 'tb-label tb-always' : 'tb-label' }, label));
  if (id === 'lang' || id === 'motion') b.classList.add('tb-opt');
  if (id !== 'motion' && id !== 'lang') { b.setAttribute('aria-haspopup', 'true'); b.setAttribute('aria-expanded', 'false'); }
  return b;
}
function syncToolbar() {
  const tb = (id) => toolbar.querySelector('[data-tb="' + id + '"]');
  const dev = DEVICES.find((d) => d.id === store.get('device')), th = THEMES.find((t) => t.id === store.get('theme'));
  tb('device').querySelector('.tb-label').textContent = dev.label; tb('theme').querySelector('.tb-label').textContent = th.label.replace(', high contrast', ' HC').replace(' (simulated)', '');
  const red = store.reducedMotion(); const m = tb('motion'); m.setAttribute('aria-pressed', red ? 'true' : 'false'); m.querySelector('.tb-label').textContent = red ? 'Quiet' : 'Motion';
  tb('lang').querySelector('.tb-label').textContent = store.get('lang') === 'it' ? 'IT' : 'EN'; tb('lang').setAttribute('aria-pressed', store.get('lang') === 'it' ? 'true' : 'false');
  const sb = tb('sim'); sb.querySelector('.tb-label').textContent = sim.state.playing ? 'x' + sim.state.speed : 'Paused';
  translate(toolbar);
}
function setLang(id) { store.set('lang', id); buildToolbar(); syncToolbar(); render(); refreshMenu(); broadcast(); }
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
}
document.addEventListener('click', (e) => { if (menu && !menu.contains(e.target) && !toolbar.contains(e.target)) closeMenu(); });
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (menu) { const n = menuName; closeMenu(); const b = toolbar.querySelector('[data-tb="' + n + '"]'); if (b) b.focus(); } else if (app.dataset.insp === 'open') closeInsp();
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
const unsub = sim.subscribe((e) => {
  if (e.type === 'clock' || e.type === 'execution.progress' || e.type === 'usage.observed') { patchLive(); if (ctx.redrawTerm && ctx.route.name === 'terminal') ctx.redrawTerm(); return; }
  if (e.type === 'sim.play' || e.type === 'sim.pause' || e.type === 'sim.speed') { if (!embed) syncToolbar(); return; }
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
window.v2live = { sim, ui, store, setPrefs };
if (embed) render(); else { fit(); if (store.get('device') === 'auto' || store.get('device') === 'terminal') render(); }

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
