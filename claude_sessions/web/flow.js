/* The session flow page. Loaded only by flowgraph.render_flow_html, which
   inlines this file — it is not part of the SPA bundle and nothing here may
   assume MO, INST, STAGE or the palette vars exist.

   Two clocks, which is the whole design:

     * CONTENT time — `e.t`, the transcript's own timestamps. It decides what is
       true at a point in the session.
     * PRESENTATION time — the playhead. It runs along a CLAMPED axis (`AX`), so
       a session that sat idle for two hours does not spend two hours of pixels
       on nothing, and playback moves at whatever multiple of it you pick.

   The canvas draws; the DOM carries the controls and the inspector. A session
   reaches thousands of events and one <div> per event would not survive a
   scrub, but canvas text ignores the font stack, so the inspector is DOM. */

const $ = s => document.querySelector(s);
const cv = $('#c'), cx = cv.getContext('2d');

/* Layout constants. GAP is the one that matters: the longest stretch of idle
   the axis will pay pixels for. STEP keeps two events that share a timestamp
   from landing on the same x. */
const GAP = 8, STEP = 0.35, PAD = 28, TOP = 56, ROW = 110;

let EVS = FLOW.slice(), AX = [], TOTAL = 1, LANES = 1;
let cur = 0, playing = false, z = 1, panX = 0, sel = null, off = META.offset || 0;
let W = 0, H = 0, raf = null, poll = null, lastAt = 0;

const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ── the axis ─────────────────────────────────────────────────────────────
   Cumulative, with every gap clamped. Rebuilt whenever a poll appends, which
   is cheap and is the only thing that can change it. */
function axis() {
  AX = new Array(EVS.length);
  let acc = 0, prev = null;
  for (let i = 0; i < EVS.length; i++) {
    const t = EVS[i].t || prev;
    if (prev !== null && t !== null) acc += Math.min(Math.max(t - prev, 0), GAP);
    acc += STEP;
    AX[i] = acc;
    if (t !== null) prev = t;
  }
  TOTAL = Math.max(acc, 1);
  LANES = 1;
  for (const e of EVS) LANES = Math.max(LANES, (e.lane || 0) + 1);
}

const pxPer = () => (W - PAD * 2) / TOTAL * z;
const sx = i => PAD + AX[i] * pxPer() - panX;

/* A session with no subagents is ONE lane, and a single row of dots down the
   middle of an empty page is a barcode, not a graph. So a lane is a SPINE with
   the call above it and the result below: the pairing becomes the shape of the
   thing, and the vertical space is carrying information instead of being
   whitespace. Lanes are centred for the same reason. */
const TIER = { tool: -34, spawn: -34, result: 34, error: 34 };
const laneTop = () => Math.max(TOP, (H - (LANES - 1) * ROW) / 2);
const sy = e => laneTop() + (e.lane || 0) * ROW + (TIER[e.type] || 0);

function clampPan() {
  const span = TOTAL * pxPer() + PAD * 2;
  panX = Math.max(0, Math.min(panX, Math.max(0, span - W)));
}

/* ── drawing ──────────────────────────────────────────────────────────── */
function size() {
  const r = cv.getBoundingClientRect();
  // DPR clamped at 2: this draws 1px lines and small arcs, which alias badly
  // at 1x and cost four times the fill at 3x for nothing anyone can see.
  const d = Math.min(devicePixelRatio || 1, 2);
  W = r.width; H = r.height;
  cv.width = Math.round(W * d); cv.height = Math.round(H * d);
  cx.setTransform(d, 0, 0, d, 0, 0);
  draw();
}

const LABEL = {
  tool: e => e.name, spawn: e => e.name || 'subagent', model: e => e.name,
  prompt: e => (e.text || 'prompt'), error: () => 'error', compact: () => 'compacted',
};

function radius(e) { return e.type === 'prompt' ? 7 : e.type === 'spawn' ? 7 : 5; }

function draw() {
  cx.clearRect(0, 0, W, H);
  if (!EVS.length) {
    cx.fillStyle = '#585b70'; cx.font = '13px system-ui';
    cx.fillText('This session recorded no events archeus can read.', PAD, TOP);
    return;
  }
  const head = PAD + cur * pxPer() - panX;

  // lane rails first, so nothing is drawn on top of a node
  cx.strokeStyle = '#1e2230'; cx.lineWidth = 1;
  for (let l = 0; l < LANES; l++) {
    const y = laneTop() + l * ROW + .5;
    cx.beginPath(); cx.moveTo(0, y); cx.lineTo(W, y); cx.stroke();
  }

  // every prompt is where the session changed direction — the one landmark
  // worth a full-height rule, and what makes scrubbing navigable
  for (let i = 0; i < EVS.length; i++) {
    if (EVS[i].type !== 'prompt') continue;
    const x = sx(i);
    if (x < -2 || x > W + 2) continue;
    cx.strokeStyle = '#2b3550';
    cx.beginPath(); cx.moveTo(x + .5, 0); cx.lineTo(x + .5, H); cx.stroke();
    cx.fillStyle = '#6c7086'; cx.font = '11px system-ui';
    cx.fillText((EVS[i].text || '').slice(0, 60), x + 6, H - 10);
  }

  // edges: along a lane, and from a tool call to the result that closed it
  const lastIn = {};
  cx.lineWidth = 1;
  for (let i = 0; i < EVS.length; i++) {
    const e = EVS[i], x = sx(i), y = sy(e);
    if (x < -40 || x > W + 40) { lastIn[e.lane || 0] = i; continue; }
    const p = lastIn[e.lane || 0];
    cx.globalAlpha = AX[i] <= cur ? .55 : .16;
    if (p !== undefined) {
      cx.strokeStyle = '#313547';
      cx.beginPath(); cx.moveTo(sx(p), sy(EVS[p])); cx.lineTo(x, y); cx.stroke();
    }
    if (e.ref) {
      // call to result: a straight line between two tiers, so its SLOPE is how
      // long the tool took. A slow call leans; an instant one is vertical.
      const j = i - e.ref;
      if (j >= 0) {
        cx.strokeStyle = COLORS.tool;
        cx.lineWidth = e.dur > 2 ? 2 : 1;
        cx.beginPath(); cx.moveTo(sx(j), sy(EVS[j])); cx.lineTo(x, y); cx.stroke();
        cx.lineWidth = 1;
      }
    }
    lastIn[e.lane || 0] = i;
  }

  // nodes
  const lastLab = {};
  for (let i = 0; i < EVS.length; i++) {
    const e = EVS[i], x = sx(i);
    if (x < -20 || x > W + 20) continue;
    const y = sy(e), c = COLORS[e.type] || '#cdd6f4', on = AX[i] <= cur;
    cx.globalAlpha = on ? 1 : .22;
    cx.fillStyle = c;
    cx.beginPath(); cx.arc(x, y, radius(e), 0, 6.2832); cx.fill();
    if (sel === i) {
      cx.strokeStyle = '#ffffff'; cx.lineWidth = 2;
      cx.beginPath(); cx.arc(x, y, radius(e) + 4, 0, 6.2832); cx.stroke();
    }
    // A name per node is a smear at any zoom a long session opens at, and no
    // name at all is a field of anonymous dots. So: one label per tier per 76px,
    // which stays readable while zoomed out and fills in as you zoom.
    // An assistant node's name is its MODEL, which the header already carries
    // once — labelling every one of them printed `claude-opus-5` across the
    // whole spine and said nothing. A result is named by the call above it.
    const key = TIER[e.type] || 0, lab = LABEL[e.type] ? LABEL[e.type](e) : '';
    if (lab && x - (lastLab[key] || -1e9) > 76) {
      lastLab[key] = x;
      cx.globalAlpha = on ? .8 : .18;
      cx.fillStyle = '#a6adc8'; cx.font = '11px Consolas,ui-monospace,monospace';
      cx.fillText(lab.slice(0, 18), x + 9, y - 9);
    }
  }
  cx.globalAlpha = 1;

  // playhead
  cx.strokeStyle = '#7dcfff'; cx.lineWidth = 1;
  cx.beginPath(); cx.moveTo(head + .5, 0); cx.lineTo(head + .5, H); cx.stroke();
}

/* ── the loop, which parks ────────────────────────────────────────────────
   Registered only while playing, and never rescheduled while the document is
   hidden. Nothing animates at all under prefers-reduced-motion. */
function tick(now) {
  raf = null;
  if (!playing || document.hidden || REDUCED) return;
  const dt = lastAt ? Math.min((now - lastAt) / 1000, .25) : 0;
  lastAt = now;
  cur += dt * speedNow();
  if (cur >= TOTAL) { cur = TOTAL; stop(); }
  keepInView(); syncScrub(); draw();
  if (playing) raf = requestAnimationFrame(tick);
}
function speedNow() { return +$('#speed').value || TOTAL; }
/* The playhead is the thing being watched, so the view follows it — but only
   once it is actually leaving, or every frame would be a pan and reading the
   graph while it plays would be impossible. */
function keepInView() {
  const head = PAD + cur * pxPer() - panX;
  if (head > W * .82 || head < W * .12) {
    panX = PAD + cur * pxPer() - W * .3; clampPan();
  }
}
function start() {
  if (REDUCED) { cur = TOTAL; syncScrub(); draw(); return; }
  // the page opens with the whole session shown, so play means REPLAY — without
  // this it stopped on the frame it started on and looked broken
  if (cur >= TOTAL - .01) cur = 0;
  playing = true; lastAt = 0; setTxt($('#play'), '❚❚');
  if (!raf) raf = requestAnimationFrame(tick);
}
function stop() { playing = false; setTxt($('#play'), '▶'); }
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { lastAt = 0; return; }
  if (playing && !raf) raf = requestAnimationFrame(tick);
});
addEventListener('blur', () => { lastAt = 0; });

/* ── DOM, written only when it changed ────────────────────────────────────
   This page polls once a second; an unconditional textContent= on every tick
   destroys and recreates the node and reflows the bar for nothing. */
function setTxt(el, s) { if (el && el.__v !== s) { el.__v = s; el.textContent = s; } }
function setHtml(el, s) { if (el && el.__h !== s) { el.__h = s; el.innerHTML = s; } }

function syncScrub() {
  const v = Math.round(cur / TOTAL * 1000);
  if (+$('#scrub').value !== v) $('#scrub').value = v;
  const at = atTime();
  setTxt($('#clock'), at ? fmtClock(at) + '  ·  ' + fmtDur(at - META.first) : '');
}
function atTime() {
  let t = 0;
  for (let i = 0; i < EVS.length && AX[i] <= cur; i++) if (EVS[i].t) t = EVS[i].t;
  return t || META.first || 0;
}
const p2 = n => String(n).padStart(2, '0');
function fmtClock(t) {
  const d = new Date(t * 1000);
  return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate())
    + ' ' + p2(d.getHours()) + ':' + p2(d.getMinutes()) + ':' + p2(d.getSeconds());
}
function fmtDur(s) {
  if (s > 0 && s < 1) return Math.round(s * 1000) + 'ms';
  s = Math.max(0, Math.round(s));
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s / 60) + 'm ' + p2(s % 60) + 's';
  return Math.floor(s / 3600) + 'h ' + p2(Math.floor(s % 3600 / 60)) + 'm';
}
const esc = s => String(s == null ? '' : s).replace(/[&<>]/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

/* The result that closed the call at `i`, if it is in the window a tool result
   can plausibly be — bounded, so a call that never returned costs a short scan
   rather than the length of the session. */
function closedBy(i) {
  for (let j = i + 1; j < Math.min(EVS.length, i + 400); j++)
    if (EVS[j].ref && j - EVS[j].ref === i) return EVS[j];
  return null;
}

function inspect(i) {
  sel = i;
  if (i == null) { setHtml($('#sidebody'), '<div class="empty">Click a node to inspect it.</div>'); draw(); return; }
  const e = EVS[i], rows = [];
  const add = (k, v) => { if (v || v === 0) rows.push('<div class="k">' + esc(k) + '</div><div>' + esc(v) + '</div>'); };
  add('when', e.t ? fmtClock(e.t) : 'no timestamp');
  add('since start', e.t && META.first ? fmtDur(e.t - META.first) : '');
  add('lane', e.lane ? 'sidechain ' + e.lane : 'main');
  // a CALL does not know its own duration — the result that closed it does, so
  // a call is asked about by looking forward for whatever points back at it
  const dur = e.dur || (closedBy(i) || {}).dur;
  if (dur) add('took', fmtDur(dur));
  add('target', e.target);
  if (e.tok_in || e.tok_out) add('tokens', (e.tok_in || 0) + ' in · ' + (e.tok_out || 0) + ' out');
  setHtml($('#sidebody'),
    '<h4>' + esc(e.name || e.type) + '</h4>'
    + '<span class="tag" style="color:' + esc(COLORS[e.type] || '#cdd6f4') + '">' + esc(e.type) + '</span>'
    + rows.join('')
    + (e.text ? '<div class="k">text</div><pre>' + esc(e.text) + '</pre>' : ''));
  draw();
}

/* ── pointer: click a node, drag to pan, wheel to zoom ──────────────────── */
let down = null;
cv.addEventListener('pointerdown', ev => {
  down = { x: ev.clientX, pan: panX, moved: false };
  cv.setPointerCapture(ev.pointerId); cv.classList.add('drag');
});
cv.addEventListener('pointermove', ev => {
  if (!down) return;
  const d = ev.clientX - down.x;
  if (Math.abs(d) > 3) down.moved = true;
  panX = down.pan - d; clampPan(); draw();
});
cv.addEventListener('pointerup', ev => {
  cv.classList.remove('drag');
  if (down && !down.moved) inspect(hit(ev));
  down = null;
});
function hit(ev) {
  const r = cv.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  let best = null, bd = 14 * 14;
  for (let i = 0; i < EVS.length; i++) {
    const dx = sx(i) - mx, dy = sy(EVS[i]) - my, d = dx * dx + dy * dy;
    if (d < bd) { bd = d; best = i; }
  }
  return best;
}
cv.addEventListener('wheel', ev => {
  ev.preventDefault();
  const r = cv.getBoundingClientRect(), mx = ev.clientX - r.left;
  const before = (mx + panX - PAD) / pxPer();
  z = Math.max(1, Math.min(z * (ev.deltaY < 0 ? 1.25 : .8), 400));
  panX = before * pxPer() + PAD - mx; clampPan(); draw();
}, { passive: false });

/* ── controls ─────────────────────────────────────────────────────────── */
$('#play').addEventListener('click', () => playing ? stop() : start());
$('#scrub').addEventListener('input', () => {
  cur = +$('#scrub').value / 1000 * TOTAL; keepInView(); syncScrub(); draw();
});
addEventListener('keydown', ev => {
  if (ev.key === ' ') { ev.preventDefault(); playing ? stop() : start(); }
  if (ev.key === 'Escape') inspect(null);
});
addEventListener('resize', size);

/* ── follow ───────────────────────────────────────────────────────────────
   The page was served from the URL it polls, so the token it needs is already
   in its own address bar — there is nothing to pass and nothing to store. */
$('#follow').addEventListener('change', () => {
  clearInterval(poll); poll = null;
  if ($('#follow').checked) poll = setInterval(tail, 1000);
  header();
});
async function tail() {
  if (document.hidden) return;
  try {
    const r = await fetch(location.pathname + location.search + '&since=' + off,
      { headers: { 'Accept': 'application/json' } });
    if (!r.ok) return;
    const d = await r.json();
    if (!d.events || !d.events.length) return;
    const atEnd = cur >= TOTAL - .5;
    EVS = EVS.concat(d.events); off = d.offset || off;
    axis(); clampPan();
    if (atEnd) { cur = TOTAL; keepInView(); }
    syncScrub(); header(); draw();
  } catch (e) { /* a poll that fails is a poll that retries in a second */ }
}

function header() {
  setHtml($('#meta'),
    ($('#follow').checked ? '<span class="live"></span>' : '')
    + esc(META.harness) + ' · ' + EVS.length + ' events'
    + (META.models.length ? ' · ' + esc(META.models.join(', ')) : '')
    + (META.capped ? ' · showing the first ' + EVS.length : ''));
}

/* Opening zoomed all the way OUT is the one thing that cannot work: a session is
   thousands of events, and the whole of it across one screen is a barcode with
   every label on top of the next. So the page opens at the END, at a zoom where
   a node has room for its own name, and the scrub bar is how you get back. */
function fit() {
  z = Math.max(1, EVS.length / 150);
  panX = Infinity; clampPan();
}

if (!POLL) $('#folbox').style.display = 'none';
if (REDUCED) { $('#play').disabled = true; $('#play').title = 'Playback is off: this system asks for reduced motion'; }
axis();
cur = TOTAL;
header();
size();
fit();
draw();
syncScrub();
