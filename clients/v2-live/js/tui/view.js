// The terminal view: a window frame, a character grid drawn from the controller's frame, a key bar for touch, a linear mode for
// screen readers. Everything it shows comes from the controller; it only draws and passes keys and clicks back.
import { h, clear } from '../dom.js';
import { createTui, LOOKS } from './controller.js';
import { BOX_MASK, speech } from './cells.js';
import * as store from '../store.js';

const PREFS = 'archeus-v2-live-tui';
const readPrefs = () => { try { return JSON.parse(localStorage.getItem(PREFS)) || {}; } catch (e) { return {}; } };
const writePrefs = (p) => { try { localStorage.setItem(PREFS, JSON.stringify(p)); } catch (e) { /* blocked storage: the look is not remembered */ } };

const KEYNAME = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Enter: 'enter', Escape: 'esc', Backspace: 'backspace', PageUp: 'pageup', PageDown: 'pagedown', Home: 'home', End: 'end' };
export function keyName(e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return null;
  if (e.key === 'Tab') return e.shiftKey ? 'shift-tab' : 'tab';
  return KEYNAME[e.key] || (e.key.length === 1 ? e.key : null);
}

// a segment becomes runs of plain text, one element per glyph (so every glyph is exactly one cell wide in any font),
// and drawn cells for the box lines and the meter blocks (crisp at any size)
function addSeg(parent, [text, cls, hit]) {
  const c = (cls || '').split(' ').filter(Boolean).map((x) => 'c-' + x).join(' ');
  const mk = (tag, klass, t) => { const e = document.createElement('span'); e.className = (klass + ' ' + c).trim(); if (hit) e.dataset.h = hit; if (t != null) e.textContent = t; return e; };
  let run = '';
  const flush = () => { if (run) { parent.append(mk('span', '', run)); run = ''; } };
  for (const ch of text) {
    const code = ch.charCodeAt(0);
    if (code >= 32 && code < 127) { run += ch; continue; }
    flush();
    const m = BOX_MASK[ch];
    if (m) { const e = mk('span', 'bx' + (m & 1 ? ' bl' : '') + (m & 2 ? ' br' : '') + (m & 4 ? ' bu' : '') + (m & 8 ? ' bd' : '')); parent.append(e); }
    else if (ch === '█' || ch === '░') parent.append(mk('span', ch === '█' ? 'bk' : 'bk lo'));
    else parent.append(mk('span', ch === '✕' ? 'g gx' : 'g', ch));
  }
  flush();
}
const sigOf = (l) => (l.rule ? 'R' : '') + (l.h ? 'H' : '') + (l.ov ? 'O' : '') + l.s.map((x) => x[0] + '\u0001' + x[1] + '\u0001' + (x[2] || '')).join('\u0002');

export function viewTerminal(ctx) {
  const sim = ctx.sim;
  const saved = readPrefs(), q = new URLSearchParams(location.search);
  const t = ctx.ui.tui || (ctx.ui.tui = {});
  if (!t.ctl) {
    t.ctl = createTui(sim, {
      lang: () => store.get('lang'), reduced: () => store.reducedMotion(),
      prefs: { look: LOOKS.some((x) => x.id === (q.get('look') || saved.look)) ? (q.get('look') || saved.look) : 'app', ascii: q.get('ascii') ? q.get('ascii') === '1' : !!saved.ascii, linear: q.get('sr') ? q.get('sr') === '1' : !!saved.linear },
      onQuit: () => ctx.nav('#/now'), onSetting: ([k, v]) => store.set(k, k === 'theme' && v === 'contrast' ? (store.get('theme').startsWith('light') ? 'light-hc' : 'dark-hc') : v), onPrefs: (p) => writePrefs({ look: p.look, ascii: p.ascii, linear: p.linear })
    });
  }
  const ctl = t.ctl;
  ctl.route(ctx.route.id);

  const grid = h('pre', { class: 'tui-grid', tabindex: '0', role: 'region', 'aria-label': 'Terminal view of the simulated state. Press ? for the keys.', 'data-key': 'term' });
  const lin = h('div', { class: 'tui-lin', role: 'document', 'aria-label': 'Terminal view as linear text', tabindex: '0', hidden: true });
  const stage = h('div', { class: 'tui-stage' }, grid, lin);
  const probe = h('span', { class: 'tui-probe', 'aria-hidden': 'true' }, '0'.repeat(100));
  const live = h('div', { class: 'vh', role: 'status', 'aria-live': 'polite' });
  const btn = (label, aria, on, extra) => h('button', { class: 'tui-btn', type: 'button', 'aria-label': aria || label, onclick: on }, label, extra || null);
  const press = (k) => { ctl.key(k); draw(); };
  const lookBtn = btn('Colours', 'Colours: cycle the look', () => press('L'));
  const asciiBtn = btn('ASCII', 'ASCII glyphs only', () => press('G'));
  const readBtn = btn('Read', 'Linear text for a screen reader', () => press('T'));
  const title = h('div', { class: 'tui-title' }, h('span', { class: 'tui-name' }, 'archeus ', h('b', null, 'terminal view')), h('span', { class: 'sp' }),
    lookBtn, asciiBtn, readBtn, btn('Keys', 'Keys and help', () => press('?')), h('a', { class: 'tui-btn act', href: '#/now', 'aria-label': 'Back to the app', 'data-key': 'tui-exit' }, 'App'));
  const keys = h('div', { class: 'tui-keys', role: 'group', 'aria-label': 'Terminal keys' });
  const input = h('input', { type: 'text', class: 'tui-input', 'aria-label': 'Command line: a place, a slash command, or a message to Archeus', autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false', placeholder: 'Go to, or /status, /help ...' });
  const cmd = h('form', { class: 'tui-cmd', hidden: true }, h('label', { class: 'tui-prompt', for: 'tui-input' }, ':'), input, h('button', { class: 'tui-btn', type: 'submit' }, 'Run'), h('button', { class: 'tui-btn', type: 'button', onclick: () => { press('esc'); grid.focus(); } }, 'Esc'));
  input.id = 'tui-input';
  const wrap = h('div', { class: 'term-wrap tui', 'data-look': 'app', 'data-ascii': 'false', 'data-sr': 'false' }, title, stage, keys, cmd, live, probe);

  const geo = { cols: 80, rows: 30, ratio: 0.6 };
  let prev = [], keySig = '', escAt = 0, frame = null;

  function measure() {
    const r = probe.getBoundingClientRect().width / 100 / 100 || 0.6;
    geo.ratio = r;
    const cs = getComputedStyle(stage), padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight), padY = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
    const w = stage.clientWidth - padX, hh = stage.clientHeight - padY;
    if (w < 50 || hh < 50) return false;
    const cw14 = Math.max(6, Math.round(14 * r)), cols = Math.max(40, Math.min(200, Math.floor(w / cw14)));
    const cw = Math.max(5, Math.floor(w / cols)), fs = cw / r, lh = Math.round(fs * 1.32);
    geo.cols = Math.floor(w / cw); geo.rows = Math.max(12, Math.floor(hh / lh));
    if (geo.cols > 200) geo.cols = 200;
    wrap.style.setProperty('--cw', cw + 'px'); wrap.style.setProperty('--fs', fs.toFixed(2) + 'px'); wrap.style.setProperty('--lh', lh + 'px');
    grid.style.width = geo.cols * cw + 'px'; grid.style.height = geo.rows * lh + 'px';
    return true;
  }

  function paintGrid(f) {
    const rows = f.lines;
    while (grid.childNodes.length > rows.length) grid.removeChild(grid.lastChild);
    rows.forEach((l, i) => {
      const sig = sigOf(l);
      if (prev[i] === sig && grid.childNodes[i]) return;
      prev[i] = sig;
      const d = document.createElement('div'); d.className = 'r' + (l.rule ? ' rule' : '') + (l.h ? ' hd' : '') + (l.ov ? ' ov' : '');
      if (!l.rule) l.s.forEach((sg) => addSeg(d, sg));
      if (grid.childNodes[i]) grid.replaceChild(d, grid.childNodes[i]); else grid.append(d);
    });
    prev.length = rows.length;
  }
  function paintLinear(f) {
    const big = ctl.frame({ cols: 60, rows: 400 });
    clear(lin);
    let list = null;
    big.lines.forEach((l) => {
      if (l.rule || l.deco) return;
      const text = speech(l.s).replace(/[─│┌┐└┘├┤┬┴┼]/g, ' ').replace(/^[›>]\s*/, '').replace(/\s+/g, ' ').trim();
      if (!text) { list = null; return; }
      const sel = l.s.some((x) => /\bsel\b/.test(x[1]));
      if (l.h) { list = null; lin.append(h('h2', null, text)); return; }
      if (!list) { list = h('ul', { class: 'tui-list' }); lin.append(list); }
      list.append(h('li', { 'aria-current': sel ? 'true' : null }, text));
    });
    return big;
  }

  function keybar(f) {
    const acts = ctl.actions(ctl.selected());
    const sig = acts.map((a) => a.key + a.label).join('|') + f.mode;
    if (sig === keySig) return; keySig = sig; clear(keys);
    const kb = (label, aria, k, cls) => h('button', { class: 'tui-btn k' + (cls ? ' ' + cls : ''), type: 'button', 'aria-label': aria, 'data-k': k, onclick: () => { press(k); if (ctl.state.mode && ctl.state.mode.kind === 'cmd') input.focus(); else grid.focus({ preventScroll: true }); } }, label);
    keys.append(kb('↑', 'Up', 'up'), kb('↓', 'Down', 'down'), kb('⏎', 'Enter, open', 'enter'), kb('Esc', 'Escape, back', 'esc'), kb('Tab', 'Tab, next pane', 'tab'), kb(':', 'Command line', ':'), kb('?', 'Help', '?'));
    acts.forEach((a) => keys.append(kb(a.label, a.label + ' (key ' + a.key + ')', a.key, 'act')));
  }

  function draw() {
    if (!grid.isConnected) return;
    if (!measure()) return;
    const linear = ctl.prefs.linear;
    frame = ctl.frame({ cols: geo.cols, rows: geo.rows });
    wrap.dataset.look = ctl.prefs.look; wrap.dataset.ascii = String(ctl.prefs.ascii); wrap.dataset.sr = String(linear); wrap.dataset.tier = frame.tier; wrap.dataset.screen = frame.screen;
    lookBtn.textContent = LOOKS.find((x) => x.id === ctl.prefs.look).short;
    asciiBtn.setAttribute('aria-pressed', String(ctl.prefs.ascii)); readBtn.setAttribute('aria-pressed', String(linear));
    grid.hidden = linear; lin.hidden = !linear;
    if (linear) paintLinear(frame); else paintGrid(frame);
    keybar(frame);
    const inCmd = frame.mode === 'cmd';
    cmd.hidden = !inCmd;
    if (inCmd && document.activeElement !== input) { input.value = ctl.state.mode.buf; input.focus({ preventScroll: true }); } else if (inCmd && input.value !== ctl.state.mode.buf) input.value = ctl.state.mode.buf;
    if (live.textContent !== frame.live) live.textContent = frame.live;
    const id = ctl.routeId();
    if (ctx.route.name === 'terminal' && (ctx.route.id || '') !== id) { try { history.replaceState(null, '', '#/terminal' + (id ? '/' + id : '')); ctx.route.id = id || null; } catch (e) { /* embedded frame without history */ } }
  }
  t.redraw = draw;
  ctx.redrawTerm = draw;
  ctx.termRoute = (r) => { ctl.route(r.id); draw(); };

  // ---------- events ----------
  const onKey = (e) => {
    const k = keyName(e); if (!k) return;
    if (k === 'esc') escAt = performance.now();
    if ((k === 'tab' || k === 'shift-tab') && (ctl.prefs.linear || performance.now() - escAt < 2500)) return; // Esc then Tab leaves the terminal
    if (ctl.prefs.linear && k === 'tab') return;
    if (ctl.key(k)) e.preventDefault();
    draw();
  };
  grid.addEventListener('keydown', onKey); lin.addEventListener('keydown', onKey);
  const onClick = (e) => {
    const el = e.target.closest && e.target.closest('[data-h]');
    grid.focus({ preventScroll: true });
    if (el) { ctl.click(el.dataset.h); draw(); }
  };
  grid.addEventListener('click', onClick);
  grid.addEventListener('wheel', (e) => { e.preventDefault(); const n = Math.max(1, Math.round(Math.abs(e.deltaY) / 60)); for (let i = 0; i < n; i++) ctl.key(e.deltaY > 0 ? 'down' : 'up'); draw(); }, { passive: false });
  input.addEventListener('input', () => { ctl.cmdSet(input.value); draw(); });
  input.addEventListener('keydown', (e) => {
    const k = keyName(e); if (!k) return;
    if (k === 'esc') { e.preventDefault(); ctl.key('esc'); draw(); grid.focus({ preventScroll: true }); }
    else if (k === 'up' || k === 'down' || k === 'tab') { e.preventDefault(); ctl.key(k); input.value = ctl.state.mode ? ctl.state.mode.buf : ''; draw(); }
  });
  cmd.addEventListener('submit', (e) => { e.preventDefault(); ctl.cmdSubmit(); draw(); if (!ctl.state.mode || ctl.state.mode.kind !== 'cmd') grid.focus({ preventScroll: true }); });

  const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => draw()) : null;
  ctx.mounts.push(() => { if (ro) ro.observe(stage); if (document.fonts && document.fonts.ready) document.fonts.ready.then(draw); draw(); if (!document.body.dataset.embed) grid.focus({ preventScroll: true }); });

  // the slow breath of the core mark, as a glyph swap: only with live work, full motion and a visible tab
  const breath = setInterval(() => {
    if (!grid.isConnected) { clearInterval(breath); return; }
    const on = sim.liveWork().length > 0 && !store.reducedMotion() && !document.hidden;
    ctl.setBreath(on ? !ctl.state.breath : false); draw();
  }, 3000);
  const clearStatus = setInterval(() => { if (!grid.isConnected) { clearInterval(clearStatus); return; } if (ctl.state.status) { ctl.clearStatus(); draw(); } }, 7000);
  return wrap;
}
