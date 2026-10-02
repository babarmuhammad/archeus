// Drawing (p18-design-gate A3, A10): Canvas 2D, fine lines, the encoding table
// and nothing else. Level of detail: up to LOD_NODES visible nodes each is its
// shape; above, every node is a dot and dots of one colour are ONE path, so the
// work per frame grows with the number of colours, not of nodes. Edges are
// batched per style the same way. No loop here: the view's Loop calls frame().
//
// Two layers (A10 proxy 5): everything but the pulses is drawn once into a
// cached STATIC layer, redrawn only when something it shows changed; a frame
// in which only a pulse moved copies that layer and strokes the pulsed edges
// over it, so its work is one copy plus one path per pulse, whatever the
// number of nodes. The activity halo is part of the static layer: a node with
// live work costs no frame for having it. Travelling markers are drawn over
// the layer like pulses: two paths per frame, whatever the number of markers.
import { ALPHA } from '../state/tokens.ts';
import { attrsText, colourVar, countsText, dashOf, lookOf, radiusOf, tracePath, widthOf } from './encoding.ts';
import { ancestors, travelOf, type Drawn, type Model } from './model.ts';
import type { Point } from './layout.ts';
import type { LegendRow } from './legend.ts';

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
  focus: string | null; // the walk's current node: the keyboard or pointer selection
  root?: string | null; // the query's focus: labelled whatever the walk does (A10)
  hover?: string | null; // the node under a mouse (A10)
  selected?: string | null; // a drawn edge id
  context: ReadonlySet<string> | null; // focus + context: the nodes labelled with the focus
  depth?: ReadonlyMap<string, number> | null; // node key → its depth alpha (model.depthAlphas); absent → 1
  path?: ReadonlySet<string> | null; // drawn edge ids on a traced path
  live: ReadonlySet<string>; // drawn edge ids with a live execution
  liveStatic: boolean; // reduced motion: live edges drawn thicker, never pulsed
  pulse: ReadonlyMap<string, number>; // drawn edge id → 0..1 of its one pulse
  marker?: ReadonlyMap<string, number>; // markerTarget → 0..1 of its travel
  halo: ReadonlySet<string>; // node keys with live work (model.haloed): a static ring each
  opaque?: boolean; // forced colours or reduced transparency: every alpha token opaque (ADR-0028 §3)
  degraded?: boolean; // frames run slow (Loop.degraded): no pulse, the focus's label only
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
  hulls: number; // project volumes drawn
}

/** The whole picture on one context: the static layer, then the pulses. */
export function draw(ctx: CanvasRenderingContext2D, s: Scene): DrawStats {
  return counted(ctx, s, (stats) => {
    paintStatic(ctx, s, stats);
    drawPulses(ctx, s);
    drawMarkers(ctx, s);
  });
}

/** The cached static layer: an offscreen context the size of the canvas, and
 * what it was last drawn from. */
export interface Layer {
  ctx: CanvasRenderingContext2D;
  sig: readonly unknown[] | null;
}

/** What the static layer shows: when none of it changed, the layer is reused.
 * The pulse map is deliberately not in it. */
export function staticSig(s: Scene): unknown[] {
  return [s.model, s.keys, s.drawn, s.pos, s.cam.x, s.cam.y, s.cam.k, s.focus, s.root ?? null, s.hover ?? null, s.selected ?? null, s.context, s.path ?? null, s.live, s.liveStatic, s.halo, !!s.opaque, s.depth ?? null, !!s.degraded, s.width, s.height, s.dpr, s.colour('--bg'), s.colour('--text')];
}

/** One frame of the view: redraw the static layer only if it changed, copy it,
 * stroke the pulses over it. `paths` counts the work on the visible canvas;
 * `layer` says whether the static layer was redrawn (its own work then
 * counted in `layerPaths`). */
export function frame(ctx: CanvasRenderingContext2D, layer: Layer, s: Scene): DrawStats & { layer: boolean; layerPaths: number } {
  const sig = staticSig(s);
  const stale = !layer.sig || sig.length !== layer.sig.length || sig.some((v, i) => v !== layer.sig![i]);
  let under: DrawStats | null = null;
  if (stale) {
    under = counted(layer.ctx, s, (stats) => paintStatic(layer.ctx, s, stats));
    layer.sig = sig;
  }
  const top = counted(ctx, s, () => {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(layer.ctx.canvas, 0, 0);
    drawPulses(ctx, s);
    drawMarkers(ctx, s);
  });
  return { ...top, labels: under?.labels ?? 0, hulls: under?.hulls ?? 0, layer: stale, layerPaths: under?.paths ?? 0 };
}

function counted(ctx: CanvasRenderingContext2D, s: Scene, body: (stats: DrawStats) => void): DrawStats {
  const stats: DrawStats = { lod: s.keys.length > LOD_NODES ? 'dots' : 'full', paths: 0, labels: 0, nodes: s.keys.length, hulls: 0 };
  const bp = ctx.beginPath.bind(ctx);
  ctx.beginPath = () => {
    stats.paths++;
    bp();
  };
  try {
    body(stats);
  } finally {
    ctx.beginPath = bp;
  }
  return stats;
}

const toCamera = (ctx: CanvasRenderingContext2D, s: Scene) =>
  ctx.setTransform(s.dpr * s.cam.k, 0, 0, s.dpr * s.cam.k, s.dpr * (s.width / 2 - s.cam.x * s.cam.k), s.dpr * (s.height / 2 - s.cam.y * s.cam.k));

function paintStatic(ctx: CanvasRenderingContext2D, s: Scene, stats: DrawStats) {
  ctx.setTransform(s.dpr, 0, 0, s.dpr, 0, 0);
  ctx.fillStyle = s.colour('--bg');
  ctx.fillRect(0, 0, s.width, s.height);
  toCamera(ctx, s);
  drawHulls(ctx, s, stats);
  drawEdges(ctx, s);
  drawHalos(ctx, s, stats);
  drawNodes(ctx, s, stats);
  drawLabels(ctx, s, stats);
}

const alphaOf = (s: Scene, k: string) => s.depth?.get(k) ?? 1;

/** Padding between a project's members and its hull, in world units. */
export const HULL_PAD = 6;

export interface Hull {
  project: string;
  pts: Point[];
  focused: boolean;
}

/** The project hulls (ADR-0025 §4, rulebook §12): for each drawn project with
 * at least one drawn member — a node it contains at any depth — the convex
 * hull of its own and its members' shapes, padded; focused when the focus is
 * the project or one of its members. A collapsed project draws none. */
export function hulls(s: Pick<Scene, 'model' | 'keys' | 'pos' | 'focus'>): Hull[] {
  const out: Hull[] = [];
  for (const k of s.keys) {
    const n = s.model.byKey.get(k);
    if (n?.kind !== 'project' || n.endpoint) continue;
    const members = s.keys.filter((x) => x !== k && ancestors(s.model, x).includes(k));
    if (!members.length) continue;
    const pts: Point[] = [];
    for (const x of [k, ...members]) {
      const p = s.pos.get(x);
      const m = s.model.byKey.get(x)!;
      if (!p) continue;
      const r = radiusOf(lookOf(m.kind, m.endpoint, m.type).shape) + HULL_PAD;
      for (let i = 0; i < 12; i++) pts.push({ x: p.x + r * Math.cos((i * Math.PI) / 6), y: p.y + r * Math.sin((i * Math.PI) / 6) });
    }
    out.push({ project: k, pts: convex(pts), focused: !!s.focus && (s.focus === k || members.includes(s.focus)) });
  }
  return out;
}

/** Andrew's monotone chain: the convex hull, counter-clockwise. */
function convex(ps: Point[]): Point[] {
  const p = [...ps].sort((a, b) => a.x - b.x || a.y - b.y);
  if (p.length < 3) return p;
  const cross = (o: Point, a: Point, b: Point) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const half = (pts: Point[]) => {
    const h: Point[] = [];
    for (const q of pts) {
      while (h.length >= 2 && cross(h[h.length - 2], h[h.length - 1], q) <= 0) h.pop();
      h.push(q);
    }
    h.pop();
    return h;
  };
  return [...half(p), ...half([...p].reverse())];
}

/** One filled path per project hull, under every stroke, in text ink at
 * `hull` (`hull-focus` for the focused project's); opaque, a 1 px outline. */
function drawHulls(ctx: CanvasRenderingContext2D, s: Scene, stats: DrawStats) {
  const hs = hulls(s);
  stats.hulls = hs.length;
  ctx.setLineDash([]);
  for (const h of hs) {
    ctx.beginPath();
    h.pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
    ctx.closePath();
    if (s.opaque) {
      ctx.globalAlpha = 1;
      ctx.lineWidth = 1 / s.cam.k;
      ctx.strokeStyle = s.colour('--line');
      ctx.stroke();
    } else {
      ctx.globalAlpha = ALPHA[h.focused ? 'hull-focus' : 'hull'];
      ctx.fillStyle = s.colour('--text');
      ctx.fill();
    }
  }
  ctx.globalAlpha = 1;
}

/** Receding lines (ADR-0025 §4, rulebook §24-25): an edge the focus does not
 * touch, and every edge Archeus only suggested, at alpha-recede; a recorded
 * edge of the focus at full strength (a mixed bundle claims no tier, so it
 * follows the focus rule). The selected, path and live edges are bright: the
 * caller never asks. Opaque: nothing recedes. */
export function recede(s: Pick<Scene, 'focus' | 'opaque'>, d: Pick<Drawn, 'a' | 'b' | 'tier'>): number {
  if (s.opaque) return 1;
  if (d.tier && d.tier !== 'EXTRACTED') return ALPHA['alpha-recede'];
  return !s.focus || d.a === s.focus || d.b === s.focus ? 1 : ALPHA['alpha-recede'];
}

/** A live node's core (ADR-0025 §4, rulebook §12): a dot of thread ink inside
 * its shape, this fraction of its radius. */
export const CORE = 0.35;

function drawEdges(ctx: CanvasRenderingContext2D, s: Scene) {
  const groups = new Map<string, Drawn[]>();
  for (const d of s.drawn) {
    const pa = s.pos.get(d.a);
    const pb = s.pos.get(d.b);
    if (!pa || !pb) continue;
    const hot = d.id === s.selected || !!s.path?.has(d.id);
    const live = s.live.has(d.id);
    const alpha = hot || live ? 1 : recede(s, d);
    const key = [dashOf(d.tier).join(','), widthOf(d.count, live && s.liveStatic), alpha, hot, d.inactive, d.structural].join('|');
    const g = groups.get(key);
    if (g) g.push(d);
    else groups.set(key, [d]);
  }
  for (const [key, ds] of groups) {
    const [dash, w, alpha, hot, inactive, structural] = key.split('|');
    ctx.setLineDash(dash ? dash.split(',').map(Number) : []);
    ctx.lineWidth = Number(w) / s.cam.k;
    ctx.globalAlpha = Number(alpha) * (structural === 'true' ? 0.5 : 1);
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
  ctx.globalAlpha = 1;
}

// drawn edges by id, once per drawn list (the view memoises it): a pulse frame
// looks its edges up instead of scanning them
const BY_ID = new WeakMap<readonly Drawn[], Map<string, Drawn>>();

/** One opacity step per pulsed edge, over the static layer (A8); none while
 * frames run slow (A10 degrade). */
function drawPulses(ctx: CanvasRenderingContext2D, s: Scene) {
  if (s.degraded || !s.pulse.size) return;
  toCamera(ctx, s);
  ctx.setLineDash([]);
  let index = BY_ID.get(s.drawn);
  if (!index) BY_ID.set(s.drawn, (index = new Map(s.drawn.map((d) => [d.id, d]))));
  for (const [id, t] of s.pulse) {
    const d = index.get(id);
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

/** The marker token (rulebook §38): thread ink, a 3 px head and a 12 px tail,
 * in screen pixels whatever the zoom. */
export const MARKER_HEAD = 3;
export const MARKER_TAIL = 12;

/** The travelling markers over the static layer (ADR-0024 §6, rulebook A-04):
 * each a head at its progress p along the straight edge from its source to its
 * target — linear, constant speed — with a tail back toward the source, never
 * past it; all tails one path, all heads one path. While frames run slow a
 * marker becomes the A-02 pulse's form instead (rulebook §21-§22: degraded →
 * pulse): the edge's one opacity step, no travel. A marker whose edge is no
 * longer drawn between its two ends is not drawn. */
function drawMarkers(ctx: CanvasRenderingContext2D, s: Scene) {
  if (!s.marker?.size) return;
  toCamera(ctx, s);
  ctx.setLineDash([]);
  let index = BY_ID.get(s.drawn);
  if (!index) BY_ID.set(s.drawn, (index = new Map(s.drawn.map((d) => [d.id, d]))));
  const heads: [number, number][] = [];
  const tails: [number, number, number, number][] = [];
  for (const [target, p] of s.marker) {
    const t = travelOf(target);
    const d = index.get(t.edge);
    const a = s.pos.get(t.from);
    const b = s.pos.get(t.to);
    if (!d || !a || !b || !((d.a === t.from && d.b === t.to) || (d.a === t.to && d.b === t.from))) continue;
    if (s.degraded) {
      ctx.globalAlpha = Math.max(0, 1 - p);
      ctx.lineWidth = 2 / s.cam.k;
      ctx.strokeStyle = s.colour('--state-active');
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      continue;
    }
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    const hx = a.x + dx * p;
    const hy = a.y + dy * p;
    const back = Math.min(p * len, MARKER_TAIL / s.cam.k) / len;
    tails.push([hx - dx * back, hy - dy * back, hx, hy]);
    heads.push([hx, hy]);
  }
  ctx.globalAlpha = 1;
  if (!heads.length) return;
  ctx.strokeStyle = s.colour('--thread');
  ctx.lineWidth = 1 / s.cam.k;
  ctx.beginPath();
  for (const [x0, y0, x1, y1] of tails) {
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
  }
  ctx.stroke();
  ctx.fillStyle = s.colour('--thread');
  ctx.beginPath();
  const r = MARKER_HEAD / 2 / s.cam.k;
  for (const [x, y] of heads) {
    ctx.moveTo(x + r, y);
    ctx.arc(x, y, r, 0, Math.PI * 2);
  }
  ctx.fill();
}

/** A legend row's swatch (ADR-0025 §2), drawn with what the graph draws that
 * thing with: the kind's traced shape in the neutral node colour, the tier's
 * dash in edge ink, the halo's two rings (one solid when transparency must not
 * carry it), the marker's thread-ink tail and head — or, under reduced motion,
 * the static live edge that replaces it. Canvas pixels, origin top left. */
export function drawSwatch(ctx: CanvasRenderingContext2D, row: LegendRow, w: number, h: number, colour: (v: string) => string, solid = false, reduced = false) {
  const cx = w / 2;
  const cy = h / 2;
  ctx.clearRect(0, 0, w, h);
  ctx.globalAlpha = 1;
  ctx.lineWidth = 1;
  ctx.setLineDash([]);
  const line = (dash: readonly number[], width: number, ink: string) => {
    ctx.setLineDash(dash as number[]);
    ctx.lineWidth = width;
    ctx.strokeStyle = colour(ink);
    ctx.beginPath();
    ctx.moveTo(2, cy);
    ctx.lineTo(w - 2, cy);
    ctx.stroke();
    ctx.setLineDash([]);
  };
  if (row.group === 'kind') {
    ctx.setLineDash(row.shape === 'endpoint' ? [1.5, 3] : []);
    const { filled } = tracePath(ctx, row.shape, cx, cy, Math.min(radiusOf(row.shape), h / 2 - 2));
    if (filled) {
      ctx.fillStyle = colour('--text-2');
      ctx.fill();
    } else {
      ctx.strokeStyle = colour('--text-2');
      ctx.stroke();
    }
  } else if (row.group === 'tier') {
    line(row.dash, widthOf(1), '--line-strong');
  } else if (row.key === 'halo') {
    const r = radiusOf('dot');
    tracePath(ctx, 'dot', cx, cy, r);
    ctx.fillStyle = colour('--text-2');
    ctx.fill();
    ctx.fillStyle = colour('--thread');
    ctx.beginPath();
    ctx.arc(cx, cy, r * CORE, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = colour('--state-active');
    for (const [gap, alpha] of haloRings(solid)) {
      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.arc(cx, cy, r + gap, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  } else if (reduced) {
    line([], widthOf(1, true), '--line-strong');
  } else {
    line([], widthOf(1), '--line-strong');
    const hx = w * 0.7;
    ctx.strokeStyle = colour('--thread');
    ctx.beginPath();
    ctx.moveTo(hx - MARKER_TAIL, cy);
    ctx.lineTo(hx, cy);
    ctx.stroke();
    ctx.fillStyle = colour('--thread');
    ctx.beginPath();
    ctx.arc(hx, cy, MARKER_HEAD / 2, 0, Math.PI * 2);
    ctx.fill();
  }
}

/** Where the halo's two strokes sit, outside the node's own radius (inside the
 * focus ring's 4 and outside it, so a focused live node shows both). */
export const HALO_RINGS = [2, 6] as const;

/** The halo's rings as (gap, alpha): two at halo-inner and halo-outer, or one
 * solid ring when transparency must not carry it. */
const haloRings = (solid: boolean): [number, number][] =>
  solid ? [[HALO_RINGS[0], 1]] : [[HALO_RINGS[0], ALPHA['halo-inner']], [HALO_RINGS[1], ALPHA['halo-outer']]];

/** The activity halo (ADR-0024 §6, ADR-0028 §3): two static 1 px strokes of
 * --state-active round every visible node with live work, the inner at
 * halo-inner and the outer at halo-outer; one solid ring when transparency
 * must not carry it. No gradient, no glow, never animated. One path per
 * ring and dimming, whatever the number of halos. */
function drawHalos(ctx: CanvasRenderingContext2D, s: Scene, stats: DrawStats) {
  if (!s.halo.size) return;
  const dots = stats.lod === 'dots';
  const rings = haloRings(!!s.opaque);
  ctx.setLineDash([]);
  ctx.lineWidth = 1 / s.cam.k;
  ctx.strokeStyle = s.colour('--state-active');
  const depths = [...new Set(s.keys.filter((k) => s.halo.has(k)).map((k) => alphaOf(s, k)))];
  for (const depth of depths)
    for (const [gap, alpha] of rings) {
      const at: [number, number, number][] = [];
      for (const k of s.keys) {
        const n = s.halo.has(k) && alphaOf(s, k) === depth ? s.model.byKey.get(k) : undefined;
        const p = n && s.pos.get(k);
        if (!n || !p) continue;
        at.push([p.x, p.y, dots ? (2 + gap) / s.cam.k : radiusOf(lookOf(n.kind, n.endpoint, n.type).shape) + gap]);
      }
      if (!at.length) continue;
      ctx.globalAlpha = alpha * depth;
      ctx.beginPath();
      for (const [x, y, r] of at) {
        ctx.moveTo(x + r, y);
        ctx.arc(x, y, r, 0, Math.PI * 2);
      }
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
      const c = colourVar(n.kind, n.machine, n.state) + '|' + alphaOf(s, k);
      const g = byColour.get(c);
      if (g) g.push(p);
      else byColour.set(c, [p]);
    }
    for (const [c, ps] of byColour) {
      const [cssVar, alpha] = c.split('|');
      ctx.globalAlpha = Number(alpha);
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
    ctx.globalAlpha = alphaOf(s, k);
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
    if (s.halo.has(k)) {
      ctx.fillStyle = s.colour('--thread');
      ctx.beginPath();
      ctx.arc(p.x, p.y, radiusOf(look.shape) * CORE, 0, Math.PI * 2);
      ctx.fill();
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
  // A10: the query focus and the selection always (above 250 nodes, only
  // they); up to 250 also the selection's neighbours and the hovered node;
  // below LABEL_ZOOM cluster labels only; degraded, the two foci only
  const main = (k: string) => k === s.focus || k === s.root;
  const wanted = new Set<string>();
  for (const k of s.keys) {
    const n = s.model.byKey.get(k);
    if (!n) continue;
    const cluster = lookOf(n.kind, n.endpoint, n.type).shape === 'cluster';
    if (s.degraded) {
      if (main(k)) wanted.add(k); // frames run slow: the foci's labels only
    } else if (cluster) wanted.add(k);
    else if (s.cam.k >= LABEL_ZOOM) {
      if (main(k)) wanted.add(k);
      else if (stats.lod === 'full' && (k === s.hover || !s.context || s.context.has(k))) wanted.add(k);
    }
  }
  ctx.fillStyle = s.colour('--text');
  ctx.font = `${12 / s.cam.k}px ${getFont()}`;
  ctx.textBaseline = 'middle';
  for (const k of wanted) {
    const n = s.model.byKey.get(k)!;
    const p = s.pos.get(k);
    if (!p) continue;
    const x = p.x + (radiusOf(lookOf(n.kind, n.endpoint, n.type).shape) + 4);
    ctx.globalAlpha = alphaOf(s, k);
    ctx.fillText(n.label, x, p.y);
    stats.labels++;
    // a second line, only what Core returned: a project's counts (A3, A4),
    // a route decision's recorded selection facts when it is focused (A3)
    const detail = n.kind === 'project' ? countsText(n.counts) : n.kind === 'route_decision' && k === s.focus ? attrsText(n.attrs) : '';
    if (detail && !s.degraded) {
      ctx.fillStyle = s.colour('--text-2');
      ctx.fillText(detail, x, p.y + 15 / s.cam.k);
      ctx.fillStyle = s.colour('--text');
    }
  }
  ctx.globalAlpha = 1;
}

let font = '';
function getFont() {
  if (!font && typeof document !== 'undefined') font = getComputedStyle(document.documentElement).getPropertyValue('--font') || 'system-ui';
  return font || 'system-ui';
}
