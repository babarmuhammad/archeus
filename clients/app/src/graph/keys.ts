// Keyboard traversal (p18-design-gate A11; p16 §20.11): keyboard equals
// pointer. ↑/↓ select the previous/next edge of the focused node in the drawn
// order, → crosses the selected edge, ← steps back along the way it came,
// Home returns to the query's focus. Enter, Space, +/-, 0, /, p and . are commands
// the view carries out. Pure: the view keeps the state, this decides the next.
import { around, type Drawn } from './model.ts';

export interface Walk {
  at: string; // the focused node
  sel: number; // index into around(at)
  trail: string[]; // the nodes crossed from, most recent last
}

export type Command = 'open' | 'toggle' | 'zoom-in' | 'zoom-out' | 'fit' | 'search' | 'clear' | 'path-mark' | 'pin' | null;

export function start(root: string): Walk {
  return { at: root, sel: 0, trail: [] };
}

export function step(w: Walk, key: string, drawn: readonly Drawn[], root: string): { walk: Walk; command: Command } {
  const edges = around(drawn, w.at);
  const n = edges.length;
  switch (key) {
    case 'ArrowDown':
      return { walk: { ...w, sel: n ? (w.sel + 1) % n : 0 }, command: null };
    case 'ArrowUp':
      return { walk: { ...w, sel: n ? (w.sel - 1 + n) % n : 0 }, command: null };
    case 'ArrowRight': {
      const e = edges[w.sel];
      if (!e) return { walk: w, command: null };
      return { walk: { at: e.other, sel: 0, trail: [...w.trail, w.at] }, command: null };
    }
    case 'ArrowLeft': {
      if (!w.trail.length) return { walk: w, command: null };
      const back = w.trail[w.trail.length - 1];
      const i = around(drawn, back).findIndex((x) => x.other === w.at);
      return { walk: { at: back, sel: Math.max(0, i), trail: w.trail.slice(0, -1) }, command: null };
    }
    case 'Home':
      return { walk: start(root), command: null };
    case 'Enter':
      return { walk: w, command: 'open' };
    case ' ':
      return { walk: w, command: 'toggle' };
    case '+':
    case '=':
      return { walk: w, command: 'zoom-in' };
    case '-':
      return { walk: w, command: 'zoom-out' };
    case '0':
      return { walk: w, command: 'fit' };
    case '/':
      return { walk: w, command: 'search' };
    case 'Escape':
      return { walk: w, command: 'clear' };
    case 'p':
      return { walk: w, command: 'path-mark' };
    case '.':
      return { walk: w, command: 'pin' };
    default:
      return { walk: w, command: null };
  }
}

/** The selected edge of the walk, if any. */
export function selected(w: Walk, drawn: readonly Drawn[]): { edge: Drawn; other: string } | null {
  return around(drawn, w.at)[w.sel] ?? null;
}
