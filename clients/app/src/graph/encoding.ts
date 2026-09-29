// The spatial view's encoding (p18-design-gate A3; research §26, ADR-0016):
// every visual variable is one domain fact and nothing else. This is the only
// place the renderer reads a shape, a dash or a colour role from; the parity
// test draws every row through a recording context. Pure.
import { present } from '../state/present.ts';
import { TIER_STYLE } from './relations.ts';

export type Shape =
  | 'cluster' | 'circle' | 'small-circle' | 'triangle' | 'bar' | 'square' | 'ring' | 'dot'
  | 'diamond' | 'hexagon' | 'hexagon-filled' | 'outline-diamond' | 'notched-square'
  | 'chevron' | 'brackets' | 'rounded-rect' | 'dot-in-circle' | 'tick-circle' | 'endpoint'
  | 'folder' | 'file';

export interface KindLook {
  shape: Shape;
  state: boolean; // coloured by its state (missions, tasks, executions only — P16 §20.10)
  noun: string; // what the mirror and the announcer call it
}

/** Kind → look. A kind not here is drawn as an endpoint, never guessed. */
export const ENCODING: Readonly<Record<string, KindLook>> = {
  project: { shape: 'cluster', state: false, noun: 'project' },
  mission: { shape: 'circle', state: true, noun: 'mission' },
  task: { shape: 'small-circle', state: true, noun: 'task' },
  execution: { shape: 'triangle', state: true, noun: 'execution' },
  plan: { shape: 'bar', state: false, noun: 'plan version' },
  repository: { shape: 'square', state: false, noun: 'repository' },
  session: { shape: 'ring', state: false, noun: 'session' },
  knowledge_item: { shape: 'dot', state: false, noun: 'knowledge' },
  verification: { shape: 'hexagon', state: false, noun: 'verification' },
  review: { shape: 'hexagon-filled', state: false, noun: 'review' },
  approval: { shape: 'outline-diamond', state: false, noun: 'approval' },
  policy_decision: { shape: 'notched-square', state: false, noun: 'policy decision' },
  route_decision: { shape: 'chevron', state: false, noun: 'route decision' },
  context_package: { shape: 'brackets', state: false, noun: 'context package' },
  meeting: { shape: 'rounded-rect', state: false, noun: 'meeting' },
  automation: { shape: 'dot-in-circle', state: false, noun: 'automation' },
  automation_run: { shape: 'tick-circle', state: false, noun: 'automation run' },
  // the repository import graph (A5)
  directory: { shape: 'folder', state: false, noun: 'directory' },
  file: { shape: 'file', state: false, noun: 'file' },
};

/** A DECISION-type knowledge item is the decision's record: a diamond (A3, V7). */
export function lookOf(kind: string, endpoint?: boolean, ktype?: string | null): KindLook {
  if (endpoint) return { shape: 'endpoint', state: false, noun: kind.replace(/_/g, ' ') };
  if (kind === 'knowledge_item' && ktype === 'DECISION') return { shape: 'diamond', state: false, noun: 'decision' };
  return ENCODING[kind] ?? { shape: 'endpoint', state: false, noun: kind.replace(/_/g, ' ') };
}

/** The CSS custom property a node is coloured with: a state colour only where
 * the kind carries state, `--text-2` (neutral) everywhere else, and `--text-3`
 * for a plan version no longer current (its presentation class `inactive`:
 * superseded or rejected — A3). */
export function colourVar(kind: string, machine?: string, state?: string): string {
  if (kind === 'plan' && machine && state && present(machine, state).cls === 'inactive') return '--text-3';
  const look = ENCODING[kind];
  if (!look?.state || !machine || !state) return '--text-2';
  const role = present(machine, state).role;
  return '--' + role.replace('.', '-');
}

/** Dash arrays per tier (TIER_STYLE): EXTRACTED solid, INFERRED dashed,
 * AMBIGUOUS dotted; an edge read from a column is solid. */
export const DASH: Readonly<Record<string, readonly number[]>> = { solid: [], dashed: [6, 4], dotted: [1.5, 3] };

export function dashOf(tier?: string | null): readonly number[] {
  if (!tier) return DASH.solid;
  return DASH[TIER_STYLE[tier as keyof typeof TIER_STYLE] ?? 'solid'];
}

/** Line width of a (possibly lifted) edge: 1 px, thickening with how many
 * real edges it stands for, capped at 3 px. A live edge under reduced motion
 * is drawn 2 px instead of pulsing (A8). */
export function widthOf(count: number, liveStatic = false): number {
  const w = Math.min(3, 1 + Math.log2(Math.max(1, count)));
  return liveStatic ? Math.max(2, w) : w;
}

/** Node radius in world units per shape; dots above the LOD threshold. */
export function radiusOf(shape: Shape): number {
  switch (shape) {
    case 'cluster':
      return 26;
    case 'circle':
    case 'square':
    case 'ring':
    case 'folder':
      return 10;
    case 'dot':
      return 4;
    default:
      return 7;
  }
}

/** Trace one shape as a path centred on (x, y) with radius r. The caller
 * fills or strokes; `filled` says which the encoding means. */
export function tracePath(ctx: CanvasRenderingContext2D, shape: Shape, x: number, y: number, r: number): { filled: boolean } {
  ctx.beginPath();
  const poly = (pts: [number, number][]) => {
    ctx.moveTo(x + pts[0][0] * r, y + pts[0][1] * r);
    for (const [px, py] of pts.slice(1)) ctx.lineTo(x + px * r, y + py * r);
    ctx.closePath();
  };
  const hex: [number, number][] = [0, 1, 2, 3, 4, 5].map((i) => [Math.cos((Math.PI / 3) * i), Math.sin((Math.PI / 3) * i)]);
  switch (shape) {
    case 'cluster':
    case 'ring':
    case 'endpoint':
      ctx.arc(x, y, r, 0, Math.PI * 2);
      return { filled: false };
    case 'circle':
    case 'small-circle':
    case 'dot':
      ctx.arc(x, y, r, 0, Math.PI * 2);
      return { filled: true };
    case 'triangle':
      poly([[0, -1], [0.9, 0.7], [-0.9, 0.7]]);
      return { filled: true };
    case 'bar':
      ctx.rect(x - r, y - r * 0.35, r * 2, r * 0.7);
      return { filled: false };
    case 'square':
      ctx.rect(x - r * 0.8, y - r * 0.8, r * 1.6, r * 1.6);
      return { filled: true };
    case 'diamond':
      poly([[0, -1], [1, 0], [0, 1], [-1, 0]]);
      return { filled: true };
    case 'outline-diamond':
      poly([[0, -1], [1, 0], [0, 1], [-1, 0]]);
      return { filled: false };
    case 'hexagon':
      poly(hex);
      return { filled: false };
    case 'hexagon-filled':
      poly(hex);
      return { filled: true };
    case 'notched-square':
      poly([[-0.8, -0.8], [0.3, -0.8], [0.8, -0.3], [0.8, 0.8], [-0.8, 0.8]]);
      return { filled: false };
    case 'chevron':
      poly([[-0.8, -0.8], [0.2, -0.8], [0.9, 0], [0.2, 0.8], [-0.8, 0.8], [-0.1, 0]]);
      return { filled: false };
    case 'brackets':
      ctx.moveTo(x - r * 0.3, y - r);
      ctx.lineTo(x - r, y - r);
      ctx.lineTo(x - r, y + r);
      ctx.lineTo(x - r * 0.3, y + r);
      ctx.moveTo(x + r * 0.3, y - r);
      ctx.lineTo(x + r, y - r);
      ctx.lineTo(x + r, y + r);
      ctx.lineTo(x + r * 0.3, y + r);
      return { filled: false };
    case 'rounded-rect':
      ctx.roundRect(x - r, y - r * 0.6, r * 2, r * 1.2, r * 0.4);
      return { filled: false };
    case 'dot-in-circle':
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.moveTo(x + r * 0.3, y);
      ctx.arc(x, y, r * 0.3, 0, Math.PI * 2);
      return { filled: false };
    case 'tick-circle':
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.moveTo(x - r * 0.45, y);
      ctx.lineTo(x - r * 0.1, y + r * 0.35);
      ctx.lineTo(x + r * 0.5, y - r * 0.35);
      return { filled: false };
    case 'folder':
      poly([[-1, -0.7], [-0.3, -0.7], [-0.1, -0.45], [1, -0.45], [1, 0.75], [-1, 0.75]]);
      return { filled: false };
    case 'file':
      poly([[-0.7, -1], [0.35, -1], [0.7, -0.65], [0.7, 1], [-0.7, 1]]);
      return { filled: false };
  }
}
