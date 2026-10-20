/* LE-5 the motion middle: JS half. NOT product code.
 *
 * The primitives LR Appendix 2 proposes between "instant" and the hero moments. Rules held:
 * transform and opacity only; WAAPI (compositor-driven, parks itself — no rAF loop is ever
 * started here, including for gesture release); every animation is tracked so any input
 * renders its end state at once (F-5); one spatial primitive per region (LR §14 "cognitive
 * load"); reduced motion is a <= 160 ms opacity change or nothing, with focus kept.
 * Fenced per primitive so tools/budget.py can price each one alone.
 */
(function () {
  'use strict';
  /*<core>*/
  const M = (window.MID = { live: new Set(), regions: new Map(), log: [] });
  const root = document.documentElement;
  M.reduced = () => root.dataset.motion === 'reduced' || matchMedia('(prefers-reduced-motion: reduce)').matches;
  M.EASE = 'cubic-bezier(.22,.8,.18,1)';
  /** Run one WAAPI animation, tracked: it ends (finish + cancel) on any input or region reuse. */
  M.anim = function (el, kf, ms, opt) {
    const a = el.animate(kf, Object.assign({ duration: ms, easing: M.EASE }, opt));
    M.live.add(a);
    const done = () => M.live.delete(a);
    a.onfinish = done; a.oncancel = done;
    return a;
  };
  /** One spatial primitive at a time per region: a new one renders the previous one's end. */
  M.claim = function (region, anims) {
    const prev = M.regions.get(region);
    if (prev) for (const a of prev) if (M.live.has(a)) a.finish();
    M.regions.set(region, anims);
    return anims;
  };
  M.settle = function () { for (const a of [...M.live]) a.finish(); };
  /** F-5: any input ends everything in flight. Capture phase, so it runs before the handler. */
  addEventListener('pointerdown', (e) => { if (!e.target.closest('[data-keepalive]')) M.settle(); }, true);
  addEventListener('keydown', M.settle, true);
  M.done = (anims) => Promise.all(anims.map((a) => a.finished.catch(() => 0)));
  /*</core>*/

  /*<flip>*/
  /** FLIP: measure, mutate, invert, play. Only rows that moved and are on screen animate;
   * more than 30 movers is a re-render, not a motion (LR App. 2 "reorder"). */
  M.flip = function (els, mutate, ms, easing) {
    const vh = innerHeight;
    const first = new Map(els.map((e) => [e, e.getBoundingClientRect().top]));
    mutate();
    if (M.reduced()) return [];
    const movers = [];
    for (const e of els) {
      if (!e.isConnected) continue;
      const top = e.getBoundingClientRect().top;
      const d = first.get(e) - top;
      if (Math.abs(d) < 0.5 || (top > vh && first.get(e) > vh) || (top < -60 && first.get(e) < -60)) continue;
      movers.push([e, d]);
    }
    if (movers.length > 30) return [];
    return movers.map(([e, d]) => M.anim(e, [{ transform: `translateY(${d}px)` }, { transform: 'none' }], ms, { easing: easing || M.EASE }));
  };
  /*</flip>*/

  /*<disclose>*/
  /** disclose / collapse: the body appears in place, siblings move by FLIP. 240 open, 200 close;
   * content fades with a 4 px offset. Reduced: instant + 120 ms fade, focus kept. */
  M.disclose = function (row, open) {
    const list = row.parentElement;
    const body = row.querySelector('[data-body]');
    const sibs = [...list.children].filter((e) => e !== row && e.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_PRECEDING);
    let clone = null;
    if (!open && !M.reduced()) {
      clone = body.cloneNode(true);
      clone.classList.add('p-disc-clone');
      clone.style.top = body.offsetTop + 'px';
      row.style.position = 'relative';
      row.appendChild(clone);
    }
    const anims = M.flip(sibs, () => { body.hidden = !open; row.setAttribute('aria-expanded', String(open)); }, open ? 240 : 200);
    if (open) {
      anims.push(M.reduced()
        ? M.anim(body, [{ opacity: 0 }, { opacity: 1 }], 120)
        : M.anim(body, [{ opacity: 0, transform: 'translateY(-4px)' }, { opacity: 1, transform: 'none' }], 240));
    } else if (clone) {
      const a = M.anim(clone, [{ opacity: 1 }, { opacity: 0 }], 120, { easing: 'linear' });
      const rm = () => clone.remove();
      a.finished.then(rm, rm);
      anims.push(a);
    }
    return M.claim(list, anims);
  };
  /*</disclose>*/

  /*<spring>*/
  /** Analytic damped spring (zeta >= 0.72 keeps overshoot <= 4 %, LR §11). Returns position
   * over time from displacement d0 and velocity v0 (px, px/ms) toward 0. */
  M.spring = function (d0, v0, zeta, periodMs) {
    const w = (2 * Math.PI) / periodMs;
    if (zeta >= 1) {
      const B = v0 + w * d0;
      return (t) => (d0 + B * t) * Math.exp(-w * t);
    }
    const wd = w * Math.sqrt(1 - zeta * zeta);
    const B = (v0 + zeta * w * d0) / wd;
    return (t) => Math.exp(-zeta * w * t) * (d0 * Math.cos(wd * t) + B * Math.sin(wd * t));
  };
  /** Sample a spring into WAAPI keyframes: compositor-driven, velocity-aware, parks itself. */
  M.springFrames = function (fn, maxMs, axis) {
    const kf = [];
    let end = maxMs;
    for (let t = 0; t <= maxMs; t += 16) {
      const x = fn(t);
      kf.push(x);
      if (t > 80 && Math.abs(x) < 0.4 && Math.abs(fn(t + 16) - x) < 0.2) { end = t; break; }
    }
    kf.push(0);
    const n = kf.length - 1;
    return { ms: Math.max(end, 16), frames: kf.map((x, i) => ({ offset: i / n, transform: `translate${axis}(${x.toFixed(2)}px)` })) };
  };
  /** The settle easing as a CSS linear() for fire-and-forget moves (reorder): zeta 0.85. */
  M.SETTLE = (() => {
    const f = M.spring(1, 0, 0.85, 420);
    const pts = [];
    for (let i = 0; i <= 24; i++) pts.push((1 - f((240 * i) / 24)).toFixed(3));
    return `linear(${pts.join(',')})`;
  })();
  /*</spring>*/

  /*<reorder>*/
  /** reorder: the same row in a new place, 240 ms, NO stagger, batched (<= 1 per 500 ms). */
  M.reorder = function (list, mutate) {
    const now = performance.now();
    const els = [...list.children];
    if (now - (M._lastReorder || -1e9) < 500) { mutate(); return []; }
    M._lastReorder = now;
    return M.claim(list, M.flip(els, mutate, 240, M.SETTLE));
  };
  /*</reorder>*/

  /*<count>*/
  /** count: a number changed by an event rolls one glyph height in 160 ms; up for more, down
   * for fewer. Reduced and quiet: instant. Screen readers get the text, never the motion. */
  M.count = function (el, to) {
    const cur = el.querySelector('span:last-child');
    const from = cur ? cur.textContent : '';
    to = String(to);
    if (from === to) return [];
    const up = Number(to) > Number(from);
    el.setAttribute('aria-label', to);
    if (M.reduced() || root.dataset.motion === 'quiet' || !cur) { el.innerHTML = `<span aria-hidden="true">${to}</span>`; return []; }
    const nu = document.createElement('span');
    nu.setAttribute('aria-hidden', 'true');
    nu.textContent = to;
    el.appendChild(nu);
    const d = up ? '100%' : '-100%', u = up ? '-100%' : '100%';
    const a1 = M.anim(cur, [{ transform: 'none' }, { transform: `translateY(${u})`, opacity: 0 }], 160);
    const a2 = M.anim(nu, [{ transform: `translateY(${d})` }, { transform: 'none' }], 160);
    const rm = () => cur.remove();
    a1.finished.then(rm, rm);
    return [a1, a2];
  };
  /*</count>*/

  /*<release>*/
  /** release: a dragged strip/sheet tracks the finger 1:1, rubber-bands past its bounds, and
   * on release travels to the snap point PROJECTED from its velocity, by a spring sampled
   * into WAAPI keyframes (zeta 0.86). No rAF loop: gesture release does not need one. */
  M.draggable = function (el, opts) {
    const snaps = opts.snaps; // ascending translateY values, e.g. [-480, 0]
    let pos = opts.start || 0, y0 = 0, p0 = 0, hist = [], drag = false;
    const lo = snaps[0], hi = snaps[snaps.length - 1];
    const band = (p) => (p < lo ? lo - (lo - p) * 0.35 : p > hi ? hi + (p - hi) * 0.35 : p);
    const set = (p) => { el.style.transform = `translateY(${p}px)`; };
    set(pos);
    el.addEventListener('pointerdown', (e) => {
      drag = true; y0 = e.clientY; p0 = pos; hist = [[e.timeStamp, e.clientY]];
      el.setPointerCapture(e.pointerId);
    });
    el.addEventListener('pointermove', (e) => {
      if (!drag) return;
      hist.push([e.timeStamp, e.clientY]);
      if (hist.length > 5) hist.shift();
      pos = band(p0 + e.clientY - y0);
      set(pos);
    });
    const up = () => {
      if (!drag) return;
      drag = false;
      const [t0, a] = hist[0], [t1, b] = hist[hist.length - 1];
      const v = t1 > t0 ? (b - a) / (t1 - t0) : 0; // px/ms
      const projected = pos + v * 180;
      const target = snaps.reduce((m, s) => (Math.abs(s - projected) < Math.abs(m - projected) ? s : m), snaps[0]);
      M.release(el, pos, target, v, opts.onSnap);
      pos = target;
    };
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
    return { snapTo: (t, v) => { M.release(el, pos, t, v || 0, opts.onSnap); pos = t; } };
  };
  M.release = function (el, from, to, v, onSnap) {
    el.style.transform = `translateY(${to}px)`;
    if (onSnap) onSnap(to);
    if (M.reduced()) {
      return [M.anim(el, [{ transform: `translateY(${from}px)` }, { transform: `translateY(${to}px)` }], 160, { easing: 'ease-out' })];
    }
    const s = M.springFrames(M.spring(from - to, v, 0.86, 420), 560, 'Y');
    const frames = s.frames.map((k) => ({ offset: k.offset, transform: k.transform.replace(/\(([-\d.]+)px\)/, (_, x) => `(${(+x + to).toFixed(2)}px)`) }));
    return [M.anim(el, frames, s.ms, { easing: 'linear' })];
  };
  /*</release>*/

  /*<tooltip>*/
  /** tooltip group: the first one waits 700 ms; a peer within 300 ms of the last shows at once.
   * Opacity only. Focus shows it too (proof of life is reachable by keyboard). */
  M.tooltips = function (scope) {
    let tip = null, timer = 0, lastHide = -1e9;
    const show = (t) => {
      hide();
      tip = document.createElement('div');
      tip.className = 'p-tip';
      tip.setAttribute('role', 'tooltip');
      tip.textContent = t.dataset.tip;
      document.body.appendChild(tip);
      const r = t.getBoundingClientRect();
      tip.style.left = Math.min(r.left, innerWidth - tip.offsetWidth - 8) + 'px';
      tip.style.top = r.bottom + 6 + 'px';
      t.setAttribute('aria-describedby', 'p-tip');
      tip.id = 'p-tip';
      if (!M.reduced()) M.anim(tip, [{ opacity: 0 }, { opacity: 1 }], 120, { easing: 'linear' });
    };
    const hide = () => { clearTimeout(timer); if (tip) { tip.remove(); tip = null; lastHide = performance.now(); } };
    const enter = (e) => {
      const t = e.target.closest('[data-tip]');
      if (!t) return;
      clearTimeout(timer);
      if (performance.now() - lastHide < 300 || e.type === 'focusin') show(t);
      else timer = setTimeout(() => show(t), 700);
    };
    const leave = (e) => { if (e.target.closest('[data-tip]')) hide(); };
    scope.addEventListener('pointerover', enter);
    scope.addEventListener('pointerout', leave);
    scope.addEventListener('focusin', enter);
    scope.addEventListener('focusout', leave);
  };
  /*</tooltip>*/

  /*<nav>*/
  /** navigation between peers: by keyboard instant; by pointer a 120 ms opacity crossfade.
   * Never a directional slide (A keeps a fade; LR §11 rejects peer slides). */
  M.nav = function (host, render, byKey) {
    render();
    if (byKey || M.reduced()) return [];
    return M.claim(host, [M.anim(host, [{ opacity: 0.001 }, { opacity: 1 }], 120, { easing: 'linear' })]);
  };
  /*</nav>*/

  /*<confirm>*/
  /** confirm: the committed decision's label becomes the result with its time, the row
   * recedes in place (it does NOT leave and pull rows under the pointer), and focus moves to
   * the next decision at once — keystrokes during the 240 ms land on the next row. */
  M.confirm = function (row, label, next) {
    const btn = row.querySelector('[data-verb]');
    btn.textContent = label;
    btn.disabled = true;
    row.classList.add('p-decided');
    row.setAttribute('aria-disabled', 'true');
    if (next) next.focus();
    if (M.reduced()) return [];
    return [M.anim(btn, [{ opacity: 0.2 }, { opacity: 1 }], 160, { easing: 'linear' })];
  };
  /** refuse: the reason appears beside the item and focus goes to the recovery action. No shake. */
  M.refuse = function (row, reason, recover) {
    let r = row.querySelector('[data-reason]');
    if (!r) { r = document.createElement('p'); r.dataset.reason = ''; r.setAttribute('role', 'status'); row.appendChild(r); }
    r.textContent = reason;
    if (recover) recover.focus();
    return M.reduced() ? [] : [M.anim(r, [{ opacity: 0 }, { opacity: 1 }], 160, { easing: 'linear' })];
  };
  /*</confirm>*/

  /*<push>*/
  /** push / pop (phone, hierarchical): a decision page enters from the right over 280 ms and
   * owns a history entry, so Back closes it and never exits the app (rulebook §25).
   * Reduced: instant. Peers never slide; only depth does. */
  M.push = function (page, onPop) {
    page.hidden = false;
    history.pushState({ page: page.id }, '');
    const h = () => { removeEventListener('popstate', h); M.pop(page, true); if (onPop) onPop(); };
    addEventListener('popstate', h);
    page.querySelector('[data-first]')?.focus({ preventScroll: true });
    if (M.reduced()) return [];
    return M.claim('page', [M.anim(page, [{ transform: 'translateX(100%)' }, { transform: 'none' }], 280)]);
  };
  M.pop = function (page, fromHistory) {
    if (!fromHistory) { history.back(); return []; }
    if (M.reduced()) { page.hidden = true; return []; }
    const a = M.anim(page, [{ transform: 'none' }, { transform: 'translateX(100%)' }], 240);
    const hide = () => { page.hidden = true; };
    a.finished.then(hide, hide);
    return M.claim('page', [a]);
  };
  /*</push>*/
})();
