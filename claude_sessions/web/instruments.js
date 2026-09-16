'use strict';
/* ── instruments ───────────────────────────────────────────────────────────
   Readable gauges, bound to numbers the page already fetched, drawn next to the
   number they describe. This replaced 26 generative "ambient motion" renderers
   that painted abstract fields (rain, embers, petals, dust) behind the whole
   app: the data was real but nobody could read a token burn rate off a shower
   of falling pixels, and the field looped forever whether or not anything had
   happened.

   The vocabulary comes from the reference dashboards in references/:

     ring   donut arc + outer tick ring, DOM readout in the middle
            → plan quota, MCP up/total
     dial   240° needle gauge with zones and minor ticks
            → burn rate against your own peak day
     spark  area sparkline, gradient fill, lit last point
            → 7/14/30-day token trend
     eq     thin equalizer strip; the ONE continuously-moving instrument, and
            only while there is something to move for
            → live burn, running jobs
     flow   node map, dashed links between projects sharing an account
            → the workspace at a glance

   Three rules keep this off the flicker path (CLAUDE.md):

   1. ONE rAF chain for the whole app, owned by MO.frame(), and it PARKS. An
      instrument registers a job only while its value is still travelling to a
      new target (or while it is genuinely live, like eq during an active burn).
      Settled dashboard → job set empties → zero frames. This is the concrete
      answer to "animated everywhere": nothing animates unless something moved.

   2. Geometry on canvas, text in the DOM. Canvas text needs font loading, does
      not inherit the theme, cannot be selected, and re-rasterises every frame.
      The centre readouts are real elements, so MO.count can tween them and the
      palette applies for free.

   3. Backing store at min(devicePixelRatio, 2) — NOT the ambient layer's clamp
      of 1. That clamp was right for a full-screen blurred field and wrong for
      1px ticks and hairline arcs, which alias badly at 1x on a 4K panel. These
      are small, so the extra fill is negligible.

   Feeds cost nothing: every page renderer already fetches what its surface
   needs and calls INST.set(). No instrument ever issues its own request. */

const INST_TAU = 0.16;            // seconds to close ~63% of the gap
const INST_EPS = 0.0015;          // below this, snap and park
const INST_MAX = 24;              // hard cap on simultaneously mounted gauges
const INST_FPS = 30;              // ceiling; a gauge has nothing to say at 60

function iEase(cur, tgt, dt) {
  return cur + (tgt - cur) * (1 - Math.exp(-dt / INST_TAU));
}
function iRgba(hex, a) {
  return `rgba(${INST.rgb(hex)},${a})`;
}
function iClamp(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

/* The event palette is authored ONCE, in Python, for the standalone flow page —
   which is always dark, so every hue sits at 70-85% lightness. The dashboard is
   not: ten of the shipped palettes are light or OLED, and #f9e2af on a white
   card is 1.2:1. So the HUE is the shared vocabulary (a tool is the same yellow
   on both surfaces) and the LIGHTNESS is a per-mode transform, rather than a
   second colour table to keep in step with the first. Same argument ACCT_RAMP
   already makes: a categorical scale is tuned per ground, not generated. */
const iShadeCache = {};
function iShade(hex, mode) {
  const k = hex + mode;
  if (iShadeCache[k]) return iShadeCache[k];
  const n = parseInt(String(hex).slice(1), 16);
  const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let hh = 0;
  if (d) {
    if (mx === r) hh = ((g - b) / d + (g < b ? 6 : 0));
    else if (mx === g) hh = (b - r) / d + 2;
    else hh = (r - g) / d + 4;
    hh *= 60;
  }
  const l = (mx + mn) / 2;
  const s = d ? d / (1 - Math.abs(2 * l - 1)) : 0;
  // 38% on a light ground clears 4.5:1 against every light panel in the set;
  // dark grounds keep the authored value, so nothing changes on the 22 themes
  // the flow page was tuned against.
  const L = mode === 'light' ? Math.min(l, 0.38) : l;
  return (iShadeCache[k] = `hsl(${hh.toFixed(0)} ${(s * 100).toFixed(0)}% ${(L * 100).toFixed(0)}%)`);
}
/* normalise a series to 0..1 against its own max — every instrument shows a
   shape relative to the caller's own history, never an absolute scale */
function iNorm(arr) {
  const m = Math.max(...(arr || []), 0) || 1;
  return (arr || []).map(v => (v || 0) / m);
}

const INST = {
  reg: [],                  // mounted targets
  feeds: {},                // key -> latest data pushed by a page renderer
  P: null,                  // resolved palette (hex, not var())
  /* per-skin stroke language. A HUD ring and a Sakura ring must not be the same
     ring recoloured — the skin owns tick SHAPE, line cap, stroke weight and glow.
     Defaults are the HUD values so a gauge drawn before applyTheme still looks
     deliberate rather than unstyled. */
  SK: { tick: 'line', cap: 'round', lw: 1.0, glow: .5 },
  setSkin(sk) {
    if (sk && sk.gauge) this.SK = { ...this.SK, ...sk.gauge };
    this.draw(true);
  },
  io: null,
  acc: 0,
  job: null,

  /* ── palette ──
     Canvas gradients cannot parse var(), so the hex is resolved once per theme
     change and cached. applyTheme() calls this. */
  setTheme(pal) {
    this.P = pal ? { ...pal } : null;
    this._rgb = {};
    for (const t of this.reg) t.S = { ...t.S, _g: null };
    this.draw(true);
  },
  rgb(hex) {
    if (!hex) return '125,207,255';
    this._rgb = this._rgb || {};
    if (!this._rgb[hex]) {
      const n = parseInt(String(hex).slice(1), 16);
      this._rgb[hex] = `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
    }
    return this._rgb[hex];
  },

  /* ── markup ──
     Emitted by the page renderers so an instrument is one call, and so the
     readout markup (which MO.count drives) stays consistent everywhere.

     Three-part structure, and the nesting matters: .inst is a FIXED-height box
     that the canvas fills, and only a donut's readout may live inside it. The
     label (and every other gauge's readout) is a sibling in .iwrap. Putting them
     inside .inst instead — as an earlier cut did — overflows the fixed height and
     lands the text on top of whatever the card renders next. */
  html(kind, key, o) {
    o = o || {};
    // a ring has a genuinely empty centre; a needle dial has a hub and a needle
    // sweeping through it, and the flat gauges have a trace across the whole box
    const over = kind === 'ring';
    // NOTE: no data-num here. That attribute is the declarative path MO.counts()
    // sweeps on every mount, and these readouts are driven imperatively by
    // setRead() instead — carrying both meant a mount right after a feed re-applied
    // the markup's stale 0 over the value that had just been pushed.
    const read = o.noread ? '' :
      `<div class="iread"><b data-fmt="${o.fmt || 'pct'}">–</b>` +
      (o.unit ? `<i>${o.unit}</i>` : '') +
      (o.sub ? `<u>${o.sub}</u>` : '') + `</div>`;
    return `<div class="iwrap i-${kind}${o.big ? ' big' : ''}" data-k="${key}"` +
      (o.title ? ` title="${o.title}"` : '') + `>` +
      `<div class="inst" data-inst="${kind}" data-k="${key}">` +
      `<canvas></canvas>${over ? read : ''}</div>` +
      (over ? '' : read) +
      (o.label ? `<div class="ilbl">${o.label}</div>` : '') + `</div>`;
  },

  /* ── mounting ──
     Any [data-inst] in the DOM, whenever it appears. The SPA rewrites #content
     wholesale, so detached targets are swept rather than tracked. */
  mount(root) {
    (root || document).querySelectorAll('.inst[data-inst]').forEach(el => {
      if (el.__inst || this.reg.length >= INST_MAX) return;
      const cv = el.querySelector('canvas');
      if (!cv) return;
      el.__inst = 1;
      const t = { el, cv, kind: el.dataset.inst, key: el.dataset.k || 'global',
                  S: {}, vis: true };
      this.reg.push(t);
      if (!this.io && window.IntersectionObserver)
        this.io = new IntersectionObserver(es => {
          for (const e of es) {
            const tg = this.reg.find(x => x.el === e.target);
            if (tg) tg.vis = e.isIntersecting;
          }
          this.wake();
        }, { threshold: 0 });
      if (this.io) this.io.observe(el);
    });
    this.draw(true);
  },
  sweep() {
    for (let i = this.reg.length - 1; i >= 0; i--) {
      const t = this.reg[i];
      if (t.el.isConnected) continue;
      if (this.io) this.io.unobserve(t.el);
      t.el.__inst = 0;
      this.reg.splice(i, 1);
    }
  },

  /* ── feeds ──
     set() is the only way data reaches an instrument. Pushing the same value
     again is free: the target does not change, so nothing wakes up. */
  set(key, data) {
    const prev = this.feeds[key];
    this.feeds[key] = { ...(prev || {}), ...data };
    this.wake();
  },
  feed(key) { return this.feeds[key] || {}; },
  /* A feed outlives its gauge on purpose — a page renderer sets before it
     mounts. That is fine for the fixed keys ('quota', 'burn', …) and a slow
     leak for a key made from a session id, which only ever grows: the caller
     that knows an id has gone says so. */
  drop(key) { delete this.feeds[key]; },

  /* ── scheduler ──
     wake() registers the shared job; the job retires itself once every gauge
     has settled and none is live. That retirement is the whole design. */
  wake() {
    if (!this.reg.length || this.job) return;
    if (!window.MO) return;
    this.job = MO.frame(dt => {
      this.acc += dt;
      if (this.acc < 1 / INST_FPS) return true;      // frame cap
      const step = this.acc; this.acc = 0;
      this.sweep();
      const moving = this.draw(false, step);
      if (moving) return true;
      this.job = null;                               // parked
      return false;
    });
  },

  /* one pass over every mounted instrument. Returns true if anything still
     needs another frame — either mid-tween or declared live. */
  draw(force, dt) {
    if (!this.P) return false;
    let moving = false;
    for (const t of this.reg) {
      if (!t.vis && !force) continue;
      const w = t.cv.clientWidth, h = t.cv.clientHeight;
      if (!w || !h) continue;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const bw = Math.round(w * dpr), bh = Math.round(h * dpr);
      if (t.cv.width !== bw || t.cv.height !== bh) { t.cv.width = bw; t.cv.height = bh; }
      const c = t.cv.getContext('2d');
      c.setTransform(dpr, 0, 0, dpr, 0, 0);
      c.clearRect(0, 0, w, h);
      const fn = IKIND[t.kind] || IKIND.ring;
      let live = false;
      try { live = fn(c, w, h, this.feed(t.key), t.S, this.P, force ? 0 : (dt || 0)); }
      catch (e) { live = false; }
      if (live) moving = true;
    }
    return moving && (!window.MO || MO.on);
  },

  /* re-fit every canvas. The Qt shell and the 720px transcript drawer both
     change available width WITHOUT firing a window resize event, so app.js
     drives this from a ResizeObserver rather than trusting onresize. */
  refit() { this.draw(true); },
  clear() {
    for (const t of this.reg) { if (this.io) this.io.unobserve(t.el); t.el.__inst = 0; }
    this.reg.length = 0;
    if (this.job && window.MO) { MO.unframe(this.job); this.job = null; }
  },
};

/* ── the renderers ─────────────────────────────────────────────────────────
   Each takes (ctx, w, h, data, scratch, palette, dt) and returns whether it
   wants another frame. dt === 0 means "settle immediately" (a forced redraw
   after a mount, theme change or resize) — never animate into a resize, or
   every layout change looks like a data change. */
const TAU2 = Math.PI * 2;

function iSettle(S, name, target, dt) {
  const cur = S[name] == null ? (dt ? 0 : target) : S[name];
  if (!dt) { S[name] = target; return { v: target, moving: false }; }
  const v = iEase(cur, target, dt);
  const moving = Math.abs(target - v) > INST_EPS;
  S[name] = moving ? v : target;
  return { v: S[name], moving };
}

const IKIND = {
  /* ── ring: donut arc + outer tick ring ──
     ref: the 94% DEPLOY donut and the HUD dials. The tick ring is what makes it
     read as an instrument rather than a progress pie; ticks under the arc light
     up as the value passes them, so the value is legible without the number. */
  ring(c, w, h, D, S, P, dt) {
    const { v, moving } = iSettle(S, 'v', iClamp(D.v), dt);
    const cx = w / 2, cy = h / 2;
    const R = Math.min(w, h) / 2 - 7;
    const lw = Math.max(3, R * 0.20);
    const tone = D.tone === 'warn' ? P.warn : D.tone === 'err' ? P.err
      : D.tone === 'ok' ? P.ok : P.accent;
    const SK = INST.SK;
    const lww = lw * SK.lw;
    // track
    c.lineWidth = lww; c.lineCap = 'butt';
    c.strokeStyle = iRgba(P.line, 0.9);
    c.beginPath(); c.arc(cx, cy, R, 0, TAU2); c.stroke();
    // tick ring: shape is the skin's — hairlines for HUD/neon, dots for the soft
    // skins, chunky blocks for mecha/brutal/crt
    const N = SK.tick === 'block' ? 24 : 36;
    for (let i = 0; i < N; i++) {
      const a = -Math.PI / 2 + TAU2 * i / N;
      const lit = i / N <= v;
      const r0 = R + lww / 2 + 2;
      const col = lit ? iRgba(tone, 0.65) : iRgba(P.dim2, 0.30);
      if (SK.tick === 'dot') {
        c.fillStyle = col;
        c.beginPath(); c.arc(cx + Math.cos(a) * (r0 + 2), cy + Math.sin(a) * (r0 + 2),
          lit ? 1.6 : 1, 0, TAU2); c.fill();
      } else if (SK.tick === 'block') {
        c.fillStyle = col;
        c.save(); c.translate(cx + Math.cos(a) * (r0 + 2.5), cy + Math.sin(a) * (r0 + 2.5));
        c.rotate(a); c.fillRect(-2.5, -1.6, 5, 3.2); c.restore();
      } else {
        c.strokeStyle = col; c.lineWidth = 1;
        c.beginPath();
        c.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
        c.lineTo(cx + Math.cos(a) * (r0 + (lit ? 4 : 2.5)), cy + Math.sin(a) * (r0 + (lit ? 4 : 2.5)));
        c.stroke();
      }
    }
    /* value arc — ONE arc, or one arc per segment.
       `segments` exists because a single number cannot answer "how much of this
       is whose". Each entry is {v, color}: v is that segment's share of the
       whole (they sum to <= 1), and the arcs are laid end to end from 12
       o'clock. A stacked arc is the right shape precisely when the parts ARE
       additive — which is why the dashboard feeds it tokens and never
       percentages of five separate quotas. */
    const segs = Array.isArray(D.segments) ? D.segments.filter(s => s && s.v > 0.001) : null;
    if (segs && segs.length) {
      if (SK.glow) {
        c.shadowColor = iRgba(tone, SK.glow * 0.5);
        c.shadowBlur = 8 * SK.glow;
      }
      c.lineWidth = lww;
      // butt caps between segments: a round cap would overlap its neighbour and
      // make two adjacent shares look like one
      c.lineCap = segs.length > 1 ? 'butt' : SK.cap;
      // ALWAYS normalised: the segments together fill exactly `v`, whatever
      // scale the caller happened to hand over. Leaving a gap when they sum to
      // less than 1 would read as unaccounted usage rather than as rounding.
      let a0 = -Math.PI / 2;
      const total = segs.reduce((n, s) => n + s.v, 0) || 1;
      for (const s of segs) {
        const a1 = a0 + TAU2 * v * (s.v / total);
        c.strokeStyle = s.color || tone;
        c.beginPath(); c.arc(cx, cy, R, a0, a1); c.stroke();
        a0 = a1;
      }
      c.shadowBlur = 0;
    } else if (v > 0.001) {
      const g = c.createLinearGradient(cx - R, cy - R, cx + R, cy + R);
      g.addColorStop(0, tone);
      g.addColorStop(1, D.tone ? tone : P.accent2);
      if (SK.glow) {                    // a canvas shadow is a paint-time blur on
        c.shadowColor = iRgba(tone, SK.glow * 0.5);   // a small surface, not a
        c.shadowBlur = 8 * SK.glow;                   // framebuffer readback
      }
      c.strokeStyle = g; c.lineWidth = lww; c.lineCap = SK.cap;
      c.beginPath();
      c.arc(cx, cy, R, -Math.PI / 2, -Math.PI / 2 + TAU2 * v);
      c.stroke();
      c.shadowBlur = 0;
    }
    return moving;
  },

  /* ── dial: 240° needle gauge ──
     ref: the UV-index gauge and the CLOCK SPEED dials. Zones carry the
     judgement (this is fine / this is hot) so the needle only has to carry the
     value; a bare needle with no zones makes the reader do the thinking. */
  dial(c, w, h, D, S, P, dt) {
    const { v, moving } = iSettle(S, 'v', iClamp(D.v), dt);
    const cx = w / 2, cy = h * 0.60;
    const R = Math.min(w / 2, h * 0.62) - 6;
    const A0 = Math.PI * 0.75, SW = Math.PI * 1.5;         // 240° sweep
    const lw = Math.max(3, R * 0.16);
    c.lineCap = 'butt';
    // zones: cool → warm → hot, so a needle in the last third reads as a cost
    const zones = D.zones || [[0, 0.6, P.accent], [0.6, 0.85, P.warn], [0.85, 1, P.err]];
    for (const [z0, z1, col] of zones) {
      c.strokeStyle = iRgba(col, 0.22); c.lineWidth = lw;
      c.beginPath(); c.arc(cx, cy, R, A0 + SW * z0, A0 + SW * z1); c.stroke();
    }
    // minor ticks
    for (let i = 0; i <= 20; i++) {
      const a = A0 + SW * (i / 20), maj = i % 5 === 0;
      const r0 = R - lw / 2 - 2, r1 = r0 - (maj ? 6 : 3);
      c.strokeStyle = iRgba(maj ? P.dim : P.dim2, maj ? 0.55 : 0.30);
      c.lineWidth = 1;
      c.beginPath();
      c.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
      c.lineTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1);
      c.stroke();
    }
    // travelled arc
    const zone = zones.find(z => v <= z[1]) || zones[zones.length - 1];
    c.strokeStyle = iRgba(zone[2], 0.85); c.lineWidth = lw; c.lineCap = 'round';
    c.beginPath(); c.arc(cx, cy, R, A0, A0 + SW * Math.max(0.001, v)); c.stroke();
    // needle + hub
    const a = A0 + SW * v;
    c.strokeStyle = iRgba(P.txt, 0.85); c.lineWidth = 2; c.lineCap = 'round';
    c.beginPath();
    c.moveTo(cx - Math.cos(a) * R * 0.14, cy - Math.sin(a) * R * 0.14);
    c.lineTo(cx + Math.cos(a) * R * 0.80, cy + Math.sin(a) * R * 0.80);
    c.stroke();
    c.fillStyle = iRgba(zone[2], 0.95);
    c.beginPath(); c.arc(cx, cy, Math.max(2.5, R * 0.09), 0, TAU2); c.fill();
    return moving;
  },

  /* ── spark: area sparkline ──
     ref: the O₂ Concentration card. The gradient fill is what gives a 30px-tall
     trace enough body to read at a glance; the lit last point tells you which
     end is now, which a bare polyline does not. */
  spark(c, w, h, D, S, P, dt) {
    const src = iNorm(D.series || []);
    if (src.length < 2) return false;
    // tween element-wise so a day rolling off the window slides rather than jumps
    S.s = S.s || src.slice();
    if (S.s.length !== src.length) S.s = src.slice();
    let moving = false;
    const s = S.s;
    for (let i = 0; i < src.length; i++) {
      if (!dt) { s[i] = src[i]; continue; }
      s[i] = iEase(s[i], src[i], dt);
      if (Math.abs(src[i] - s[i]) > INST_EPS) moving = true; else s[i] = src[i];
    }
    const PB = 3, PT = 4;
    const X = i => (i / (s.length - 1)) * (w - 2) + 1;
    const Y = v => h - PB - v * (h - PB - PT);
    const g = c.createLinearGradient(0, PT, 0, h);
    g.addColorStop(0, iRgba(P.accent, 0.34));
    g.addColorStop(1, iRgba(P.accent, 0));
    c.beginPath();
    c.moveTo(X(0), h);
    for (let i = 0; i < s.length; i++) c.lineTo(X(i), Y(s[i]));
    c.lineTo(X(s.length - 1), h);
    c.closePath();
    c.fillStyle = g; c.fill();
    c.beginPath();
    for (let i = 0; i < s.length; i++) i ? c.lineTo(X(i), Y(s[i])) : c.moveTo(X(i), Y(s[i]));
    c.strokeStyle = iRgba(P.accent, 0.9);
    c.lineWidth = 1.5; c.lineJoin = 'round'; c.lineCap = 'round';
    c.stroke();
    const lx = X(s.length - 1), ly = Y(s[s.length - 1]);
    const hg = c.createRadialGradient(lx, ly, 0, lx, ly, 7);
    hg.addColorStop(0, iRgba(P.accent2, 0.55));
    hg.addColorStop(1, iRgba(P.accent2, 0));
    c.fillStyle = hg; c.beginPath(); c.arc(lx, ly, 7, 0, TAU2); c.fill();
    c.fillStyle = P.accent2; c.beginPath(); c.arc(lx, ly, 2.2, 0, TAU2); c.fill();
    return moving;
  },

  /* ── eq: equalizer strip ──
     ref: the Wind Status panel. The ONLY instrument that keeps moving with a
     static input, because "a job is running right now" is itself a continuous
     fact — and the instant the last job ends it goes still and the whole frame
     loop parks.

     `beats` (running jobs) alone decides whether it moves. `v` (throughput) only
     shapes the bars. Getting that backwards is a trap worth naming: driving
     liveness off `v` meant the strip animated forever any time you had spent a
     token today, which is always — the exact "animated everywhere" failure this
     layer replaced, reintroduced through a one-word feed mistake. */
  eq(c, w, h, D, S, P, dt) {
    const { v, moving } = iSettle(S, 'v', iClamp(D.v), dt);
    const beats = Math.max(0, D.beats || 0);
    const live = beats > 0;
    S.t = (S.t || 0) + (dt || 0) * (0.6 + v * 2.4);
    const src = (D.series && D.series.length) ? iNorm(D.series) : null;
    const N = Math.max(12, Math.min(40, Math.round(w / 6)));
    const bw = w / N;
    for (let i = 0; i < N; i++) {
      const base = src ? src[Math.floor(i / N * src.length)] : 0.45;
      // a travelling wave, not per-bar noise: noise reads as a decoration,
      // a wave reads as throughput
      const wave = live ? (0.5 + 0.5 * Math.sin(S.t * 2.2 - i * 0.42)) : 0;
      const bh = Math.max(1.5, (h - 2) * (0.12 + base * 0.5 * (0.45 + v * 0.55)
        + wave * 0.30 * v));
      const g = c.createLinearGradient(0, h - bh, 0, h);
      g.addColorStop(0, iRgba(beats && i % 7 === 0 ? P.warn : P.accent, 0.85));
      g.addColorStop(1, iRgba(P.accent2, 0.12));
      c.fillStyle = g;
      const x = i * bw + bw * 0.22, bwe = Math.max(1.5, bw * 0.56);
      c.beginPath();
      // rounded caps: the reference bars are all pill-shaped, and a 2px radius
      // is the difference between "chart" and "readout"
      if (c.roundRect) { c.roundRect(x, h - bh, bwe, bh, Math.min(bwe / 2, 2)); c.fill(); }
      else c.fillRect(x, h - bh, bwe, bh);
    }
    c.fillStyle = iRgba(P.line, 0.9);
    c.fillRect(0, h - 1, w, 1);
    return moving || (live && (!window.MO || MO.on));
  },

  /* ── flow: the workspace as a node map ──
     ref: the CODE FLOW MAP panel. Absorbs what used to be a second, separate
     rAF chain (the dashboard "constellation"): same deterministic golden-angle
     layout, so positions never jitter between frames and identical data always
     lands identically, but rendered as ring-outline nodes with dashed links —
     legible structure instead of a nebula of glow blobs.

     Nothing here loops. An earlier cut marched the link dashes forever, which is
     precisely the decorative motion this rewrite exists to remove: a dependency
     edge is *structure*, not activity, so animating it says nothing and costs a
     frame every 33ms for as long as the dashboard is open. The map animates only
     when it has something to say — nodes ease outward as they arrive — and then
     holds still. */
  flow(c, w, h, D, S, P, dt) {
    const items = D.items || [];
    if (!items.length) {
      c.strokeStyle = iRgba(P.line, 0.7);
      c.setLineDash([3, 4]);
      c.strokeRect(8, 8, w - 16, h - 16);
      c.setLineDash([]);
      return false;
    }
    const { v: grow, moving } = iSettle(S, 'g', 1, dt);
    // golden-angle spiral, solved from the index alone
    const pos = items.map((n, i) => {
      const a = 2.399963 * i, r = 26 * Math.sqrt(i);
      return [Math.cos(a) * r, Math.sin(a) * r];
    });
    let ext = 1;
    items.forEach((n, i) => {
      ext = Math.max(ext, Math.hypot(pos[i][0], pos[i][1]) + 22);
    });
    const k = Math.min((w / 2 - 8) / ext, (h / 2 - 8) / ext, 1.7);
    const cx = w / 2, cy = h / 2;
    const XY = i => [cx + pos[i][0] * k * grow, cy + pos[i][1] * k * grow];
    // links first, so nodes sit on top of them
    const links = D.links || [];
    c.lineWidth = 1;
    c.setLineDash([2, 5]);
    for (const l of links.slice(0, 48)) {
      const A = XY(l[0]), B = XY(l[1]);
      if (!A || !B) continue;
      c.strokeStyle = iRgba(P.accent, 0.10 + Math.min(0.22, (l[2] || 1) * 0.07));
      c.beginPath(); c.moveTo(A[0], A[1]); c.lineTo(B[0], B[1]); c.stroke();
    }
    c.setLineDash([]);
    items.forEach((n, i) => {
      const [x, y] = XY(i);
      const r = Math.max(2.5, (3 + (n.v || 0) * 7) * Math.min(1, k * 1.1));
      const col = n.col || P.accent;
      const heat = n.heat == null ? 0.6 : n.heat;
      // a filled core inside an outline ring: the ring says "this exists", the
      // core's opacity says "this is warm". A glow blob said only the latter.
      c.strokeStyle = iRgba(col, 0.25 + heat * 0.5);
      c.lineWidth = 1.2;
      c.beginPath(); c.arc(x, y, r + 3, 0, TAU2); c.stroke();
      c.fillStyle = iRgba(col, 0.30 + heat * 0.55);
      c.beginPath(); c.arc(x, y, r, 0, TAU2); c.fill();
    });
    return moving;
  },

  /* ── trail: one live session's recent flow, as typed ticks ──
     The glance half of the session flow graph. The full graph (/flow) lays
     events on a CLAMPED CLOCK, because there it has a whole window and you are
     asking where the time went. Here the question is different — "what is this
     session doing" — and the answer wants every recent event visible, so the
     axis is the event INDEX. 160 ticks across ~320px is 2px each: a burst of
     tool calls reads as a dense band and a stalled session as a short one,
     which a time axis would flatten into a blob and a margin of nothing.

     Type is the only channel, and it is the SAME type vocabulary the big graph
     uses, so the strip teaches the page you click through to. Errors are drawn
     full height over a shorter baseline rather than in a louder colour: a red
     that has to win against 32 palettes is a red that shouts on all of them.

     Nothing loops. The track wipes in once when the card arrives and the job
     retires — a session being busy is not a reason to spend a frame every 33ms
     saying so, and a poll that appends three events simply draws them. */
  trail(c, w, h, D, S, P, dt) {
    const evs = D.events || [];
    if (!evs.length) {
      c.strokeStyle = iRgba(P.line, 0.7);
      c.setLineDash([3, 4]);
      c.strokeRect(1, h / 2 - 5, w - 2, 10);
      c.setLineDash([]);
      return false;
    }
    const { v: grow, moving } = iSettle(S, 'g', 1, dt);
    const colors = D.colors || {};
    const mode = (P && P.mode) || 'dark';
    const n = evs.length;
    const bw = w / n;
    const tw = Math.max(1, Math.min(bw - 0.6, 6));
    const base = h * 0.34, full = h * 0.86;
    // the baseline reads as "this is a track", so a gap in it is legible as a
    // gap rather than as the end of the data
    c.fillStyle = iRgba(P.line, 0.55);
    c.fillRect(0, h / 2 - 0.5, w, 1);
    for (let i = 0; i < n; i++) {
      const e = evs[i];
      const loud = e.type === 'error' || e.type === 'compact';
      // a wipe in reading order, oldest first — the order the session ran in
      const a = iClamp(grow * n - i);
      if (a <= 0) continue;
      const th = (loud ? full : base + (e.type === 'tool' || e.type === 'spawn'
        ? h * 0.22 : 0)) * (0.35 + a * 0.65);
      // an unknown type takes the palette's own accent, never a literal: a
      // second copy of the event palette is a second thing to keep in step
      c.fillStyle = iShade(colors[e.type] || P.accent, mode);
      c.globalAlpha = loud ? 1 : 0.82;
      const x = i * bw + (bw - tw) / 2;
      c.fillRect(x, (h - th) / 2, tw, th);
    }
    c.globalAlpha = 1;
    return moving;
  },
};

window.INST = INST;
