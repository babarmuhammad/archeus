// Bottom sheet maths, pure so it can be tested: detent heights, where a drag lands, how fast the finger was moving.
// A detent is a name and a share of the space the sheet may use; heights are pixels of that space.
export const DETENTS = { peek: 0.4, half: 0.56, full: 0.92 };
export const FLICK = 0.5;          // px per ms: a faster release goes to the next detent in its direction
export const KEYBOARD_GAP = 8;     // px kept free above the keyboard or the top edge

// The detents a sheet offers, smallest first, as { name, px }. A detent never exceeds the space left above the keyboard.
export function heights(names, avail, fixed = {}) {
  const cap = Math.max(0, avail - KEYBOARD_GAP);
  let floor = 0; // a fixed detent can be taller than a share on a short viewport: a larger name is never shorter than a smaller one
  return [...names].sort((a, b) => DETENTS[a] - DETENTS[b]).map((name) => ({ name, px: (floor = Math.min(Math.max(fixed[name] ?? Math.round(DETENTS[name] * avail), floor), cap)) }));
}

// Where a drag released at `height` lands: a detent name, or 'close'. Flick (|velocity| over FLICK, up positive): the next detent that way, or close past the lowest.
// Slow release: the nearest detent, or close when below half of the lowest one. `dismissible: false` never closes.
export function snap({ height, velocity, detents, dismissible = true }) {
  const low = detents[0], flick = Math.abs(velocity) >= FLICK;
  if (flick && velocity > 0) return (detents.find((d) => d.px > height + 1) || detents[detents.length - 1]).name;
  if (flick) {
    const below = [...detents].reverse().find((d) => d.px < height - 1);
    return below ? below.name : dismissible ? 'close' : low.name;
  }
  if (dismissible && height < low.px / 2) return 'close';
  return detents.reduce((a, d) => (Math.abs(d.px - height) < Math.abs(a.px - height) ? d : a)).name;
}

// The finger's speed over the last `span` ms of pointer samples [{ t, y }], up positive (y grows downwards on screen).
export function velocity(samples, span = 100) {
  if (samples.length < 2) return 0;
  const last = samples[samples.length - 1], first = samples.find((s) => last.t - s.t <= span) || samples[0];
  return last.t === first.t ? 0 : (first.y - last.y) / (last.t - first.t);
}

// The height while a finger is down: follows it 1:1 between nothing and the tallest detent.
export const follow = (start, dy, max) => Math.min(max, Math.max(0, start - dy));

// The handle button and the arrow keys step through the detents: up goes to the next taller one, and from the tallest back to the smallest.
const order = (names) => [...names].sort((a, b) => DETENTS[a] - DETENTS[b]);
export const step = (current, names, dir = 1) => {
  const o = order(names), i = o.indexOf(current);
  return dir > 0 ? o[(i + 1) % o.length] : o[Math.max(0, i - 1)];
};
export const stepLabel = (current, names) => (current === order(names).at(-1) ? 'Collapse' : 'Expand');

// A sheet is modal (scrim, inert page, focus trap, aria-modal) always when asked to be, otherwise only at its full height.
export const isModal = (detent, modal = true) => modal || detent === 'full';
