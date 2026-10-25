// The terminal view: a monospace panel that shows the same simulated state the TUI would. Text is laid out for the columns that fit.
import { h, clear } from './dom.js';
import { termModel, TERM_SCREENS } from '../term.js';

export function viewTerminal(ctx) {
  const ui = ctx.ui.term || (ctx.ui.term = { screen: 'now', sel: 0, mission: 1, ascii: false });
  const sim = ctx.sim;
  const pre = h('pre', { class: 'term-screen', tabindex: '0', role: 'region', 'aria-label': 'Terminal view of the simulated state', 'data-key': 'term' });
  const probe = h('span', { class: 'term-probe', 'aria-hidden': 'true' }, '0'.repeat(40));
  let model = null;

  const go = (screen) => { ui.screen = screen; ui.sel = 0; draw(); };
  const move = (d) => { const n = model ? model.items.length : 0; if (n) { ui.sel = (ui.sel + d + n) % n; draw(); } };
  const open = () => {
    const it = model && model.items[ui.sel]; if (!it) return;
    if (it.mission) { const ids = Object.keys(sim.state.missions); ui.mission = ids.indexOf(it.mission); go('replay'); }
  };
  const decide = (kind) => {
    const it = model && model.items[ui.sel];
    if (it && it.kind === 'attention' && it.ref && String(it.ref).startsWith('a-')) ctx.act(kind, it.ref);
    else ctx.toast('Select a decision first (Attention or Now), then ' + (kind === 'approve' ? 'p' : 'x') + '.');
  };
  const key = (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key; let used = true;
    if (k === 'j' || k === 'ArrowDown') move(1); else if (k === 'k' || k === 'ArrowUp') move(-1); else if (k === 'Enter') open();
    else if (k === 'p') decide('approve'); else if (k === 'x') decide('reject'); else if (k === 'n' && ui.screen === 'replay') { ui.mission += 1; draw(); }
    else if (k === 'q' || k === 'Escape') ctx.nav('#/now');
    else { const sc = TERM_SCREENS.find((s) => s.key === k); if (sc) go(sc.id); else used = false; }
    if (used) e.preventDefault();
  };
  pre.addEventListener('keydown', key);

  function cols() {
    const cw = probe.getBoundingClientRect().width / 40 || 8;
    const cs = getComputedStyle(pre), pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    return Math.max(30, Math.floor((pre.clientWidth - pad) / cw) - 1);
  }
  function draw() {
    if (!pre.isConnected) return;
    model = termModel(sim, { cols: cols(), screen: ui.screen, sel: ui.sel, mission: ui.mission, ascii: ui.ascii });
    if (ui.sel > model.items.length - 1) { ui.sel = Math.max(0, model.items.length - 1); model = termModel(sim, { cols: model.cols, screen: ui.screen, sel: ui.sel, mission: ui.mission, ascii: ui.ascii }); }
    clear(pre);
    model.lines.forEach((l) => pre.append(h('span', { class: 'l ' + l.k }, l.t || ' ')));
    bar.querySelectorAll('[data-screen]').forEach((b) => b.setAttribute('aria-current', b.dataset.screen === ui.screen ? 'true' : 'false'));
    asciiBtn.setAttribute('aria-pressed', ui.ascii ? 'true' : 'false');
  }
  const asciiBtn = h('button', { class: 'btn', type: 'button', 'aria-pressed': 'false', onclick: () => { ui.ascii = !ui.ascii; draw(); } }, 'ASCII');
  const bar = h('div', { class: 'term-bar' },
    h('a', { class: 'btn', href: '#/now' }, 'App'),
    ...TERM_SCREENS.map((s) => h('button', { class: 'btn', type: 'button', 'data-screen': s.id, onclick: () => go(s.id) }, s.key + ' ' + s.label)),
    h('span', { class: 'sp' }), asciiBtn);
  const keys = h('div', { class: 'term-keys', role: 'group', 'aria-label': 'Terminal keys' },
    h('button', { class: 'btn', type: 'button', 'aria-label': 'Up', onclick: () => move(-1) }, 'k up'), h('button', { class: 'btn', type: 'button', 'aria-label': 'Down', onclick: () => move(1) }, 'j down'),
    h('button', { class: 'btn', type: 'button', onclick: open }, 'Enter'), h('button', { class: 'btn', type: 'button', onclick: () => decide('approve') }, 'p approve'), h('button', { class: 'btn', type: 'button', onclick: () => decide('reject') }, 'x reject'),
    h('a', { class: 'btn', href: '#/now' }, 'q back'));
  const wrap = h('div', { class: 'term-wrap' }, bar, pre, keys, probe);
  ctx.mounts.push(() => { draw(); if (ctx.ui.focusTerm) pre.focus({ preventScroll: true }); });
  ctx.redrawTerm = draw;
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => draw()).observe(pre);
  return wrap;
}
