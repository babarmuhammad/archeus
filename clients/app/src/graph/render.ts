// Drawing (p18-design-gate A3, A10): Canvas 2D, fine lines, the encoding table
// and nothing else. Level of detail: up to LOD_NODES visible nodes each is its
// shape; above, every node is a dot and dots of one colour are ONE path, so the
// work per frame grows with the number of colours, not of nodes. Edges are
// batched per style the same way. No loop here: the view's Loop calls draw().
import { colourVar, dashOf, lookOf, radiusOf, tracePath, widthOf } from './encoding.ts';
import type { Drawn, Model } from './model.ts';
import type { Point } from './layout.ts';

export const LOD_NODES = 250; // the legacy renderer's threshold (G4)
export const LABEL_ZOOM = 0.5; // below it: cluster labels only (ui-architecture §5)

export interface Camera {
  x: number;
  y: number;
  k: number;
}

export interface Scene {
  model: Model;
  keys: readonly string[]; // visible, in order
  drawn: readonly Drawn[];
  pos: ReadonlyMap<string, Point>;
  cam: Camera;
  focus: string | null;
  selected?: string | null; // a drawn edge id
  context: ReadonlySet<string> | null; // focus + context: null → nothing dimmed
  path?: ReadonlySet<string> | null; // drawn edge ids on a traced path
  live: ReadonlySet<string>; // drawn edge ids with a live execution
  liveStatic: boolean; // reduced motion: live edges drawn thicker, never pulsed
  pulse: ReadonlyMap<string, number>; // drawn edge id → 0..1 of its one pulse
  colour: (cssVar: string) => string;
  width: number;
  height: number;
  dpr: number;
}

export interface DrawStats {
  lod: 'full' | 'dots';
  paths: number; // beginPath calls: the CI proxy for work per frame
  labels: number;
  nodes: number;
}

export function draw(ctx: CanvasRenderingContext2D, s: Scene): DrawStats {
  const stats: DrawStats = { lod: s.keys.length > LOD_NODES ? 'dots' : 'full', paths: 0, labels: 0, nodes: s.keys.length };
  const bp = ctx.beginPath.bind(ctx);
  ctx.beginPath = () => {
    stats.paths++;
    bp();
  };
  try {
    ctx.setTransform(s.dpr, 0, 0, s.dpr, 0, 0);
    ctx.fillStyle = s.colour('--bg');
    ctx.fillRect(0, 0, s.width, s.height);
    ctx.setTransform(s.dpr * s.cam.k, 0, 0, s.dpr * s.cam.k, s.dpr * (s.width / 2 - s.cam.x * s.cam.k), s.dpr * (s.height / 2 - s.cam.y * s.cam.k));
    drawEdges(ctx, s);
    drawNodes(ctx, s, stats);
    drawLabels(ctx, s, stats);
  } finally {
    ctx.beginPath = bp;
  }
  return stats;
}

const dim = (s: Scene, k: string) => !!s.context && !s.context.has(k);

function drawEdges(ctx: CanvasRenderingContext2D, s: Scene) {
  const groups = new Map<string, Drawn[]>();
  for (const d of s.drawn) {
    const pa = s.pos.get(d.a);
    const pb = s.pos.get(d.b);
    if (!pa || !pb) continue;
    const faded = dim(s, d.a) || dim(s, d.b);
    const hot = d.id === s.selected || !!s.path?.has(d.id);
    const live = s.live.has(d.id);
    const key = [dashOf(d.tier).join(','), widthOf(d.count, live && s.liveStatic), faded, hot, d.inactive, d.structural].join('|');
    const g = groups.get(key);
    if (g) g.push(d);
    else groups.set(key, [d]);
  }
  for (const [key, ds] of groups) {
    const [dash, w, faded, hot, inactive, structural] = key.split('|');
    ctx.setLineDash(dash ? dash.split(',').map(Number) : []);
    ctx.lineWidth = Number(w) / s.cam.k;
    ctx.globalAlpha = faded === 'true' ? 0.25 : structural === 'true' ? 0.5 : 1;
    ctx.strokeStyle = s.colour(hot === 'true' ? '--focus' : inactive === 'true' ? '--text-3' : '--line-strong');
    ctx.beginPath();
    for (const d of ds) {
      const pa = s.pos.get(d.a)!;
      const pb = s.pos.get(d.b)!;
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
    }
    ctx.stroke();
  }
  // one opacity step per pulsed edge, drawn over the static layer (A8)
  ctx.setLineDash([]);
  for (const [id, t] of s.pulse) {
    const d = s.drawn.find((x) => x.id === id);
    const pa = d && s.pos.get(d.a);
    const pb = d && s.pos.get(d.b);
    if (!pa || !pb) continue;
    ctx.globalAlpha = Math.max(0, 1 - t);
    ctx.lineWidth = 2 / s.cam.k;
    ctx.strokeStyle = s.colour('--state-active');
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    ctx.lineTo(pb.x, pb.y);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

function drawNodes(ctx: CanvasRenderingContext2D, s: Scene, stats: DrawStats) {
  ctx.setLineDash([]);
  if (stats.lod === 'dots') {
    const byColour = new Map<string, Point[]>();
    for (const k of s.keys) {
      const n = s.model.byKey.get(k);
      const p = s.pos.get(k);
      if (!n || !p) continue;
      const c = colourVar(n.kind, n.machine, n.state) + (dim(s, k) ? '|dim' : '');
      const g = byColour.get(c);
      if (g) g.push(p);
      else byColour.set(c, [p]);
    }
    for (const [c, ps] of byColour) {
      const [cssVar, faded] = c.split('|');
      ctx.globalAlpha = faded ? 0.25 : 1;
      ctx.fillStyle = s.colour(cssVar);
      ctx.beginPath();
      const r = 2 / s.cam.k;
      for (const p of ps) {
        ctx.moveTo(p.x + r, p.y);
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      }
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    return;
  }
  for (const k of s.keys) {
    const n = s.model.byKey.get(k);
    const p = s.pos.get(k);
    if (!n || !p) continue;
    const look = lookOf(n.kind, n.endpoint, n.type);
    const col = s.colour(colourVar(n.kind, n.machine, n.state));
    ctx.globalAlpha = dim(s, k) ? 0.25 : 1;
    ctx.lineWidth = 1 / s.cam.k;
    ctx.setLineDash(look.shape === 'endpoint' ? [1.5, 3] : []);
    const { filled } = tracePath(ctx, look.shape, p.x, p.y, radiusOf(look.shape));
    if (filled) {
      ctx.fillStyle = col;
      ctx.fill();
    } else {
      ctx.strokeStyle = col;
      ctx.stroke();
    }
    if (k === s.focus) {
      ctx.setLineDash([]);
      ctx.strokeStyle = s.colour('--focus');
      ctx.lineWidth = 2 / s.cam.k;
      ctx.beginPath();
      ctx.arc(p.x, p.y, radiusOf(look.shape) + 4, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
}

function drawLabels(ctx: CanvasRenderingContext2D, s: Scene, stats: DrawStats) {
  const wanted = new Set<string>();
  for (const k of s.keys) {
    const n = s.model.byKey.get(k);
    if (!n) continue;
    const cluster = lookOf(n.kind, n.endpoint, n.type).shape === 'cluster';
    if (cluster) wanted.add(k);
    else if (s.cam.k >= LABEL_ZOOM) {
      if (k === s.focus) wanted.add(k);
      else if (stats.lod === 'full' && (!s.context || s.context.has(k))) wanted.add(k);
    }
  }
  ctx.fillStyle = s.colour('--text');
  ctx.font = `${12 / s.cam.k}px ${getFont()}`;
  ctx.textBaseline = 'middle';
  for (const k of wanted) {
    const n = s.model.byKey.get(k)!;
    const p = s.pos.get(k);
    if (!p) continue;
    ctx.globalAlpha = dim(s, k) ? 0.4 : 1;
    ctx.fillText(n.label, p.x + (radiusOf(lookOf(n.kind, n.endpoint, n.type).shape) + 4), p.y);
    stats.labels++;
  }
  ctx.globalAlpha = 1;
}

let font = '';
function getFont() {
  if (!font && typeof document !== 'undefined') font = getComputedStyle(document.documentElement).getPropertyValue('--font') || 'system-ui';
  return font || 'system-ui';
}
