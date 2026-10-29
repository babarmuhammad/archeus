// Autopilot (AP01 to AP12): a guided tour that drives the real UI with real DOM events, one feature after another, under a caption bar.
// The chapters are data (autopilot-script.js). This file is the only code that touches the page: it finds a target, moves the cursor ring to it, fires the events a person's
// pointer or keyboard would, and waits. Any trusted click or key outside the bar stops the tour; whatever the tour changed is put back (restoreAll).
import { h, s, clear } from './dom.js';
import { icon } from './icons.js';
import { tr } from './i18n.js';
import * as store from './store.js';
import { isPhone } from './viewport.js';
import { CHAPTERS, GROUPS } from './autopilot-script.js';

const KEY = 'v2live.autopilot'; // sessionStorage: the tour survives the page reload a project count needs
const SPEEDS = [0.5, 1, 2];
const WAIT = 2500; // how long a step looks for its target before it is skipped
const PREFS = ['theme', 'motion', 'notes', 'heronotes', 'overview', 'slashpins', 'slashrecent', 'projsort'];
const MODIFIERS = ['Shift', 'Control', 'Alt', 'Meta', 'Tab'];

const lang = () => (store.get('lang') === 'it' ? 1 : 0);
const pick = (pair) => pair[lang()];
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const visible = (el) => !!el && el.isConnected && el.checkVisibility({ checkVisibilityCSS: true }) && el.getBoundingClientRect().width > 0 && !el.closest('.apbar, .ap-list');
const sel = (t) => (/^[[.#]|[\s>,:]/.test(t) ? t : t.endsWith('*') ? '[data-key^="' + t.slice(0, -1) + '"]' : '[data-key="' + t + '"]');
const all = (t) => [...document.querySelectorAll(sel(t))].filter(visible);

export function installAutopilot(ctx, { setPrefs }) {
  const { sim } = ctx;
  let run = null, bar = null, list = null, ring = null, cursor = null, hovered = null, onInput = null;

  // ---------- state that survives a reload ----------
  const flush = () => { if (run.ct) { run.times[CHAPTERS[run.i].id].ms += performance.now() - run.ct; run.ct = performance.now(); } };
  const save = (extra) => { flush(); try { sessionStorage.setItem(KEY, JSON.stringify({ i: run.i, st: run.st, speed: run.speed, base: run.base, times: run.times, log: run.log.slice(-600), ...extra })); } catch { /* private window: the tour still runs, it just cannot survive a reload */ } };
  const load = () => { try { return JSON.parse(sessionStorage.getItem(KEY)); } catch { return null; } };
  const clearSaved = () => { try { sessionStorage.removeItem(KEY); } catch { /* nothing stored */ } };
  const urlWith = (search) => location.pathname + search + location.hash;
  const marked = (search, on) => { const p = new URLSearchParams(search); p.delete('autopilot'); if (on) p.set('autopilot', 'resume'); const s = p.toString(); return s ? '?' + s : ''; };

  // ---------- finding and pointing ----------
  const find = (t, nth = 0) => all(t)[nth] || null;
  const target = async (s) => { const el = await until(() => find(s.target, s.nth || 0)); return el; };
  async function until(fn, ms = WAIT) {
    const end = performance.now() + ms;
    for (;;) { const v = fn(); if (v) return v; if (run.token.dead || performance.now() > end) return null; await wait(50); }
  }
  // A pause in tour time: shortened by the speed, frozen while paused, cut short by skip or stop.
  async function nap(ms) {
    let left = ms / run.speed;
    while (left > 0 && !run.token.dead) { const t0 = performance.now(); await wait(Math.min(left, 50)); if (!run.paused) left -= performance.now() - t0; }
  }
  const hold = async () => { while (run.paused && !run.token.dead) await wait(80); };

  function point(el) {
    el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    const r = el.getBoundingClientRect();
    ring.style.cssText = 'left:' + (r.left - 4) + 'px;top:' + (r.top - 4) + 'px;width:' + (r.width + 8) + 'px;height:' + (r.height + 8) + 'px';
    ring.hidden = false; cursor.hidden = false;
    cursor.style.transform = 'translate(' + (r.left + r.width / 2) + 'px,' + (r.top + r.height / 2) + 'px)';
    return { clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 };
  }
  const fire = (el, type, init, C = PointerEvent) => el.dispatchEvent(new C(type, { bubbles: true, cancelable: true, composed: true, view: window, ...init }));
  const mouse = (p, extra) => ({ ...p, button: 0, buttons: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true, ...extra });

  async function tap(el) {
    const p = point(el); await nap(store.reducedMotion() ? 0 : 420);
    const m = mouse(p), svg = !!el.closest('svg'); // a map keeps pointer capture on pointerdown, which a pointer that was never real cannot take: click events only there
    fire(el, 'pointerover', m); fire(el, 'pointerenter', { ...m, bubbles: false });
    if (!svg) { fire(el, 'pointerdown', mouse(p, { buttons: 1 })); fire(el, 'mousedown', mouse(p, { buttons: 1 }), MouseEvent); el.focus({ preventScroll: true }); fire(el, 'pointerup', m); fire(el, 'mouseup', m, MouseEvent); }
    fire(el, 'click', { ...m, detail: 1 }, MouseEvent);
  }
  function leave() {
    if (!hovered) return;
    const m = mouse({ clientX: 0, clientY: 0 });
    if (hovered.isConnected) { fire(hovered, 'pointerout', m); fire(hovered, 'pointerleave', { ...m, bubbles: false }); }
    hovered = null;
  }
  async function over(el) {
    leave();
    const p = point(el); await nap(store.reducedMotion() ? 0 : 420);
    const m = mouse(p);
    fire(el, 'pointerover', m); fire(el, 'pointerenter', { ...m, bubbles: false }); fire(el, 'pointermove', m); fire(el, 'mouseover', m, MouseEvent); fire(el, 'mousemove', m, MouseEvent);
    hovered = el;
  }
  const typed = (el, text) => { const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set; set.call(el, text); el.dispatchEvent(new InputEvent('input', { bubbles: true, data: text.slice(-1), inputType: 'insertText' })); };
  async function type(el, text) {
    await tap(el);
    for (const c of text) { fire(el, 'keydown', { key: c }, KeyboardEvent); typed(el, el.value + c); fire(el, 'keyup', { key: c }, KeyboardEvent); await nap(store.reducedMotion() ? 10 : 55); if (run.token.dead) return; }
  }
  function press(spec, el) {
    const parts = spec.split('+'), key = parts.pop(), to = el || document.activeElement || document.body;
    const init = { key, ctrlKey: parts.includes('ctrl'), shiftKey: parts.includes('shift'), altKey: parts.includes('alt'), metaKey: parts.includes('meta') };
    fire(to, 'keydown', init, KeyboardEvent); fire(to, 'keyup', init, KeyboardEvent);
  }

  // ---------- the prototype tools (Tools tray on a desktop window, the Prototype tools sheet where the toolbar is folded) ----------
  const toolsOpen = () => !!document.querySelector('.menu, .tools');
  async function closeMenus() { for (let k = 0; k < 4 && document.querySelector('.menu, .sheet-wrap, .safety-pop, .helpscrim'); k++) { press('Escape', document); await wait(120); } }
  async function openTool(name) {
    await closeMenus();
    const folded = find('tools');
    if (folded) { await tap(folded); const row = await until(() => find('tools-' + name)); if (row) await tap(row); return !!row; }
    if (!find('[data-tb="' + name + '"]')) { const t = find('[data-tb="tools"]'); if (t) await tap(t); }
    const b = await until(() => find('[data-tb="' + name + '"]'));
    if (b) await tap(b);
    return !!b;
  }

  // ---------- one step ----------
  const here = (s) => !s.on || (s.on === 'phone') === isPhone();
  // a chapter keyed on: is judged by the shape the tour started in (a chapter may switch the device itself)
  const inTour = (ch) => !ch.on || (ch.on === 'phone') === run.base.phone;
  const nextIn = (i, d) => { while (CHAPTERS[i] && !inTour(CHAPTERS[i])) i += d; return i; };
  const inTourIdx = () => CHAPTERS.map((c, i) => i).filter((i) => inTour(CHAPTERS[i]));
  async function exec(s) {
    if (!here(s)) return 'off';
    if (s.do === 'wait') { await nap(s.ms); return 'ok'; }
    if (s.do === 'nav') {
      const m = /^#\/(\w+)$/.exec(s.arg), link = m && find('.rail [data-route="' + m[1] + '"]');
      if (link && location.hash !== s.arg) await tap(link); else ctx.nav(s.arg);
      return 'ok';
    }
    if (s.do === 'unhover') { leave(); return 'ok'; }
    if (s.do === 'press') { const el = s.target === 'document' ? document : s.target ? await target(s) : null; if (s.target && s.target !== 'document' && !el) return 'miss'; press(s.arg, el); return 'ok'; }
    if (s.do === 'reload') {
      const b = run.base, p = new URLSearchParams(b.search);
      if (s.arg !== 'baseline') { p.delete('projects'); Object.entries(s.arg).forEach(([k, v]) => p.set(k, v)); }
      run.st += 1; save(); location.assign(urlWith(marked(p.toString() ? '?' + p : '', true)));
      return 'ok';
    }
    // a menu item that rebuilds its menu closes it (the page's own outside click rule), so every such step opens the menu again if it has to
    if (s.tool && (!toolsOpen() || run.menu !== s.tool)) { if (!(await openTool(s.tool))) return 'miss'; run.menu = s.tool; }
    const el = await target(s);
    if (!el) return 'miss';
    if (el.closest('[inert]')) return 'miss';
    if (s.tool === 'projects') { run.st += 1; save(); history.replaceState(null, '', urlWith(marked(location.search, true))); } // the page reloads with the new count
    if (s.do === 'click') await tap(el);
    else if (s.do === 'hover') await over(el);
    else if (s.do === 'type') await type(el, s.arg);
    else if (s.do === 'clear') typed(el, '');
    else if (s.do === 'select') { el.value = s.arg; fire(el, 'change', {}, Event); }
    if (s.tool && !toolsOpen()) run.menu = null;
    return 'ok';
  }

  // ---------- chapters ----------
  async function prepare() {
    await closeMenus(); leave(); run.menu = null; ring.hidden = cursor.hidden = true;
    const ch = CHAPTERS[run.i], want = (ch.env && ch.env.device) || run.base.device;
    restoreSettings();
    if (store.get('device') !== want && !(want === 'phone' && isPhone())) { ctx.setDevice(want); await wait(400); }
  }
  async function doChapter(ch) {
    const tok = run.token; run.ct = performance.now();
    if (run.st === 0) await prepare();
    for (let k = run.st; k < ch.steps.length && !tok.dead; k++) {
      await hold(); if (tok.dead) break;
      run.st = k; const s = ch.steps[k];
      const r = await exec(s);
      if (tok.dead) break;
      const skipped = r === 'miss';
      run.log.push({ ch: ch.id, k, do: s.do, target: s.target || s.arg || '', r: skipped && s.optional ? 'optional' : r });
      if (skipped && !s.optional) { run.note = tr('Skipped a step: nothing to point at on this screen.'); drawBar(); run.times[ch.id].skipped += 1; }
      await nap(r === 'off' || skipped ? 100 : (s.ms ?? 600));
    }
    run.st = 0; flush(); run.ct = 0;
    ring.hidden = true; leave();
  }
  async function loop() {
    while (run && !run.stopped && run.i < CHAPTERS.length) {
      const ch = CHAPTERS[run.i];
      run.token = { dead: false, go: null }; run.times[ch.id] = run.times[ch.id] || { ms: 0, skipped: 0 }; run.note = '';
      drawBar(); save();
      await doChapter(ch);
      if (!run || run.stopped) return;
      run.i = nextIn(run.token.go != null ? run.token.go : run.i + 1, 1);
    }
    if (run && !run.stopped) end('finished');
  }
  const go = (i) => {
    if (!run || run.stopped) return;
    i = nextIn(i, i < run.i ? -1 : 1);
    if (i < 0) return;
    if (i >= CHAPTERS.length) { end('finished'); return; }
    run.token.go = i; run.token.dead = true; if (run.shown) { run.i = i; drawBar(); }
  };

  // ---------- settings: what the tour changed goes back ----------
  const snapshot = () => ({ ...Object.fromEntries(['lang', 'device', 'tools', ...PREFS].map((k) => [k, store.get(k)])), playing: sim.state.playing, speed: sim.state.speed, estop: sim.state.estop.engaged,
    offline: window.v2live.areas.isOffline(), search: marked(location.search, false), phone: isPhone() });
  const worldDiffers = () => { const a = new URLSearchParams(location.search), b = new URLSearchParams(run.base.search); return ['projects', 'story', 'seed'].some((k) => a.get(k) !== b.get(k)); };
  function restoreSettings() {
    const b = run.base, same = (k) => JSON.stringify(store.get(k)) === JSON.stringify(b[k]);
    if (!same('lang')) ctx.setLang(b.lang);
    const diff = Object.fromEntries(PREFS.filter((k) => !same(k)).map((k) => [k, b[k]])); if (Object.keys(diff).length) setPrefs(diff);
    if (sim.state.playing !== b.playing) (b.playing ? sim.play() : sim.pause());
    if (sim.state.speed !== b.speed) sim.setSpeed(b.speed);
    if (sim.state.estop.engaged && !b.estop) sim.act('rearm');
    if (window.v2live.areas.isOffline() && !b.offline) window.v2live.areas.reconnect();
  }
  // the story starts over: the tour added missions, ideas, failures and an offline spell, and the exact earlier moment of a run is not kept
  function restoreAll(why) {
    sim.reset(); ctx.ui.replaySel = null;
    restoreSettings();
    if (store.get('device') !== run.base.device) ctx.setDevice(run.base.device);
    const tray = document.querySelector('[data-tb="tools"]');
    if (store.get('tools') !== run.base.tools && tray && visible(tray)) tray.click();
    if (worldDiffers()) { save({ phase: 'done', why }); location.assign(urlWith(marked(run.base.search, true))); return true; }
    return false;
  }

  // ---------- stopping ----------
  const SAID = { finished: 'Autopilot finished. Your settings are back as they were.', input: 'Autopilot stopped because you used the app. Your settings are back as they were.', button: 'Autopilot stopped. Your settings are back as they were.' };
  function end(why) {
    if (!run || run.stopped) return;
    run.stopped = true; run.token.dead = true; api.last = { why, times: run.times, log: run.log };
    document.removeEventListener('pointerdown', onInput, true); document.removeEventListener('keydown', onInput, true);
    leave(); closeMenus().then(() => {
      const reloading = restoreAll(why);
      teardown();
      if (!reloading) { clearSaved(); ctx.toast(SAID[why]); }
    });
  }
  // bar, ring and cursor stay referenced: a step still unwinding may touch them
  function teardown() { [bar, list, ring, cursor].forEach((e) => e && e.remove()); list = null; delete document.body.dataset.ap; window.dispatchEvent(new Event('resize')); }
  // A trusted event is a person: the tour never fires one. Tab and the modifier keys only move focus, so a keyboard user can still reach the bar.
  onInput = (e) => {
    if (!run || run.stopped || run.shown || !e.isTrusted) return;
    const inBar = !!(e.target.closest && e.target.closest('.apbar, .ap-list'));
    if (e.type === 'keydown') { if (e.key === 'Escape') end('input'); else if (!inBar && !MODIFIERS.includes(e.key)) end('input'); } else if (!inBar) end('input');
  };

  // ---------- the caption bar ----------
  const btn = (key, label, ic, fn) => h('button', { class: 'btn ap-btn', type: 'button', 'data-key': key, 'aria-label': label, title: label, onclick: fn }, icon(ic, 18), h('span', { class: 'ap-bl' }, label));
  function buildBar() {
    ring = h('div', { class: 'ap-ring', hidden: true, 'aria-hidden': 'true' });
    cursor = h('div', { class: 'ap-cursor', hidden: true, 'aria-hidden': 'true' }, s('svg', { width: 20, height: 20, viewBox: '0 0 20 20' }, s('path', { d: 'M3 2l12 7-5.2 1.4L7.6 16z' })));
    bar = h('section', { class: 'apbar', role: 'region', 'aria-label': 'Autopilot' },
      h('div', { class: 'ap-text' }, h('p', { class: 'ap-eye' }), h('h2', { class: 'ap-title' }), h('p', { class: 'ap-cap', 'aria-live': 'polite' }), h('p', { class: 'ap-note' })),
      h('div', { class: 'ap-ctl', role: 'group', 'aria-label': 'Autopilot controls' },
        btn('ap-prev', 'Previous chapter', 'back', () => go(run.i - 1)), btn('ap-pause', 'Pause', 'pause', () => { run.paused = !run.paused; drawBar(); }),
        btn('ap-next', 'Next chapter', 'forward', () => go(run.i + 1)), btn('ap-speed', 'Speed', 'clock', () => { run.speed = SPEEDS[(SPEEDS.indexOf(run.speed) + 1) % SPEEDS.length]; drawBar(); }),
        btn('ap-chapters', 'Chapters', 'menu', toggleList), btn('ap-stop', 'Stop', 'close', () => end('button'))),
      h('div', { class: 'ap-prog', role: 'progressbar', 'aria-valuemin': 0 }, h('i')));
    document.body.append(ring, cursor);
    document.body.insertBefore(bar, document.getElementById('stage'));
    document.body.dataset.ap = '';
    window.dispatchEvent(new Event('resize'));
  }
  function drawBar() {
    if (!bar) return;
    const ch = CHAPTERS[run.i], ids = inTourIdx(), n = ids.length, at = ids.indexOf(run.i) + 1;
    bar.querySelector('.ap-eye').textContent = tr('Autopilot') + ' · ' + pick(GROUPS[ch.group]) + ' · ' + tr('Chapter ' + at + ' of ' + n);
    bar.querySelector('.ap-title').textContent = pick(ch.t);
    bar.querySelector('.ap-cap').textContent = pick(ch.c);
    const note = bar.querySelector('.ap-note'); note.textContent = run.note || ''; note.hidden = !run.note;
    const label = (key, text) => { const b = bar.querySelector('[data-key="' + key + '"]'); b.setAttribute('aria-label', tr(text)); b.title = tr(text); b.querySelector('.ap-bl').textContent = tr(text); return b; };
    label('ap-prev', 'Previous chapter').disabled = at <= 1; label('ap-next', 'Next chapter'); label('ap-chapters', 'Chapters').setAttribute('aria-expanded', String(!!list)); label('ap-stop', 'Stop');
    const p = label('ap-pause', run.paused ? 'Resume' : 'Pause'); p.setAttribute('aria-pressed', String(run.paused)); p.replaceChildren(icon(run.paused ? 'resume' : 'pause', 18), h('span', { class: 'ap-bl' }, tr(run.paused ? 'Resume' : 'Pause')));
    const sp = label('ap-speed', 'Speed'); sp.querySelector('.ap-bl').replaceChildren(h('span', { class: 'ap-w' }, tr('Speed') + ' '), run.speed + 'x');
    const prog = bar.querySelector('.ap-prog'); prog.setAttribute('aria-valuemax', n); prog.setAttribute('aria-valuenow', at); prog.setAttribute('aria-label', tr('Chapter ' + at + ' of ' + n)); prog.firstChild.style.width = (at / n * 100) + '%';
    if (list) drawList();
  }
  function toggleList() {
    if (list) { list.remove(); list = null; } else { list = h('div', { class: 'ap-list', role: 'dialog', 'aria-label': 'Chapters' }); document.body.append(list); drawList(); }
    drawBar();
  }
  function drawList() {
    clear(list); let g = '';
    CHAPTERS.forEach((ch, i) => {
      if (!inTour(ch)) return;
      if (ch.group !== g) { g = ch.group; list.append(h('p', { class: 'ap-gh' }, pick(GROUPS[g]))); }
      list.append(h('button', { class: 'ap-row', type: 'button', 'data-key': 'ap-ch-' + ch.id, 'aria-current': i === run.i ? 'step' : null, onclick: () => { toggleList(); go(i); } }, h('span', { class: 'ap-n' }, String(inTourIdx().indexOf(i) + 1)), pick(ch.t)));
    });
  }

  // ---------- entry points ----------
  function open(o, from) {
    run = { i: o.chapter || from.i, st: from.st, speed: o.speed || from.speed || 1, paused: !!o.show, token: { dead: false, go: null }, base: from.base || snapshot(), times: from.times || {}, log: from.log || [], note: '', menu: null, shown: !!o.show, stopped: false };
    buildBar(); drawBar();
    document.addEventListener('pointerdown', onInput, true); document.addEventListener('keydown', onInput, true);
    if (!o.show) loop();
  }
  const api = {
    start(o = {}) { if (!run || run.stopped) open(o, { i: 0, st: 0 }); },
    // The paused bar on chapter 1 without driving anything: what the layout probe measures.
    show() { if (!run || run.stopped) open({ show: true }, { i: 0, st: 0 }); },
    hide() { if (run && !run.stopped) { run.stopped = true; run.token.dead = true; document.removeEventListener('pointerdown', onInput, true); document.removeEventListener('keydown', onInput, true); teardown(); } },
    stop: () => end('button'),
    active: () => !!run && !run.stopped,
    chapter: () => (run && !run.stopped ? run.i : -1),
    last: null // how the last tour ended, with its per-chapter times and step log (what the check tool reads)
  };

  // ?autopilot=1 starts the tour on load; ?autopilot=resume continues one a reload interrupted (or says how it ended).
  const q = new URLSearchParams(location.search), mode = q.get('autopilot');
  if (mode) {
    const saved = load(); history.replaceState(null, '', urlWith(marked(location.search, false)));
    if (mode === '1') requestAnimationFrame(() => api.start());
    else if (saved && saved.phase) { clearSaved(); requestAnimationFrame(() => ctx.toast(SAID[saved.why])); api.last = { why: saved.why, times: saved.times, log: saved.log }; }
    else if (saved) requestAnimationFrame(() => open({}, saved));
  }
  return api;
}
