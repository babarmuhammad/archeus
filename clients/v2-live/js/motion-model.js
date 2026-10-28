// The pure half of the motion layer (js/motion.js): what moved, what is new, what left, which way a route change travels.
// No DOM here, so node can test it. Rects are { left, top, right, bottom } in viewport pixels; a snapshot is a Map of key to { rect, sig }.

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
