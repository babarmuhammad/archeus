// The pure half of the motion layer (js/motion.js): what moved, what is new, what left, which way a route change travels, which duration class a beat belongs to,
// and which ambient motion may run in a given moment. No DOM here, so node can test it. Rects are { left, top, right, bottom } in viewport pixels; a snapshot is a Map of key to { rect, sig }.

// Duration classes (SPEC C02, A55 section 1). css/tokens.css carries the same numbers as --dur-<class>; test/motion-classes.test.mjs holds the two together.
// A class is a name for a number, never a new number: a beat uses a class, and a duration that fits none is an amendment.
export const CLASSES = Object.freeze({
  instant: Object.freeze({ ms: 0 }),
  quick: Object.freeze({ ms: 160 }),
  standard: Object.freeze({ ms: 240 }),
  layer: Object.freeze({ ms: 200, max: 280 }),
  travel: Object.freeze({ ms: 600 }),
  orbit: Object.freeze({ ms: 900 }),
  breath: Object.freeze({ ms: 6000 })
});
// The one documented duration that is no class: hover in, exits, popovers and the route out (--dur-out). A quick beat cut short, owner "subtle and fast" (C12).
export const OUT = 100;

export const classOf = (ms) => {
  if (ms === OUT) return 'out';
  for (const [name, c] of Object.entries(CLASSES)) if (ms === c.ms || (c.max && ms > c.ms && ms <= c.max)) return name;
  return null;
};

// Ambient motion (SPEC Q03, C03): the only things that may loop. Every cycle is 3.6 s or longer; the numbers are the css and the map's own.
export const AMBIENT = Object.freeze({
  breath: Object.freeze({ min: CLASSES.breath.ms, max: CLASSES.breath.ms }),
  drift: Object.freeze({ min: 9000, max: 17000 }),
  ring: Object.freeze({ min: 3600, max: 3600 }),
  travel: Object.freeze({ min: 3700, max: 7000 })
});

// Still moments (SPEC C06, A55 section 2): what must not move, written as data. `moves` lists the one thing a moment may animate (nothing for most),
// `pause` the ambient motion that stops while the moment holds, `rule` says it in words.
export const MOMENTS = Object.freeze({
  arriving: { moves: ['fade'], pause: [], rule: 'A row Core made arrives with one quick fade and a short rise, never replayed by a re-read; the text says what changed.' },
  disappearing: { moves: ['fade'], pause: [], rule: 'A row that left the read leaves with one out fade.' },
  thinking: { moves: [], pause: [], rule: 'A static figure and specific text: no spinner, no loop.' },
  failing: { moves: ['cross-fade'], pause: [], rule: 'The quick state cross-fade only: no shake, no pulse, no toast; the reason stays inline.' },
  quiet: { moves: [], pause: ['breath', 'travel'], rule: 'Silence is text with its age; nothing moves to say work is flowing.' },
  reconnecting: { moves: [], pause: ['breath', 'drift', 'ring', 'travel'], rule: 'Banner text and a hollow presence node; a stale read never looks alive.' },
  scrolling: { moves: [], pause: [], rule: 'Scrolling, hover on a row, selection and focus are instant: no smooth scroll.' }
});

// Which ambient motion runs now. Quiet (the Reduced setting or the OS preference, `full` false), a hidden tab and the emergency stop switch all of it off;
// `playing` is the live simulation (drift, ring, travel), `live` a fresh read showing running work (the core breath); a held moment pauses what it lists.
export function ambient({ full = true, visible = true, playing = false, stopped = false, live = false, moments = [] } = {}) {
  const held = new Set(moments.flatMap((m) => (MOMENTS[m] ? MOMENTS[m].pause : [])));
  const go = full && visible && !stopped;
  const can = (kind, ok) => go && ok && !held.has(kind);
  return { breath: can('breath', live), drift: can('drift', playing), ring: can('ring', playing), travel: can('travel', playing) };
}

// The rail order is the route order: a route to the right in this list is "forward" and arrives from the right.
export const ORDER = ['now', 'work', 'replay', 'chat', 'security', 'health', 'usage', 'accounts', 'extensions', 'projects', 'settings', 'terminal'];

export const direction = (from, to) => (ORDER.indexOf(to) >= ORDER.indexOf(from) ? 1 : -1);

// Four steps at most, 40 ms apart: the page head, then the first blocks of content.
export const staggerDelay = (i, step = 40, max = 4) => Math.min(i, max - 1) * step;

// The offset that puts an element back where it was (First minus Last), or null when it moved less than `min` px.
export function delta(first, last, min = 1) {
  const dx = first.left - last.left, dy = first.top - last.top;
  return Math.abs(dx) < min && Math.abs(dy) < min ? null : { dx, dy };
}

const inView = (r, view) => !view || (r.bottom > view.top && r.top < view.bottom && r.right > view.left && r.left < view.right);

// What to animate after a re-render, from the rows before and after. Caps keep a 100 project page from starting hundreds of animations,
// and anything fully outside the window on both ends is skipped.
export function plan(prev, next, { min = 1, maxMove = 120, maxEnter = 24, maxLeave = 8, view = null } = {}) {
  const ops = [];
  let moves = 0, enters = 0, leaves = 0;
  for (const [key, n] of next) {
    const p = prev.get(key);
    if (!p) { if (enters++ < maxEnter && inView(n.rect, view)) ops.push({ key, op: 'enter' }); continue; }
    const d = delta(p.rect, n.rect, min);
    if (d && moves < maxMove && (inView(p.rect, view) || inView(n.rect, view))) { ops.push({ key, op: 'move', dx: d.dx, dy: d.dy }); moves++; }
    if (p.sig !== n.sig && inView(n.rect, view)) ops.push({ key, op: 'tint' });
  }
  for (const [key, p] of prev) if (!next.has(key) && leaves < maxLeave && inView(p.rect, view)) { ops.push({ key, op: 'leave' }); leaves++; }
  return ops;
}

// The key of a row: an explicit data-mk wins, then the row's own data-key, then the data-key of a control inside it.
export function keyOf(el) {
  const d = el.dataset || {};
  if (d.mk) return d.mk;
  if (d.key) return d.key;
  if (d.proj) return 'proj:' + d.proj;
  const inner = el.querySelector && el.querySelector('[data-key]');
  return inner ? inner.dataset.key : null;
}

// The two numbers differ as text: a counter that should tick.
export const ticks = (before, after) => before != null && after != null && before !== after;
