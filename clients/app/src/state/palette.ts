// The command palette (rulebook §18; D-12, §46.1): go to a destination or an
// object, or act on a mission by the same Core verbs as its buttons, each
// action saying its effect first. Search is over what this client has already
// read (cache-only — server search is P21's); nothing here decides whether an
// action is allowed: the state table says what may be offered, Core judges it.
import { href, objectHref } from '../nav/destinations.ts';
import { offers } from './present.ts';

export interface PaletteMission {
  id: string;
  title: string;
  state: string;
  version: number;
}

export interface PaletteInput {
  destinations: { id: string; label: string; to: string }[];
  missions: PaletteMission[];
  projects: { id: string; name: string }[];
  knowledge: { id: string; title?: string | null }[];
  live: { mission_id: string }[]; // Core's live work (/v1/status)
}

export type Hit =
  | { key: string; label: string; go: string }
  | { key: string; label: string; act: 'pause' | 'resume'; mission: PaletteMission; effect: string };

export const PALETTE_SHOWN = 8;

const q = (s: string) => `“${s}”`;

/** What pausing or resuming a mission does, from Core's live work. */
export function effectOf(act: 'pause' | 'resume', m: PaletteMission, live: { mission_id: string }[]): string {
  if (act === 'resume') return 'its work is dispatched again';
  const n = live.filter((x) => x.mission_id === m.id).length;
  return n ? `${n} running ${n === 1 ? 'attempt pauses' : 'attempts pause'}` : 'nothing of it is running now';
}

/** Every hit for *needle*, the first PALETTE_SHOWN of them: destinations,
 * missions and their actions, projects and their graphs, knowledge — all from
 * reads this client holds. */
export function paletteHits(x: PaletteInput, needle: string): Hit[] {
  const n = needle.trim().toLowerCase();
  const out: Hit[] = x.destinations.map((d) => ({ key: 'dest:' + d.id, label: `Go to ${d.label}`, go: d.to }));
  for (const m of x.missions) {
    out.push({ key: 'msn:' + m.id, label: `Mission: ${m.title}`, go: objectHref('mission', m.id) });
    if (offers('mission', m.state, 'pause'))
      out.push({ key: 'pause:' + m.id, label: `Pause ${q(m.title)}`, act: 'pause', mission: m, effect: effectOf('pause', m, x.live) });
    if (offers('mission', m.state, 'resume', 'unblock'))
      out.push({ key: 'resume:' + m.id, label: `Resume ${q(m.title)}`, act: 'resume', mission: m, effect: effectOf('resume', m, x.live) });
  }
  for (const p of x.projects) {
    out.push({ key: 'prj:' + p.id, label: `Project: ${p.name}`, go: href({ view: 'world', project: p.id }) });
    out.push({ key: 'graph:' + p.id, label: `Open ${q(p.name)} as a graph`, go: href({ view: 'world', graph: { kind: 'project', id: p.id } }) });
  }
  for (const k of x.knowledge) if (k.title) out.push({ key: 'k:' + k.id, label: `Knowledge: ${k.title}`, go: objectHref('knowledge_item', k.id) });
  return out.filter((h) => !n || h.label.toLowerCase().includes(n)).slice(0, PALETTE_SHOWN);
}

/** The next active option for ↑/↓, or null for any other key (Home, End
 * and the rest stay the text field's). */
export function moveActive(i: number, count: number, key: string): number | null {
  if (!count) return null;
  switch (key) {
    case 'ArrowDown':
      return (i + 1) % count;
    case 'ArrowUp':
      return (i - 1 + count) % count;
    default:
      return null;
  }
}

/** A tap at (x, y) on the dialog element itself falls on its backdrop when it
 * is outside the dialog's box (p20-design-gate D5): a tap on the dialog's own
 * padding is inside and closes nothing. */
export function onBackdrop(box: { left: number; right: number; top: number; bottom: number }, x: number, y: number): boolean {
  return x < box.left || x > box.right || y < box.top || y > box.bottom;
}
