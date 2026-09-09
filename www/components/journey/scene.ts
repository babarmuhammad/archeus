/**
 * The journey scene.
 *
 * Ported from archeus's own `graph` background world (claude_sessions/web/stage.js).
 * Same vocabulary, same reasons:
 *   - geodesic icosahedral CAGES (42 vertices, 120 edges) spinning on two axes at
 *     T*0.5 and T*0.37 with a per-node phase, exactly as connections.py's
 *     drawCluster does. A dodecahedron is a SOLID and says "here is a thing"; a
 *     cage holding a population says "here is a thing made of things, and it is
 *     connected to other things", which is the subject. Every number comes from
 *     notes/constellation-study.md — read it before retuning one;
 *   - an interior population of smaller points inside every hull: a cluster made
 *     of clusters, the shape of the project's own memory graph;
 *   - a white-cored, halo-lit joint at every vertex. The halo is a second
 *     additive Points over the SAME buffer, never a bloom pass — see the
 *     no-post-processing note in Canvas.tsx;
 *   - hairline links carrying packets;
 *   - deterministic golden-angle placement (i * 2.399963, no Math.random) so the
 *     constellation is identical on every reload;
 *   - geometry MERGED into a handful of draw calls and animated entirely in the
 *     vertex shader. Merged rather than InstancedMesh on purpose: whether three
 *     injects `attribute mat4 instanceMatrix` into a raw ShaderMaterial's prefix
 *     has moved between versions.
 *
 * Everything a station "does" is one uniform driven by scroll. No CPU work per
 * frame beyond writing those uniforms and the camera.
 */
import * as THREE from 'three';
import { CLUSTER } from '@/lib/cluster-spec';

export const STATION_COUNT = 6;

/** Station centres. Spread in x/y and stepping back in z, so the finale camera
 *  can pull back far enough to hold all six in one frame. */
const P = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

const STATIONS = [
  P(0, 0, 0),
  P(-9.5, -3.4, -6),
  P(9.0, 3.6, -12.5),
  P(-8.2, 4.4, -20),
  P(8.6, -4.6, -27.5),
  P(0, -0.8, -36),
];

const RADII = [2.35, 1.5, 1.75, 1.5, 1.45, 1.3];

/** Where the camera parks for each station. The last one is the pull-back. */
const CAM = [
  P(0.7, 0.9, 7.6),
  P(-7.0, -2.4, 0.4),
  P(6.2, 2.8, -6.4),
  P(-5.9, 3.2, -14.2),
  P(6.0, -3.0, -21.4),
  P(0, 2.2, 22),
];

/** What the camera looks at. The finale looks at the constellation's middle. */
const LOOK = [...STATIONS.slice(0, 5), P(0, 0.2, -17)];

const CURVE = new THREE.CatmullRomCurve3(STATIONS, false, 'catmullrom', 0.4);
const CAM_CURVE = new THREE.CatmullRomCurve3(CAM, false, 'catmullrom', 0.5);
const LOOK_CURVE = new THREE.CatmullRomCurve3(LOOK, false, 'catmullrom', 0.5);

/* Rotate about the cage's own centre, exactly as drawCluster does: ay around Y,
   then ax around X. */
const SPIN = /* glsl */ `
  vec3 spin(vec3 local, float ph, float t){
    float ax = t * 0.5 + ph, ay = t * 0.37 + ph * 1.7;
    float ca = cos(ax), sa = sin(ax), cb = cos(ay), sb = sin(ay);
    float x = local.x * cb + local.z * sb;
    float z = -local.x * sb + local.z * cb;
    float y2 = local.y * ca - z * sa;
    float z2 = local.y * sa + z * ca;
    return vec3(x, y2, z2);
  }`;

/** Node hues, from connections.TYPE_COLORS. Six of them are bound as uniforms
 *  below, in the role order cluster_spec.py numbers them, and every colour in
 *  the scene is picked off the chord they make.
 *
 *  DEEPENED, and these are the deepened values rather than the palette's own.
 *  A perpendicular cut across a frame tube in the reference render reads
 *  (0, 55, 135) in the wall and (0, 128, 233) in the energy — RED IS ZERO in
 *  both, and connections.TYPE_COLORS is #7dcfff, which is (125, 207, 255).
 *  Same hue, same HSL saturation, a third of the way to white: the gap is
 *  LIGHTNESS, which is why no saturation push ever reached it (#7dcfff is
 *  already s = 1.0, its max channel being 255) and why this file kept reaching
 *  for pow() instead.
 *
 *  The transform is `s x 1.12, l x 0.58` in sRGB HSL, the same pair the GUI's
 *  graph scene applies at run time (DEEP_S / DEEP_L in stage.js). Applied HERE
 *  as literals rather than computed, because this list is literal already and
 *  a run-time THREE.Color round trip would go through the working colour space
 *  — which this scene has managed and the GUI has switched off, so the same
 *  two lines of code would not produce the same two colours. */
const HUES = ['#008bdc', '#3800db', '#d30028', '#22a08c', '#a56c19', '#18b726'];

/** THE CHORD A CLUSTER WEARS — four ROLE indices, from a deterministic seed.
 *
 *  This replaces a five-stop hue ladder indexed by one number per cluster.
 *  A tone was one stop on a shared ramp, so a cluster was ONE COLOUR by
 *  construction, and the reference has a single cluster running violet into
 *  magenta into cyan with gold picking out individual struts. The rule the
 *  brief calls the most important is exactly the one that ladder broke: never
 *  reduce a cluster to a single flat colour.
 *
 *  The families and their weights are `claude_sessions/cluster_spec.py`, via
 *  the generated `@/lib/cluster-spec` — the GUI's stage.js and the 2D
 *  architecture graph read the same table, which is what makes "all three
 *  render the same reference" a fact rather than three separate intentions. */
const FAM = CLUSTER.PALETTE_FAMILIES as readonly (readonly [number, string, readonly number[]])[];
const FAM_TOTAL = FAM.reduce((t, f) => t + f[0], 0);

function chordOf(seed: number): readonly number[] {
  const at = (seed - Math.floor(seed)) * FAM_TOTAL;
  let acc = 0;
  for (const f of FAM) { acc += f[0]; if (at < acc) return f[2]; }
  return FAM[FAM.length - 1][2];
}

/** A station's or a section's own seed. Deterministic, and NOT the index: the
 *  index is 0..5 and every family boundary would land in the same place, so
 *  three of the six stations would come out the same chord. */
const seedOf = (i: number) => {
  const h = Math.sin(i * 45.233 + 7.13) * 21473.7;
  return h - Math.floor(h);
};

/** ...and the gradient's DIRECTION, per cluster. Two clusters wearing the same
 *  chord must not read as the same object rotated. */
const axisOf = (i: number): [number, number, number] => {
  const a1 = seedOf(i) * 6.2831853, a2 = (i * 2.399963) % 3.14159265;
  return [Math.cos(a1) * Math.sin(a2), Math.cos(a2), Math.sin(a1) * Math.sin(a2)];
};

/** The seed a SECTION's cluster wears, in document order.
 *
 *  Stations take their own index, because their order is arbitrary and all six
 *  are on screen together. Sections are read in order and only a span of two to
 *  five is visible at once, so walking a ladder monotonically would put violet
 *  next to indigo next to cyan and never gold next to violet — and the study's
 *  whole colour argument is that gold BESIDE violet, blue and green is what
 *  makes the image read. Striding by 5 through 7 is a permutation, so the
 *  weighting is preserved exactly while adjacent sections differ. */
const secSeed = (s: number) => seedOf((s * 5) % 7 + 11);

/** ...and the SIX STATIONS are stratified rather than sampled, which is a
 *  different problem from the sections' one.
 *
 *  `seedOf(i)` is a fair draw and six draws are not a fair sample: it put three
 *  of the six stations on `blend` — the deliberately magenta-leaning violet, 14%
 *  of the table — including station 01, the hero of the front page, which came
 *  out hot magenta against a reference that is violet and blue. Nothing about
 *  the hero's colour should be a lottery it lost.
 *
 *  Walking the weighted table at (i + 0.5) / n reproduces the table's weights
 *  exactly for any n, so the six come out two violet and one each of blend,
 *  cyan, magenta and gold. The gradient AXIS still comes off seedOf(i), so the
 *  two violet stations are not the same object rotated.
 *
 *  The sections keep their stride: seven of them are read in order with only a
 *  few visible at once, and stratifying THOSE would put three violets in a row
 *  at the top of the page, which is the thing the stride exists to avoid. */
const stationSeed = (i: number, n: number) => (i + 0.5) / n;

/* THE SIX ROLES, INDEXED — one place a number becomes a colour, numbered by
   cluster_spec.py so the same index means the same hue in every renderer. */
const SF_ROLE = /* glsl */ `
  vec3 roleCol(float r){
    vec3 c = u_acc;
    c = mix(c, u_acc2, step(0.5, r));
    // the magenta role, pulled a third of the way toward the violet accent:
    // err is a SALMON in most palettes because its real job is to read as a
    // failure against body text, and used raw every cluster came out coral
    c = mix(c, mix(u_err, u_acc2, 0.45), step(1.5, r));
    c = mix(c, u_warn, step(2.5, r));
    c = mix(c, u_ok,   step(3.5, r));
    c = mix(c, vec3(1.0), step(4.5, r));
    return c;
  }`;

/* Three stops and a highlight, weighted rather than three even thirds: a
   violet cluster is roughly six parts its primary, three its secondary and one
   its accent. An even split puts as much magenta on it as violet and the field
   comes out pink. The overlap between the stops is what keeps it a blend
   rather than two bands. */
const SF_CHORD = /* glsl */ `
  vec3 chord(vec4 pal, float t, float hot){
    vec3 a = roleCol(pal.x), b = roleCol(pal.y), c = roleCol(pal.z);
    vec3 col = mix(a, b, smoothstep(0.52, 0.88, t));
    col = mix(col, c, smoothstep(0.86, 1.0, t));
    return mix(col, roleCol(pal.w), clamp(hot, 0.0, 1.0));
  }`;

/* Where a fragment sits in its cluster's gradient. Every input the brief names
   is here and each does a different job: the angular term gives the gradient a
   direction, the radial term makes the centre a different colour from the rim,
   the noise breaks the sweep up (a clean sweep reads as a stripe), and the
   per-cluster seed offsets the noise so the same chord is a different picture.
   3D noise, not the 2D kind projected onto a sphere — that has a visible seam
   down the axis it dropped. */
const SF_GRAD = /* glsl */ `
  float h31(vec3 p){ return fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453); }
  float vnoise3(vec3 p){
    vec3 i = floor(p), f = fract(p);
    vec3 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(h31(i), h31(i + vec3(1,0,0)), u.x),
                   mix(h31(i + vec3(0,1,0)), h31(i + vec3(1,1,0)), u.x), u.y),
               mix(mix(h31(i + vec3(0,0,1)), h31(i + vec3(1,0,1)), u.x),
                   mix(h31(i + vec3(0,1,1)), h31(i + vec3(1,1,1)), u.x), u.y), u.z);
  }
  float gradT(vec3 local, vec3 axis, float seed, float scale){
    vec3 d = local / max(length(local), 1e-4);
    float ang = dot(d, axis) * 0.5 + 0.5;
    float rad = clamp(length(local), 0.0, 1.2);
    float n = vnoise3(local * scale + seed * 31.7);
    return clamp(ang * 0.58 + rad * 0.20 + n * 0.34 - 0.06, 0.0, 1.0);
  }`;

/** Every hue consumer declares the same six, in whichever stage reads them. */
const SF_HUES = /* glsl */ `uniform vec3 u_acc, u_acc2, u_err, u_warn, u_ok;`;

/** What a chord consumer declares, in whichever stage reads it. Written once
 *  because a varying declared in one stage and not the other is a link error
 *  with no line number worth reading. */
const SF_CVAR = /* glsl */ `varying vec4 vPal; varying float vGT;`;

/** ...and how a vertex stage fills them. `unit` is the local offset in UNIT
 *  hull space: gradT wants a direction and a radius, and a position already
 *  scaled by the hull would make the radial term depend on how big the cluster
 *  happens to be. */
const SF_CSET = /* glsl */ `
  void setChord(vec4 pal, vec4 cx, vec3 unit){
    vPal = pal;
    vGT = gradT(unit, cx.xyz, cx.w, 1.8 + cx.w * 3.2);
  }`;

/* Depth is REAL, not just a z: far means small, dim AND washed. Size by depth is
   the `vD` the shaders already had; this is the second cue, and they are not the
   same cue. Exponential, because that is how a haze accumulates over distance —
   the mechanism is stage.js's exactly, the two constants are not: this scene's
   depth budget is 46 units against the stage's 26, and the finale parks the
   camera 58 units from the last station. stage.js's `dist - 7` at 0.085 leaves
   that station at 1% and deletes the one shot the whole page builds toward. */
const SF_FOG = /* glsl */ `
  float fogOf(float dist){ return exp(-max(0.0, dist - 14.0) * 0.022); }`;

/* ── the per-section solids: constants shared by the shader and the hit test ──
   These numbers appear ONCE. The GLSL below interpolates them and `arrangeAt()`
   reads the same object, so the shape you see and the shape you can click are
   the same shape by construction — the failure mode otherwise is a solid you can
   see two sections away from where the cursor has to be. */

/** Longest section list the layer can hold. `/faq` is the largest real page at
 *  twelve; the cap exists because it is a uniform array, not because of layout. */
const MAX_SLOTS = 48;

/** Camera-space distance of the focal plane. Slot rects are converted here. */
const FOCAL = 8.0;

/** The showcases, in the order `u_layout` numbers them. Must match SpineLayout
 *  in components/site/Spine.tsx and the `.spine-*` grids in globals.css. */
export const LAYOUTS = [
  'beside', 'ladder', 'depth', 'orbit', 'triad', 'rail-left', 'rail-right', 'zigzag',
] as const;
export type LayoutName = (typeof LAYOUTS)[number];

/** Per-layout recession, as a multiple of the focal distance at one section of
 *  separation. In FOCAL units rather than in each solid's own radius, because
 *  what a reader sees as "further away" is the apparent SHRINK — and a rail
 *  solid a tenth the size of a `beside` one would otherwise barely move.
 *
 *  The falloff is `ad²/(0.6+ad)`, and the square is the whole point. The first
 *  version used `sqrt(ad)`, whose slope at zero is infinite: `sec` is a
 *  continuous index and is almost never a whole number — it is a fifth or a half
 *  of the way through a row nearly all the time — so the CURRENT solid was being
 *  thrown five units back, and the perspective divide then dragged it toward the
 *  middle of the screen and off its own slot. Measured on a hover map: the
 *  cursor found it 160px left of where it was drawn. Flat at zero, steep after
 *  half a section, is the shape this needs. */
const RECEDE: Record<LayoutName, number> = {
  beside: 1.6,
  ladder: 1.0,
  depth: 2.2,
  orbit: 1.4,
  triad: 0.9,
  'rail-left': 0.7,
  'rail-right': 0.7,
  zigzag: 1.1,
};

/** How wide the visible band of sections is, per layout. A rail of short rows
 *  scrolls through five sections in the time `beside` covers one — and `beside`
 *  is the tightest, because its neighbours' slots are in the half the copy is
 *  using. */
const SPAN: Record<LayoutName, number> = {
  beside: 2.2, ladder: 2.6, depth: 3.0, orbit: 2.6, triad: 3.0,
  'rail-left': 5.0, 'rail-right': 5.0, zigzag: 4.0,
};

/* No shader below declares its own `precision` line. three injects one into BOTH
   stages from the renderer's capabilities; a hand-written `precision mediump
   float;` in a fragment shader only overrides that half, and every uniform these
   materials SHARE between the two stages then differs in precision and the
   program fails to link — silently, on the hardware that reports highp. */
type U = Record<string, { value: unknown }>;

const uniforms = (): U => ({
  u_t: { value: 0 },
  u_prog: { value: 0 },
  u_lit: { value: 0 },
  u_frag: { value: 0 },
  u_mem: { value: 0 },
  u_shot: { value: 0 },
  u_pkt: { value: 0 },
  u_web: { value: 0 },
  // The per-section solids. `u_sec` is which section is current (continuous);
  // everything about WHERE one goes comes from `u_slot`, which is the rect of
  // that section's empty `.spine-slot` element, in CSS pixels, document space.
  u_sec: { value: 0 },
  u_slot: { value: new Float32Array(MAX_SLOTS * 4) },
  u_scroll: { value: 0 },
  u_vw: { value: 1 },
  u_vh: { value: 1 },
  // Half-extents of the frustum at the focal plane. The slot rect is converted
  // at exactly this distance, so the current section's solid fills its box.
  u_halfW: { value: 1 },
  u_halfH: { value: 1 },
  /** Which showcase this page wears. See LAYOUTS. */
  u_layout: { value: 0 },
  /** How many sections either side stay visible; a rail of short rows needs a
   *  wider span than six full-height ones. */
  u_span: { value: 3.4 },
  /** Global alpha for the section layer — a narrow viewport has no empty half,
   *  so what solids it does get stay well under the copy. */
  u_wash: { value: 1 },
  u_res: { value: new THREE.Vector2(1, 1) },
  u_acc: { value: new THREE.Color(HUES[0]) },
  u_acc2: { value: new THREE.Color(HUES[1]) },
  // Gold and green: the two warm stops of the ladder. Accents, at two sevenths
  // of the weight — see TONES.
  u_warn: { value: new THREE.Color(HUES[4]) },
  u_ok: { value: new THREE.Color(HUES[3]) },
  // THE MAGENTA. The reference cluster holds violet and magenta at once, and
  // until this was bound every hue the scene could reach was cool, gold or
  // green — the same gap the GUI's stage had.
  u_err: { value: new THREE.Color(HUES[2]) },
  // The renderer's clear colour (Canvas.tsx), which is what the depth fog mixes
  // toward. A fog that mixes toward black instead reads as a shadow.
  u_bg: { value: new THREE.Color(0x0a0c10) },
});

/** The 42 distinct vertices of the cage, deduplicated from the triangle soup
 *  three hands back — IcosahedronGeometry(1, 1) is 240 positions for 42 corners,
 *  so drawing the soup stacks five or six additive sprites on one pixel: five or
 *  six times the fill for a halo that is then five or six times too bright. The
 *  joints also have to light in a stable order, which overlapping points cannot
 *  give. Verified: 240 positions in, 42 out, every one at circumradius 1. */
function cageVertices(): THREE.Vector3[] {
  const g = new THREE.IcosahedronGeometry(1, 1);
  const pos = g.getAttribute('position');
  const seen = new Map<string, THREE.Vector3>();
  for (let i = 0; i < pos.count; i++) {
    const v = new THREE.Vector3().fromBufferAttribute(pos, i);
    const k = `${v.x.toFixed(3)}|${v.y.toFixed(3)}|${v.z.toFixed(3)}`;
    if (!seen.has(k)) seen.set(k, v);
  }
  g.dispose();
  // Deterministic order: by height, so "lighting one by one" reads as a sweep.
  return [...seen.values()].sort((a, b) => a.y - b.y || a.x - b.x);
}

/** THE trait that carries the whole idea, and the one the dodecahedral scene had
 *  no equivalent of: every hull encloses a haze of smaller points — nodes made of
 *  nodes, which is literally the shape of this project's memory graph, entities
 *  inside modules inside repositories. A hull with nothing in it is a cosmetic
 *  swap.
 *
 *  Returns local offsets for a UNIT hull (so `local * r` in the shader lands them
 *  inside a hull of any radius, which is what lets the per-section solids — whose
 *  radius is a slot measured at runtime — share this), as flat (x, y, z, h)
 *  quadruples where `h` is the point's own hash.
 *
 *  Direction comes off a Fibonacci sphere and the radius off an INDEPENDENT hash:
 *  driving both from `k` piles every point at one pole. The radius exponent is
 *  0.45, ABOVE the volume-uniform 1/3, so the cloud is very slightly hollowed
 *  rather than core-heavy — in the reference image the densest reading comes from
 *  the hull's own vertices, not from a ball in the middle.
 *
 *  No Math.random: `seed` is the hull's index, so the interior is identical on
 *  every reload for the same reason the layout is. */
const MOTE_R = 0.55;
function moteLocals(count: number, seed: number): number[] {
  const out: number[] = [];
  for (let k = 0; k < count; k++) {
    const y = 1 - (2 * (k + 0.5)) / count;
    const ring = Math.sqrt(Math.max(0, 1 - y * y));
    const th = k * 2.399963;                              // golden angle
    const h = ((k * 7919 + seed * 104729) % 233280) / 233280;
    const rad = MOTE_R * Math.pow(h, 0.45);
    out.push(Math.cos(th) * ring * rad, y * rad, Math.sin(th) * ring * rad, h);
  }
  return out;
}

/** How many motes a hull of relative size `q` (0..1 against the largest in its
 *  group) holds: a leaf a dozen, a hub about two hundred and fifty. */
const moteCount = (q: number) => 12 + Math.round(240 * Math.pow(q, 1.8));

/** A `.spine-slot` rect, in CSS pixels, document space: centre x, centre y from
 *  the top of the DOCUMENT (not the viewport), and half-extent. */
export type Slot = { x: number; y: number; r: number };

/** What the pointer is over, if anything. */
export type Hit = { kind: 'section' | 'station'; index: number };

export type Journey = {
  group: THREE.Group;
  /** Writes every uniform and the camera. The only per-frame CPU work.
   *  `px`/`py` are the damped pointer offset in -1..1, already smoothed by the
   *  caller — the scene never reads an input device itself. */
  update(
    camera: THREE.PerspectiveCamera,
    t: number,
    progress: number,
    lit: number,
    px?: number,
    py?: number,
    /** Continuous section index — 2.4 means "40% of the way from section 2 to 3".
     *  Decides which solid is at the focal plane and how far back the rest are. */
    section?: number,
    /** window.scrollY. The slots are in document space, so this is what turns
     *  them into screen positions — and it means a solid tracks its own copy
     *  exactly, at any row height, on any page. */
    scroll?: number,
  ): void;
  /** Per-section weights in document order, and which showcase this page wears.
   *  A weight decides how much of its slot a solid fills; the slot decides where.
   *  Fewer than two sections means the page has none and the layer stays off. */
  setSections(weights: number[], layout?: LayoutName): void;
  /** The measured `.spine-slot` rects, in document order. Re-measured on resize,
   *  on reflow and on every route change — never per frame. */
  setSlots(slots: Slot[]): void;
  /** The six-station journey belongs to the landing page. Every other route
   *  hides it and shows only its own section solids — two constellations at once
   *  is what made the content pages unreadable. */
  setStations(on: boolean): void;
  /** Which solid is under this NDC point, nearest first, or null. */
  hit(camera: THREE.PerspectiveCamera, nx: number, ny: number): Hit | null;
  /** Drawing-buffer size for gl_PointSize, then CSS size for the slot maths. */
  resize(w: number, h: number, cssW: number, cssH: number): void;
  dispose(): void;
};

export function buildJourney(): Journey {
  const u = uniforms();
  const group = new THREE.Group();
  const disposables: { dispose(): void }[] = [];
  const track = <T extends { dispose(): void }>(x: T) => (disposables.push(x), x);

  /* The six-station journey. It is the landing page; every other route hides it
     and shows only the per-section solids, which are that page's own subject. */
  const stations = new THREE.Group();
  group.add(stations);

  /* ── 1. the six cages, one merged LineSegments ──────────────────────────────
     IcosahedronGeometry(1, 1): 42 vertices, 120 edges, 80 faces — a subdivided
     icosahedron projected back onto its circumsphere. Two consequences worth
     stating. The facets are NOT coplanar after that projection (the dihedral
     between two sub-triangles of one original face is ~10-20°), so EdgesGeometry
     keeps all 120 rather than welding them away at its 1° default. And a
     120-edge cage is dense enough that the eye stops counting faces and starts
     reading a surface, which is most of the difference between this and a
     30-edge platonic solid that reads as a die. */
  const base = new THREE.IcosahedronGeometry(1, 1);
  const wire = new THREE.EdgesGeometry(base);
  const wp = wire.getAttribute('position');
  base.dispose();

  const R_MAX = Math.max(...RADII);
  /* Per-station colour, carried as ATTRIBUTES rather than uniform arrays. The
     GUI's stage.js does the opposite because its forty clusters MOVE and it
     needs a uniform array for their positions anyway; these six are static, the
     buffers are a few thousand vertices, and an attribute cannot be indexed
     out of range by a shader that has lost track of how many there are. */
  const PAL = Array.from({ length: STATION_COUNT }, (_, i) => chordOf(stationSeed(i, STATION_COUNT)));
  const AXIS = Array.from({ length: STATION_COUNT }, (_, i) => axisOf(i));
  const pushChord = (pal: number[], cx: number[], s: number) => {
    const q = PAL[s], a = AXIS[s];
    pal.push(q[0], q[1], q[2], q[3]);
    cx.push(a[0], a[1], a[2], seedOf(s));
  };

  const ePos: number[] = [], eCtr: number[] = [], eNd: number[] = [], eMid: number[] = [];
  const ePal: number[] = [], eCx: number[] = [], eLoc: number[] = [];
  for (let s = 0; s < STATION_COUNT; s++) {
    const c = STATIONS[s], r = RADII[s], ph = (s * 1.7) % 6.283;
    for (let v = 0; v < wp.count; v += 2) {
      const a = new THREE.Vector3().fromBufferAttribute(wp, v).multiplyScalar(r);
      const b = new THREE.Vector3().fromBufferAttribute(wp, v + 1).multiplyScalar(r);
      // The direction an edge flies off in when the solid fragments: outward
      // from the centre, along its own midpoint.
      const mid = a.clone().add(b).multiplyScalar(0.5).normalize();
      for (const q of [a, b]) {
        ePos.push(q.x, q.y, q.z);
        eCtr.push(c.x, c.y, c.z);
        eNd.push(ph, 0, s);
        eMid.push(mid.x, mid.y, mid.z);
        eLoc.push(q.x / r, q.y / r, q.z / r);
        pushChord(ePal, eCx, s);
      }
    }
  }
  wire.dispose();

  const gEdges = track(new THREE.BufferGeometry());
  gEdges.setAttribute('position', new THREE.Float32BufferAttribute(ePos, 3));
  gEdges.setAttribute('ctr', new THREE.Float32BufferAttribute(eCtr, 3));
  gEdges.setAttribute('nd', new THREE.Float32BufferAttribute(eNd, 3));
  gEdges.setAttribute('emid', new THREE.Float32BufferAttribute(eMid, 3));
  gEdges.setAttribute('cpal', new THREE.Float32BufferAttribute(ePal, 4));
  gEdges.setAttribute('ccx', new THREE.Float32BufferAttribute(eCx, 4));
  gEdges.setAttribute('cloc', new THREE.Float32BufferAttribute(eLoc, 3));

  const mEdges = new THREE.LineSegments(
    gEdges,
    track(new THREE.ShaderMaterial({
      uniforms: u,
      transparent: true,
      depthWrite: false,
      vertexShader: /* glsl */ `
        attribute vec3 ctr; attribute vec3 nd; attribute vec3 emid;
        attribute vec4 cpal; attribute vec4 ccx; attribute vec3 cloc;
        varying vec2 vN; varying float vD; varying float vS; varying float vF;
        ${SF_CVAR}
        uniform float u_t, u_frag;
        ${SPIN}
        ${SF_FOG}
        ${SF_GRAD}
        ${SF_CSET}
        void main(){
          vN = nd.xy; vS = nd.z;
          // A STRUT GRADIENTS ALONG ITS OWN LENGTH: the walk is evaluated at
          // THIS end's position, so the two ends of one edge get different
          // values and the fragment interpolates between them.
          setChord(cpal, ccx, cloc);
          // Station 02 is the one that comes apart: its edges fly outward and
          // the cage stops being a cage.
          float fr = (abs(nd.z - 1.0) < 0.5) ? u_frag : 0.0;
          vec3 local = position + emid * fr * 2.6;
          vec3 p = ctr + spin(local, nd.x, u_t * (1.0 - 0.55 * fr));
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          vD = clamp(1.0 - (-mv.z) / 46.0, 0.0, 1.0);
          vF = fogOf(-mv.z);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        varying vec2 vN; varying float vD; varying float vS; varying float vF;
        ${SF_CVAR}
        ${SF_HUES}
        uniform vec3 u_bg;
        uniform float u_frag, u_web;
        ${SF_ROLE}
        ${SF_CHORD}
        void main(){
          float fr = (abs(vS - 1.0) < 0.5) ? u_frag : 0.0;
          vec3 col = mix(u_bg, chord(vPal, vGT, 0.0), vF);
          /* A strut is DIMMER than a node and a hull-to-hull link is dimmer
             still. In the reference image the ladder is unmistakable: nodes are
             the brightest thing in the frame, struts are filaments with
             presence, links are almost background. WebGL line width is 1px
             whatever you ask for, so "thinner" is spent as alpha — the right
             currency anyway, since one control then buys both reads. */
          float a = (0.20 + 0.30 * vD) * vF * (1.0 - 0.62 * fr) * (0.86 + 0.30 * u_web);
          gl_FragColor = vec4(col, a);
        }`,
    })),
  );
  mEdges.frustumCulled = false;
  mEdges.renderOrder = 2;
  stations.add(mEdges);

  /* ── 2. the lit joint at every vertex ───────────────────────────────────── */
  const verts = cageVertices();
  const jPos: number[] = [], jCtr: number[] = [], jNd: number[] = [], jOrd: number[] = [];
  const jPal: number[] = [], jCx: number[] = [], jLoc: number[] = [];
  for (let s = 0; s < STATION_COUNT; s++) {
    const c = STATIONS[s], r = RADII[s], ph = (s * 1.7) % 6.283;
    verts.forEach((v, k) => {
      jPos.push(v.x * r, v.y * r, v.z * r);
      jCtr.push(c.x, c.y, c.z);
      jNd.push(ph, 0, s);
      jOrd.push(k / verts.length);
      jLoc.push(v.x, v.y, v.z);
      pushChord(jPal, jCx, s);
    });
  }
  const gJoint = track(new THREE.BufferGeometry());
  gJoint.setAttribute('position', new THREE.Float32BufferAttribute(jPos, 3));
  gJoint.setAttribute('ctr', new THREE.Float32BufferAttribute(jCtr, 3));
  gJoint.setAttribute('nd', new THREE.Float32BufferAttribute(jNd, 3));
  gJoint.setAttribute('ord', new THREE.Float32BufferAttribute(jOrd, 1));
  gJoint.setAttribute('cpal', new THREE.Float32BufferAttribute(jPal, 4));
  gJoint.setAttribute('ccx', new THREE.Float32BufferAttribute(jCx, 4));
  gJoint.setAttribute('cloc', new THREE.Float32BufferAttribute(jLoc, 3));

  /* The joint's vertex stage, shared by the white core and by its halo — the
     halo is the SAME 42 points drawn a second time, wider and additive, over the
     SAME buffer (one more draw call, not one more byte). That is how this scene
     gets a glow with no post-processing: bloom went in here and came straight
     back out, because these are raw ShaderMaterials writing final display values
     and a pass that re-encodes them lifts the dark tones instead of blooming the
     bright ones. See the note in Canvas.tsx. `k` is the size multiplier. */
  const jointVert = (k: number) => /* glsl */ `
    attribute vec3 ctr; attribute vec3 nd; attribute float ord;
    attribute vec4 cpal; attribute vec4 ccx; attribute vec3 cloc;
    varying vec2 vN; varying float vD; varying float vA; varying float vF;
    ${SF_CVAR}
    uniform float u_t, u_lit, u_frag, u_web; uniform vec2 u_res;
    ${SPIN}
    ${SF_FOG}
    ${SF_GRAD}
    ${SF_CSET}
    void main(){
      vN = nd.xy;
      setChord(cpal, ccx, cloc);
      vec3 p = ctr + spin(position, nd.x, u_t);
      vec4 mv = modelViewMatrix * vec4(p, 1.0);
      vD = clamp(1.0 - (-mv.z) / 46.0, 0.0, 1.0);
      vF = fogOf(-mv.z);
      // Station 01 lights its joints one by one on arrival; station 02 loses
      // them as it comes apart; the finale brings every one back up.
      float lit = (abs(nd.z) < 0.5) ? smoothstep(ord, ord + 0.22, u_lit) : 1.0;
      float dim = (abs(nd.z - 1.0) < 0.5) ? (1.0 - 0.88 * u_frag) : 1.0;
      vA = lit * dim * (0.85 + 0.45 * u_web);
      gl_Position = projectionMatrix * mv;
      gl_PointSize = (2.2 + 3.4 * vD) * (u_res.y / 900.0 + 0.6) * ${k.toFixed(2)};
    }`;

  const mJoint = new THREE.Points(
    gJoint,
    track(new THREE.ShaderMaterial({
      uniforms: u,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: jointVert(1),
      fragmentShader: /* glsl */ `
        varying vec2 vN; varying float vD; varying float vA; varying float vF;
        ${SF_CVAR}
        ${SF_HUES}
        uniform vec3 u_bg;
        ${SF_ROLE}
        ${SF_CHORD}
        void main(){
          float d = length(gl_PointCoord - 0.5);
          if (d > 0.5) discard;
          /* WHITE core inside a COLOURED halo. The reference image's nodes are
             white points sitting in a coloured bloom, not coloured dots with a
             highlight — the old joint mixed 45% toward white over the inner half
             and read as a pale version of the accent. */
          float core = smoothstep(0.20, 0.0, d);
          float wide = pow(max(0.0, 1.0 - d * 2.0), 2.2);
          vec3 col = mix(chord(vPal, vGT, 0.0), vec3(1.0), core * 0.75);
          col = mix(u_bg, col, vF);
          // Nodes are the brightest thing in the frame; struts and links are
          // scaled under them.
          float a = (core * 0.85 + wide * 0.30) * (0.30 + 0.55 * vD) * vA * vF;
          gl_FragColor = vec4(col, a);
        }`,
    })),
  );
  mJoint.frustumCulled = false;
  mJoint.renderOrder = 3;
  stations.add(mJoint);

  // …and the halo: the same points, three times as wide, coloured, additive,
  // faint. Drawn UNDER the core so the white centre stays white.
  const mHalo = new THREE.Points(
    gJoint,
    track(new THREE.ShaderMaterial({
      uniforms: u,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: jointVert(3.2),
      fragmentShader: /* glsl */ `
        varying vec2 vN; varying float vD; varying float vA; varying float vF;
        ${SF_CVAR}
        ${SF_HUES}
        uniform vec3 u_bg;
        ${SF_ROLE}
        ${SF_CHORD}
        void main(){
          float d = length(gl_PointCoord - 0.5);
          if (d > 0.5) discard;
          float g = pow(max(0.0, 1.0 - d * 2.0), 2.2);
          gl_FragColor = vec4(mix(u_bg, chord(vPal, vGT, 0.0), vF),
                              g * 0.16 * (0.35 + 0.65 * vD) * vA * vF);
        }`,
    })),
  );
  mHalo.frustumCulled = false;
  mHalo.renderOrder = 2;
  stations.add(mHalo);

  /* ── 2b. the interior population: a cluster is made of clusters ───────────
     One merged additive Points cloud for all six hulls, animated entirely in the
     vertex shader like everything else. See moteLocals for the distribution. */
  const mtPos: number[] = [], mtCtr: number[] = [], mtNd: number[] = [], mtH: number[] = [];
  const mtPal: number[] = [], mtCx: number[] = [], mtLoc: number[] = [];
  for (let s = 0; s < STATION_COUNT; s++) {
    const c = STATIONS[s], r = RADII[s], ph = (s * 1.7) % 6.283;
    const q = moteLocals(moteCount(r / R_MAX), s);
    for (let k = 0; k < q.length; k += 4) {
      mtPos.push(q[k] * r, q[k + 1] * r, q[k + 2] * r);
      mtCtr.push(c.x, c.y, c.z);
      mtNd.push(ph, 0, s);
      mtH.push(q[k + 3]);
      mtLoc.push(q[k], q[k + 1], q[k + 2]);
      pushChord(mtPal, mtCx, s);
    }
  }
  const gMote = track(new THREE.BufferGeometry());
  gMote.setAttribute('position', new THREE.Float32BufferAttribute(mtPos, 3));
  gMote.setAttribute('ctr', new THREE.Float32BufferAttribute(mtCtr, 3));
  gMote.setAttribute('nd', new THREE.Float32BufferAttribute(mtNd, 3));
  gMote.setAttribute('mh', new THREE.Float32BufferAttribute(mtH, 1));
  gMote.setAttribute('cpal', new THREE.Float32BufferAttribute(mtPal, 4));
  gMote.setAttribute('ccx', new THREE.Float32BufferAttribute(mtCx, 4));
  gMote.setAttribute('cloc', new THREE.Float32BufferAttribute(mtLoc, 3));

  const mMote = new THREE.Points(
    gMote,
    track(new THREE.ShaderMaterial({
      uniforms: u,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: /* glsl */ `
        attribute vec3 ctr; attribute vec3 nd; attribute float mh;
        attribute vec4 cpal; attribute vec4 ccx; attribute vec3 cloc;
        varying vec2 vN; varying float vD; varying float vA;
        varying float vF; varying float vH;
        ${SF_CVAR}
        uniform float u_t, u_lit, u_frag, u_web; uniform vec2 u_res;
        ${SPIN}
        ${SF_FOG}
        ${SF_GRAD}
        ${SF_CSET}
        void main(){
          vN = nd.xy; vH = mh;
          setChord(cpal, ccx, cloc);
          vec3 p = ctr + spin(position, nd.x, u_t);
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          vD = clamp(1.0 - (-mv.z) / 46.0, 0.0, 1.0);
          vF = fogOf(-mv.z);
          // The interior fills in with the joints on station 01 and is thrown
          // out with the cage on station 02 — the hash stands in for the order,
          // so it fills from nowhere in particular rather than bottom to top.
          float lit = (abs(nd.z) < 0.5) ? smoothstep(mh, mh + 0.22, u_lit) : 1.0;
          float dim = (abs(nd.z - 1.0) < 0.5) ? (1.0 - 0.88 * u_frag) : 1.0;
          vA = lit * dim * (0.85 + 0.45 * u_web);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = (1.1 + 1.8 * vD) * (u_res.y / 900.0 + 0.6);
        }`,
      fragmentShader: /* glsl */ `
        varying vec2 vN; varying float vD; varying float vA;
        varying float vF; varying float vH;
        ${SF_CVAR}
        ${SF_HUES}
        uniform vec3 u_bg;
        ${SF_ROLE}
        ${SF_CHORD}
        void main(){
          float d = length(gl_PointCoord - 0.5);
          if (d > 0.5) discard;
          /* THE INTERNAL NETWORK IS FOUR POPULATIONS, in the split the brief
             gives and cluster_spec.py holds: most of it cool, a quarter
             magenta, a tenth gold, a few white-hot. Gold is an ACCENT here,
             never the dominant colour — and it is not white either: white was a
             guess from a still, and it is why the interior used to read as flat
             fog with sparkles in it rather than as a population with a second
             kind of thing in it. */
          vec3 col = chord(vPal, clamp(mix(0.05, 0.55, vH / ${CLUSTER.FILAMENT_MIX[0]}), 0.0, 1.0), 0.0);
          col = mix(col, roleCol(2.0), step(${CLUSTER.FILAMENT_MIX[0]}, vH) * 0.85);
          col = mix(col, u_warn, step(${CLUSTER.FILAMENT_MIX[1]}, vH) * 0.9);
          col = mix(col, vec3(1.0), step(${CLUSTER.FILAMENT_MIX[2]}, vH) * 0.9);
          col = mix(u_bg, col, vF);
          float a = (1.0 - smoothstep(0.1, 0.5, d)) * (0.16 + 0.26 * vD) * vA * vF;
          gl_FragColor = vec4(col, a);
        }`,
    })),
  );
  mMote.frustumCulled = false;
  mMote.renderOrder = 2;
  stations.add(mMote);

  /* ── 2c. THE FRAME AND THE SPOKES, AS RIBBONS ─────────────────────────────
     A station's most recognisable feature is the coarse icosahedral frame:
     twelve junctions joined by thirty tubes. It used to be real lit geometry
     here — `InstancedMesh` over `MeshPhysicalMaterial`, three directional
     lights and a magenta rim, depth-written — on the argument that an additive
     scene with no depth cannot have a silhouette, so the frame sums into the
     haze it is supposed to sit in front of.

     THAT ARGUMENT LOST. The GUI's graph world was rebuilt the same way and the
     judgement on it was "keep the complications of the cluster … just remove
     from all of this the 3d effect", so both renderers draw every part the
     reference has and none of the lighting. What made the frame read as a
     frame was never the lighting model: it is that it is three times the width
     of a shell rod and carries a junction at each end, and both survive being
     drawn flat.

     A RIBBON AND NOT A LINE, because WebGL ignores `lineWidth` — the 120-edge
     cage above is a `LineSegments` and can only ever be a one-pixel hairline,
     which is right for a mesh you look through and wrong for the frame that
     mesh is wrapped around. Four vertices and two triangles per rod, expanded
     across its own width in the vertex shader, still one draw call. The width
     is in WORLD units, so a distant rod is genuinely thinner rather than a
     constant-width ribbon fighting every other depth cue in the scene. */
  const ico0 = new THREE.IcosahedronGeometry(1, 0);
  const w0 = new THREE.EdgesGeometry(ico0);
  const w0p = w0.getAttribute('position');
  const i0p = ico0.getAttribute('position');
  const seenC = new Map<string, THREE.Vector3>();
  for (let i = 0; i < i0p.count; i++) {
    const v = new THREE.Vector3().fromBufferAttribute(i0p, i);
    seenC.set(`${v.x.toFixed(3)}|${v.y.toFixed(3)}|${v.z.toFixed(3)}`, v);
  }
  /* The corners are deduplicated out of the triangle soup and CHECKED against
     the spec: `IcosahedronGeometry` hands back sixty positions for twelve
     corners, and the two counts are the one thing this scene, the GUI's stage
     and the architecture graph all have to agree about. */
  const CORNERS0 = [...seenC.values()];
  if (CORNERS0.length !== CLUSTER.FRAME_NODES || w0p.count / 2 !== CLUSTER.FRAME_EDGES) {
    throw new Error(`frame: ${CORNERS0.length}/${w0p.count / 2} against the spec's `
      + `${CLUSTER.FRAME_NODES}/${CLUSTER.FRAME_EDGES}`);
  }
  //: the 20 face centres — where a hub spoke points
  const SPOKES0: THREE.Vector3[] = [];
  for (let f = 0; f < i0p.count; f += 3) {
    const c3 = new THREE.Vector3();
    for (let k = 0; k < 3; k++) c3.add(new THREE.Vector3().fromBufferAttribute(i0p, f + k));
    SPOKES0.push(c3.normalize());
  }
  ico0.dispose();

  const dPos: number[] = [], dOther: number[] = [], dSide: number[] = [];
  const dAlpha: number[] = [], dHalf: number[] = [], dCtr: number[] = [];
  const dMid: number[] = [], dNd: number[] = [], dPal: number[] = [];
  const dCx: number[] = [], dLoc: number[] = [], dIdx: number[] = [];
  let nRod = 0;
  const rod = (st: number, a: THREE.Vector3, b: THREE.Vector3,
               half: number, alpha: number) => {
    const c = STATIONS[st], r = RADII[st], ph = (st * 1.7) % 6.283;
    // the direction this rod flies off in when station 02 comes apart —
    // outward from the centre, along its own midpoint, exactly as the cage's
    // edges do, or the frame stays put while the mesh around it scatters
    const mid = a.clone().add(b).multiplyScalar(0.5).normalize();
    const base = nRod * 4;
    for (const [t, side] of [[0, -1], [0, 1], [1, -1], [1, 1]] as [number, number][]) {
      const me = t ? b : a, other = t ? a : b;
      dPos.push(me.x, me.y, me.z);
      dOther.push(other.x, other.y, other.z);
      dSide.push(side); dAlpha.push(alpha); dHalf.push(half);
      dCtr.push(c.x, c.y, c.z);
      dMid.push(mid.x, mid.y, mid.z);
      dNd.push(ph, 0, st);
      dLoc.push(me.x / r, me.y / r, me.z / r);
      pushChord(dPal, dCx, st);
    }
    dIdx.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
    nRod++;
  };

  for (let st = 0; st < STATION_COUNT; st++) {
    const r = RADII[st];
    /* Alpha 1.0 against the cage's own ~0.2: thirty rods and a hundred and
       twenty cannot share a number, and this is the population the eye is
       supposed to read first. */
    for (let v = 0; v < w0p.count; v += 2) {
      rod(st, new THREE.Vector3().fromBufferAttribute(w0p, v).multiplyScalar(r),
          new THREE.Vector3().fromBufferAttribute(w0p, v + 1).multiplyScalar(r),
          CLUSTER.FRAME_HALF * r, 1.0);
    }
    /* ...and the twenty spokes, which stop at 0.56 R and never reach the
       centre. Twenty rods meeting at one point sum, additively, into a white
       star brighter than anything the scene means — that is what SPOKE_IN is
       for, and it matters more here than it did under the lights because every
       pass in this scene is additive. */
    for (const d of SPOKES0) {
      rod(st, d.clone().multiplyScalar(r * CLUSTER.SPOKE_IN),
          d.clone().multiplyScalar(r * CLUSTER.SPOKE_OUT),
          CLUSTER.SPOKE_HALF * r, 0.42);
    }
  }
  w0.dispose();

  const gRods = track(new THREE.BufferGeometry());
  gRods.setAttribute('position', new THREE.Float32BufferAttribute(dPos, 3));
  gRods.setAttribute('rother', new THREE.Float32BufferAttribute(dOther, 3));
  gRods.setAttribute('rside', new THREE.Float32BufferAttribute(dSide, 1));
  gRods.setAttribute('ralpha', new THREE.Float32BufferAttribute(dAlpha, 1));
  gRods.setAttribute('rhalf', new THREE.Float32BufferAttribute(dHalf, 1));
  gRods.setAttribute('ctr', new THREE.Float32BufferAttribute(dCtr, 3));
  gRods.setAttribute('emid', new THREE.Float32BufferAttribute(dMid, 3));
  gRods.setAttribute('nd', new THREE.Float32BufferAttribute(dNd, 3));
  gRods.setAttribute('cpal', new THREE.Float32BufferAttribute(dPal, 4));
  gRods.setAttribute('ccx', new THREE.Float32BufferAttribute(dCx, 4));
  gRods.setAttribute('cloc', new THREE.Float32BufferAttribute(dLoc, 3));
  gRods.setIndex(dIdx);

  const mRods = new THREE.Mesh(
    gRods,
    track(new THREE.ShaderMaterial({
      uniforms: u,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      vertexShader: /* glsl */ `
        attribute vec3 rother; attribute float rside; attribute float ralpha;
        attribute float rhalf; attribute vec3 ctr; attribute vec3 emid;
        attribute vec3 nd; attribute vec4 cpal; attribute vec4 ccx;
        attribute vec3 cloc;
        varying float vX; varying float vA; varying float vD; varying float vF;
        varying float vS;
        ${SF_CVAR}
        uniform float u_t, u_frag;
        ${SPIN}
        ${SF_FOG}
        ${SF_GRAD}
        ${SF_CSET}
        void main(){
          vX = rside; vA = ralpha; vS = nd.z;
          setChord(cpal, ccx, cloc);
          float fr = (abs(nd.z - 1.0) < 0.5) ? u_frag : 0.0;
          float sp = u_t * (1.0 - 0.55 * fr);
          vec3 pa = ctr + spin(position + emid * fr * 2.6, nd.x, sp);
          vec3 pb = ctr + spin(rother + emid * fr * 2.6, nd.x, sp);
          vec4 mv = modelViewMatrix * vec4(pa, 1.0);
          vec3 bv = (modelViewMatrix * vec4(pb, 1.0)).xyz;
          // across the rod, camera-facing: perpendicular to the rod and to the
          // view axis
          vec3 side = normalize(cross(normalize(bv - mv.xyz), normalize(-mv.xyz)));
          mv.xyz += side * rside * rhalf;
          float dist = -mv.z;
          vD = clamp(1.0 - dist / 46.0, 0.0, 1.0);
          vF = fogOf(dist);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        varying float vX; varying float vA; varying float vD; varying float vF;
        varying float vS;
        ${SF_CVAR}
        ${SF_HUES}
        uniform vec3 u_bg;
        uniform float u_frag, u_web;
        ${SF_ROLE}
        ${SF_CHORD}
        void main(){
          float ax = abs(vX);
          /* A hairline rod has room for exactly two terms: the body of the
             material and the wall where it turns away. A core term at this
             width IS the hairline the ribbon was built to replace, drawn
             inside its own replacement. */
          float body = pow(max(0.0, 1.0 - ax * ax), 1.3);
          float rim  = smoothstep(0.55, 0.92, ax) * (1.0 - smoothstep(0.92, 1.0, ax));
          vec3 col = mix(u_bg, chord(vPal, vGT, 0.08 + 0.30 * rim), vF);
          float fr = (abs(vS - 1.0) < 0.5) ? u_frag : 0.0;
          float a = (body * 0.11 + rim * 0.46) * vA * (0.46 + 0.48 * vD) * vF
                  * (1.0 - 0.62 * fr) * (0.86 + 0.30 * u_web);
          gl_FragColor = vec4(col, a);
        }`,
    })),
  );
  mRods.frustumCulled = false;
  mRods.renderOrder = 2;
  stations.add(mRods);

  /* ── 2d. THE JUNCTIONS AND THE CENTRE: A DOT WITH AN OUTER CIRCLE ─────────
     What the five lit passes were for. A junction was a hot core inside an
     energy volume inside a glass housing, and the centre the same object one
     size up; drawn flat, that object is a dot with a ring around it — the
     white middle, the chord in the gap, and the housing's silhouette as the
     circle.

     SIZED IN WORLD UNITS, which is the one thing that had to be got right.
     The 42 shell beads above are a TEXTURE and keep their screen size (a
     texture that scales to a quarter of a pixel is gone); a junction is a
     fixed fraction of its own hull in the reference, so it is projected like
     geometry — `worldR * viewportHeight * P[1][1] / 2 / distance` is exactly
     how many pixels a sphere of that radius covers. Clamped at the top, or the
     nearest station's centre is a dinner plate. */
  const kPos: number[] = [], kCtr: number[] = [], kNd: number[] = [];
  const kKd: number[] = [], kPal: number[] = [], kCx: number[] = [], kLoc: number[] = [];
  for (let s = 0; s < STATION_COUNT; s++) {
    const c = STATIONS[s], r = RADII[s], ph = (s * 1.7) % 6.283;
    for (const v of CORNERS0) {
      kPos.push(v.x * r, v.y * r, v.z * r);
      kCtr.push(c.x, c.y, c.z);
      kNd.push(ph, 0, s);
      kKd.push(1, CLUSTER.FRAME_BEAD_R * r);
      kLoc.push(v.x, v.y, v.z);
      pushChord(kPal, kCx, s);
    }
    kPos.push(0, 0, 0);
    kCtr.push(c.x, c.y, c.z);
    kNd.push(ph, 0, s);
    kKd.push(2, CLUSTER.CORE_SHELL_R * r);
    kLoc.push(0, 0, 0);
    pushChord(kPal, kCx, s);
  }
  const gNode = track(new THREE.BufferGeometry());
  gNode.setAttribute('position', new THREE.Float32BufferAttribute(kPos, 3));
  gNode.setAttribute('ctr', new THREE.Float32BufferAttribute(kCtr, 3));
  gNode.setAttribute('nd', new THREE.Float32BufferAttribute(kNd, 3));
  //: .x is which population (1 a junction, 2 the centre), .y its world radius
  gNode.setAttribute('kd', new THREE.Float32BufferAttribute(kKd, 2));
  gNode.setAttribute('cpal', new THREE.Float32BufferAttribute(kPal, 4));
  gNode.setAttribute('ccx', new THREE.Float32BufferAttribute(kCx, 4));
  gNode.setAttribute('cloc', new THREE.Float32BufferAttribute(kLoc, 3));

  const mNode = new THREE.Points(
    gNode,
    track(new THREE.ShaderMaterial({
      uniforms: u,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: /* glsl */ `
        attribute vec3 ctr; attribute vec3 nd; attribute vec2 kd;
        attribute vec4 cpal; attribute vec4 ccx; attribute vec3 cloc;
        varying float vD; varying float vA; varying float vF; varying float vK;
        ${SF_CVAR}
        uniform float u_t, u_lit, u_frag, u_web; uniform vec2 u_res;
        ${SPIN}
        ${SF_FOG}
        ${SF_GRAD}
        ${SF_CSET}
        void main(){
          vK = kd.x;
          setChord(cpal, ccx, cloc);
          float fr = (abs(nd.z - 1.0) < 0.5) ? u_frag : 0.0;
          vec3 p = ctr + spin(position, nd.x, u_t * (1.0 - 0.55 * fr));
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          float dist = -mv.z;
          vD = clamp(1.0 - dist / 46.0, 0.0, 1.0);
          vF = fogOf(dist);
          // station 01 lights up on arrival, 02 dims as it comes apart, the
          // finale brings every station back — the same two uniforms the shell
          // beads read, so a junction cannot be lit while its cage is not
          float lit = (abs(nd.z) < 0.5) ? smoothstep(0.0, 0.6, u_lit) : 1.0;
          vA = lit * (1.0 - 0.88 * fr) * (0.85 + 0.45 * u_web);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = clamp(kd.y * u_res.y * projectionMatrix[1][1]
                               / max(dist, 0.25), 2.0, 96.0);
        }`,
      fragmentShader: /* glsl */ `
        varying float vD; varying float vA; varying float vF; varying float vK;
        ${SF_CVAR}
        ${SF_HUES}
        uniform vec3 u_bg;
        ${SF_ROLE}
        ${SF_CHORD}
        void main(){
          float d = length(gl_PointCoord - 0.5);
          if (d > 0.5) discard;
          /* aa widens with distance: crisp edges, not one smoothstep from the
             middle out — that is a blur, and a blur reads as a smudge at every
             size. */
          float aa = 0.02 + 0.10 * (1.0 - vD);
          float core = 1.0 - smoothstep(0.30 - aa, 0.30 + aa, d);
          float ring = smoothstep(0.33, 0.46, d)
                     * (1.0 - smoothstep(0.46, 0.46 + aa * 2.0, d));
          float halo = pow(max(0.0, 1.0 - d * 2.0), 2.6);
          /* the white stops at the DOT: in both references you read a white
             middle through a coloured volume, and whitening the volume is what
             turns a node into a pale blob. The centre is hotter than a
             junction and it is still not a sun — the middle of a cage is dark
             in both. */
          vec3 col = chord(vPal, vGT, 0.0);
          col = mix(col, vec3(1.0), core * (0.52 + 0.34 * step(1.5, vK)) + ring * 0.24);
          col = mix(u_bg, col, vF);
          float a = (core * 0.62 + ring * 0.72 + halo * 0.22)
                  * (0.40 + 0.55 * vD) * vA * vF;
          gl_FragColor = vec4(col, a);
        }`,
    })),
  );
  mNode.frustumCulled = false;
  mNode.renderOrder = 4;
  stations.add(mNode);

  /* ── 3. the link: a tube along the same curve, drawn by scroll ───────────
     TubeGeometry parameterises by ARC LENGTH, but scroll progress is in
     station space (station i at i/5). getUtoTmapping is the inverse, so every
     vertex carries the station-space t of its ring and the reveal compares
     like with like. Getting this wrong makes the link lag the camera by a
     different amount on every segment. */
  // Radius 0.05 was a hairline that read as an artefact rather than a spine.
  // This is the trunk of the tree; it has to carry that.
  const TUBULAR = 320;
  const gTube = track(new THREE.TubeGeometry(CURVE, TUBULAR, 0.09, 6, false));
  const uv = gTube.getAttribute('uv');
  const tMap = new Map<number, number>();
  const aT = new Float32Array(uv.count);
  for (let i = 0; i < uv.count; i++) {
    const uu = uv.getX(i);
    let t = tMap.get(uu);
    if (t === undefined) { t = CURVE.getUtoTmapping(uu, 0); tMap.set(uu, t); }
    aT[i] = t;
  }
  gTube.setAttribute('aT', new THREE.BufferAttribute(aT, 1));

  /* Where the trunk is INSIDE a cage. The curve runs through every station
     centre, so the tube skewered each hull and came out the far side — the link
     never read as arriving anywhere. 1 at a centre, 0 at that cage's surface;
     the fragment shader fades it out over the outer third, so the trunk stops on
     the wireframe. Measured once at build, not per frame, and it is measured
     against RADII rather than against the geometry — so the swap to a subdivided
     icosahedron, whose vertices sit at circumradius 1 exactly as the previous
     solid's did, leaves this correct with nothing to change. */
  const tPos = gTube.getAttribute('position');
  const aIn = new Float32Array(tPos.count);
  const tv = new THREE.Vector3();
  for (let i = 0; i < tPos.count; i++) {
    tv.fromBufferAttribute(tPos, i);
    let inside = 0;
    for (let s = 0; s < STATION_COUNT; s++) {
      inside = Math.max(inside, 1 - Math.min(1, tv.distanceTo(STATIONS[s]) / RADII[s]));
    }
    aIn[i] = inside;
  }
  gTube.setAttribute('aIn', new THREE.BufferAttribute(aIn, 1));

  const mTube = new THREE.Mesh(
    gTube,
    track(new THREE.ShaderMaterial({
      uniforms: u,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      vertexShader: /* glsl */ `
        attribute float aT; attribute float aIn;
        varying float vT; varying float vD; varying float vIn;
        void main(){
          vT = aT; vIn = aIn;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          vD = clamp(1.0 - (-mv.z) / 46.0, 0.0, 1.0);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        varying float vT; varying float vD; varying float vIn;
        uniform vec3 u_acc, u_acc2;
        uniform float u_t, u_prog, u_pkt, u_web;
        // a bright head with a short tail behind it, like the particles
        // connections.py runs along its edges
        float packet(float at, float head, float w){
          float d = at - head;
          float dot_ = pow(max(0.0, 1.0 - abs(d) * (34.0 / w)), 2.0);
          float tail = d < 0.0 ? pow(max(0.0, 1.0 + d * (9.0 / w)), 3.0) * 0.35 : 0.0;
          return dot_ + tail;
        }
        void main(){
          // The dash: the link only exists behind the camera's progress.
          float drawn = smoothstep(u_prog + 0.002, u_prog - 0.03, vT);
          // …with the bright packet riding the drawing front.
          float head = pow(max(0.0, 1.0 - abs(vT - u_prog) * 26.0), 2.0);
          // Station 05 is about what the links carry, so the packets fatten there.
          float w = 1.0 + 2.2 * u_pkt;
          float sp = 0.055;
          float data = packet(vT, fract(u_t * sp), w)
                     + packet(vT, fract(u_t * sp * 0.63 + 0.47), w) * 0.7;
          data *= drawn;
          vec3 col = mix(u_acc, mix(u_acc2, vec3(1.0), 0.5), clamp(data + head, 0.0, 1.0));
          float a = drawn * (0.20 + 0.18 * vD + 0.62 * data) + head * 0.6;
          a *= (0.9 + 0.5 * u_web);
          // The trunk stops ON the solid, not through it.
          a *= 1.0 - smoothstep(0.02, 0.34, vIn);
          // On a reading page the trunk is the loudest thing in the scene and it
          // runs straight through the middle of the column. The constellation and
          // its chords carry the "connected" reading on their own there.
          gl_FragColor = vec4(col, a);
        }`,
    })),
  );
  mTube.frustumCulled = false;
  mTube.renderOrder = 1;
  stations.add(mTube);

  /* ── 4. station 03: the node blooms into a live graph ────────────────────
     Children on the deterministic golden-angle spiral, links solving into
     place — the same layout rule as the app's own field, for the same reason:
     a layout that reshuffles on reload reads as noise. */
  const MEM_N = 26;
  const memC = STATIONS[2];
  const kids: THREE.Vector3[] = [];
  for (let i = 0; i < MEM_N; i++) {
    const ang = i * 2.399963;
    const rad = 2.6 + 3.4 * Math.sqrt(i / MEM_N);
    kids.push(new THREE.Vector3(
      memC.x + Math.cos(ang) * rad,
      memC.y + Math.sin(ang) * rad * 0.74,
      memC.z + ((i * 7) % 9) * 0.42 - 1.6,
    ));
  }

  const memVert = /* glsl */ `
    attribute vec3 home; attribute float kid;
    varying float vK; varying float vD;
    // u_res is used only by the Points variant's appended gl_PointSize line, but
    // it has to be declared here — that line is concatenated onto this source.
    uniform float u_mem, u_t; uniform vec2 u_res;
    void main(){
      vK = kid;
      // each child arrives in turn, travelling out from the parent node
      float g = clamp((u_mem - kid * 0.42) / 0.58, 0.0, 1.0);
      g = g * g * (3.0 - 2.0 * g);
      vec3 base = vec3(${memC.x.toFixed(3)}, ${memC.y.toFixed(3)}, ${memC.z.toFixed(3)});
      vec3 p = mix(base, home, g);
      p.y += sin(u_t * 0.5 + kid * 6.0) * 0.12 * g;
      vec4 mv = modelViewMatrix * vec4(p, 1.0);
      vD = clamp(1.0 - (-mv.z) / 46.0, 0.0, 1.0);
      gl_Position = projectionMatrix * mv;`;

  const kp: number[] = [], kh: number[] = [], kk: number[] = [];
  kids.forEach((k, i) => { kp.push(0, 0, 0); kh.push(k.x, k.y, k.z); kk.push(i / MEM_N); });
  const gMem = track(new THREE.BufferGeometry());
  gMem.setAttribute('position', new THREE.Float32BufferAttribute(kp, 3));
  gMem.setAttribute('home', new THREE.Float32BufferAttribute(kh, 3));
  gMem.setAttribute('kid', new THREE.Float32BufferAttribute(kk, 1));
  const mMem = new THREE.Points(gMem, track(new THREE.ShaderMaterial({
    uniforms: u,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `${memVert}
      gl_PointSize = (3.0 + 4.0 * vD) * (u_res.y / 900.0 + 0.6);
    }`,
    fragmentShader: /* glsl */ `
      varying float vK; varying float vD;
      uniform vec3 u_acc, u_acc2; uniform float u_mem;
      void main(){
        float d = length(gl_PointCoord - 0.5);
        if (d > 0.5) discard;
        vec3 col = mix(u_acc, u_acc2, vK);
        col = mix(col, vec3(1.0), smoothstep(0.26, 0.0, d) * 0.5);
        gl_FragColor = vec4(col, (1.0 - smoothstep(0.30, 0.5, d)) * 0.75 * vD * u_mem);
      }`,
  })));
  mMem.frustumCulled = false;
  mMem.renderOrder = 4;
  stations.add(mMem);

  // links: parent→child, plus a chord to a near neighbour, so the field reads
  // as a graph rather than a starburst
  const lp: number[] = [], lh: number[] = [], lk: number[] = [];
  const pushEnd = (v: THREE.Vector3, i: number) => {
    lp.push(0, 0, 0); lh.push(v.x, v.y, v.z); lk.push(i / MEM_N);
  };
  kids.forEach((k, i) => {
    lp.push(0, 0, 0); lh.push(memC.x, memC.y, memC.z); lk.push(i / MEM_N);
    pushEnd(k, i);
    const j = (i + 3) % MEM_N;
    pushEnd(k, i); pushEnd(kids[j], Math.max(i, j));
  });
  const gMemLink = track(new THREE.BufferGeometry());
  gMemLink.setAttribute('position', new THREE.Float32BufferAttribute(lp, 3));
  gMemLink.setAttribute('home', new THREE.Float32BufferAttribute(lh, 3));
  gMemLink.setAttribute('kid', new THREE.Float32BufferAttribute(lk, 1));
  const mMemLink = new THREE.LineSegments(gMemLink, track(new THREE.ShaderMaterial({
    uniforms: u,
    transparent: true, depthWrite: false,
    vertexShader: `${memVert} }`,
    fragmentShader: /* glsl */ `
      varying float vK; varying float vD;
      uniform vec3 u_acc, u_acc2; uniform float u_mem;
      void main(){
        gl_FragColor = vec4(mix(u_acc, u_acc2, vK), 0.30 * vD * u_mem);
      }`,
  })));
  mMemLink.frustumCulled = false;
  mMemLink.renderOrder = 3;
  stations.add(mMemLink);

  /* ── 5. framed screenshots: a node face becomes a real capture ─────────────
     The strongest moment on the page, so it is DATA rather than one hand-built
     object — three stations carry one, each keyed to its own arrival. The DOM
     copies stay in Stations.tsx as the no-WebGL fallback and are hidden by
     `html.journey-on .shot-fallback` once GL has painted, so every picture is on
     the page exactly once and its alt text never goes missing. */
  const SHOTS = [
    // Beside the memory field rather than over it: station 03's own children
    // spiral out to about six units.
    { station: 2, src: '/img/gui-memory.png', w: 5.2, h: 3.25, at: [2.9, -0.7, 2.2] },
    { station: 3, src: '/img/tui-sessions.png', w: 6.4, h: 4.0, at: [0.4, -0.2, 2.4] },
    { station: 4, src: '/img/gui-usage.png', w: 6.0, h: 3.75, at: [0.2, -0.3, 2.4] },
  ] as const;

  const loader = new THREE.TextureLoader();
  const shots = SHOTS.map(({ station, src, w, h, at }) => {
    const c = STATIONS[station];
    const mat = track(new THREE.MeshBasicMaterial({
      transparent: true, opacity: 0, depthWrite: false, toneMapped: false,
    }));
    loader.load(src, (tex) => {
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.minFilter = THREE.LinearFilter;
      tex.generateMipmaps = false;
      mat.map = tex;
      mat.needsUpdate = true;
      disposables.push(tex);
    });
    const plane = new THREE.Mesh(track(new THREE.PlaneGeometry(w, h)), mat);
    plane.position.set(c.x + at[0], c.y + at[1], c.z + at[2]);
    plane.renderOrder = 5;
    stations.add(plane);

    const corners = [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]];
    const fp: number[] = [];
    for (let i = 0; i < 4; i++) {
      const a = corners[i], b = corners[(i + 1) % 4];
      fp.push(a[0], a[1], 0, b[0], b[1], 0);
    }
    const gFrame = track(new THREE.BufferGeometry());
    gFrame.setAttribute('position', new THREE.Float32BufferAttribute(fp, 3));
    // Its own arrival uniform: one shared `u_shot` would fade all three together.
    const uniform = { value: 0 };
    const frame = new THREE.LineSegments(gFrame, track(new THREE.ShaderMaterial({
      uniforms: { u_acc: u.u_acc, u_k: uniform },
      transparent: true, depthWrite: false,
      vertexShader: `void main(){ gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: /* glsl */ `
        uniform vec3 u_acc; uniform float u_k;
        void main(){ gl_FragColor = vec4(u_acc, 0.85 * u_k); }`,
    })));
    frame.position.copy(plane.position);
    frame.renderOrder = 6;
    stations.add(frame);

    return { station, mat, plane, frame, uniform };
  });

  /* ── 6. the finale: chords between every station, resolving ──────────────── */
  const cp: number[] = [], ct: number[] = [];
  const cd = new THREE.Vector3();
  for (let i = 0; i < STATION_COUNT; i++) {
    // Adjacent pairs included: the trunk only exists behind the camera's
    // progress, so without them the constellation had visible gaps between
    // neighbours until you had scrolled past them.
    for (let j = i + 1; j < STATION_COUNT; j++) {
      cd.copy(STATIONS[j]).sub(STATIONS[i]).normalize();
      // Surface to surface, not centre to centre — the same defect the section
      // chain already fixed, and the reason these ran through both hulls and out
      // the far side. A normalized subdivided icosahedron has every one of its
      // 42 vertices at circumradius 1, exactly as the platonic solid it replaced
      // did, so RADII is still where the wireframe is at every spin angle.
      const a = STATIONS[i].clone().addScaledVector(cd, RADII[i]);
      const b = STATIONS[j].clone().addScaledVector(cd, -RADII[j]);
      cp.push(a.x, a.y, a.z, b.x, b.y, b.z);
      ct.push(0, 1);
    }
  }
  const gWeb = track(new THREE.BufferGeometry());
  gWeb.setAttribute('position', new THREE.Float32BufferAttribute(cp, 3));
  gWeb.setAttribute('lt', new THREE.Float32BufferAttribute(ct, 1));
  const mWeb = new THREE.LineSegments(gWeb, track(new THREE.ShaderMaterial({
    uniforms: u, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: /* glsl */ `
      attribute float lt; varying float vT; varying float vD;
      void main(){
        vT = lt;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vD = clamp(1.0 - (-mv.z) / 46.0, 0.0, 1.0);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      varying float vT; varying float vD;
      uniform vec3 u_acc, u_acc2; uniform float u_web, u_t;
      void main(){
        float pk = pow(max(0.0, 1.0 - abs(vT - fract(u_t * 0.09)) * 12.0), 2.0);
        vec3 col = mix(u_acc, u_acc2, vT);
        // Present from the first frame, not only at the finale. These chords are
        // what make six solids read as ONE connected structure — a skill tree
        // rather than six separate objects that happen to share a page. The
        // finale still resolves them: it is the difference between a faint
        // lattice you sense and one you are looking at.
        gl_FragColor = vec4(col, (0.10 + 0.34 * pk) * vD * (0.24 + 0.76 * u_web));
      }`,
  })));
  mWeb.frustumCulled = false;
  mWeb.renderOrder = 1;
  stations.add(mWeb);

  /* ── 7. ONE CLUSTER PER SECTION, arriving from the background ─────────────
     Not a background field, and not one object that morphs. Every section owns
     its own cluster — the same geodesic cage holding the same interior
     population the six stations wear, sized by that section's weight and
     coloured off the same five-stop ladder. The cluster you are reading is in
     the foreground beside the copy; the others wait behind it, further back the
     further away their section is, and each travels forward as you reach it.

     They are the SAME language as the stations on purpose. A page whose sections
     were platonic solids while the landing page's stations were clusters said
     two different things about what the project is — and the study's whole point
     is that a solid says "here is a thing" while a cluster says "here is a thing
     made of things, and it is connected to other things".

     All of it happens in the vertex shader from one uniform (`u_sec`), and each
     of the five layers is one merged buffer — so N sections cost five draw calls
     whatever N is, and nothing is animated on the CPU. The group is re-anchored
     to the camera every frame, which makes these positions CAMERA-SPACE: the
     clusters hold their place on screen no matter what the journey camera is
     doing. */
  const secGroup = new THREE.Group();
  group.add(secGroup);

  /** Where a section's solid goes, and how big it is.
   *
   *  The answer comes from that section's `.spine-slot` — an empty element the
   *  page's own grid has already positioned in the space it wants to give the
   *  solid. The previous version derived a position from the frustum instead,
   *  which cannot know where the copy is: the solid sat at the exact middle of
   *  the viewport while its section was half a screen above it, landed in the
   *  margin outside a `max-w-4xl` column on /blog and /faq, and had to be
   *  switched off entirely on the pages whose prose fills the width.
   *
   *  So the section index decides only DEPTH — which solid is at the focal plane
   *  and how far behind it the rest sit. Every screen coordinate is the slot's.
   *
   *  Shared by the edges, the joints and the chain, so none of them can disagree
   *  about where a solid is. `arrangeAt()` in this file is its CPU mirror, for
   *  the hit test, and reads the same constants. */
  const PLACE = /* glsl */ `
    uniform vec4 u_slot[${MAX_SLOTS}];
    uniform float u_sec, u_t, u_scroll, u_vw, u_vh, u_halfW, u_halfH, u_layout;

    vec4 slotOf(float sid){
      return u_slot[int(sid + 0.5)];
    }

    // o.xy: lateral offset from the slot centre, in focal-plane units.
    // o.z: how far BEHIND the focal plane this section sits.
    // sx is the slot own x, so a layout can push a section OUTWARD rather
    // than leaving it in the half the copy is using.
    vec3 arrange(float d, float ad, float r, float sx){
      vec2 o = vec2(0.0);
      // Flat at zero, steep after half a section. See RECEDE.
      float fall = ad * ad / (0.6 + ad) * ${FOCAL.toFixed(1)};
      float z = 0.0;
${LAYOUTS.map((n, i) =>
  `      ${i ? 'else if' : 'if'} (u_layout < ${(i + 0.5).toFixed(1)}) z = ${RECEDE[n].toFixed(2)} * fall;`,
).join('\n')}
      // beside — the copy and the solid trade sides, so a NEIGHBOUR's slot is
      // the half you are currently reading. Push it outward as it leaves.
      if (u_layout < 0.5) o.x = sx * min(ad, 2.0) * 0.35;
      // depth — nested shells: same slot, so the recession alone separates them.
      // orbit — the read and coming sections circle the slot rather than sitting
      // still behind it.
      if (abs(u_layout - 3.0) < 0.5) {
        float a = u_t * 0.42 + d * 2.1;
        o = vec2(cos(a), sin(a)) * r * 0.55 * min(ad, 1.0);
      }
      // triad — a slow sway, so three solids in a triangle are not a diagram.
      if (abs(u_layout - 4.0) < 0.5) o.x = sin(u_t * 0.30 + d * 2.0) * r * 0.18;
      return vec3(o, z);
    }

    vec3 place(vec3 local, float sid, float w){
      vec4 sl = slotOf(sid);
      float d = sid - u_sec;
      float ad = abs(d);
      // Slot rect — CSS pixels, DOCUMENT space — to the focal plane. u_scroll is
      // the only part of this that changes per frame, which is why the rects are
      // uploaded on measure and never per frame.
      float x = ((sl.x / u_vw) * 2.0 - 1.0) * u_halfW;
      float y = (1.0 - ((sl.y - u_scroll) / u_vh) * 2.0) * u_halfH;
      float r = (sl.z / u_vh) * 2.0 * u_halfH * w;
      vec3 a = arrange(d, ad, r, x);
      // The slot is a SCREEN-space anchor, so the centre is scaled by its own
      // depth to cancel the perspective divide. Without this a receding solid
      // slides toward the middle of the frame and leaves the box the page gave
      // it — which is exactly what "the section solids do not anchor" was.
      // Receding then does only what it should: make it smaller.
      float depth = ${FOCAL.toFixed(1)} + a.z;
      float k = depth / ${FOCAL.toFixed(1)};
      return vec3((x + a.x) * k, (y + a.y) * k, -depth) + local * r;
    }

    /** The radius the solid is actually DRAWN at — what the chain has to start
     *  from if its ends are to sit on a surface rather than in a centre. */
    float drawnRadius(float sid, float w){
      vec4 sl = slotOf(sid);
      return (sl.z / u_vh) * 2.0 * u_halfH * w;
    }`;

  /** The unit cage a section's cluster is built from — the SAME geometry the six
   *  stations wear, at radius 1, so `place()` scaling it by the slot radius is
   *  the only difference between the two. 42 vertices, 120 edges, 80 faces. */
  const sBase = new THREE.IcosahedronGeometry(1, 1);
  const sWire = new THREE.EdgesGeometry(sBase);
  const swp = sWire.getAttribute('position');
  const S_EDGE = Array.from({ length: swp.count }, (_, i) =>
    new THREE.Vector3().fromBufferAttribute(swp, i));
  sBase.dispose();
  sWire.dispose();
  // The same deduplicated 42, from the same helper the stations use. Two
  // implementations of "the corners of the cage" is two chances to disagree
  // about how many there are.
  const S_VERT = verts;

  const gSecE = track(new THREE.BufferGeometry());
  const gSecJ = track(new THREE.BufferGeometry());
  const gSecM = track(new THREE.BufferGeometry());

  const secUniforms = {
    uniforms: u,
    transparent: true,
    depthWrite: false,
    depthTest: false,
    blending: THREE.AdditiveBlending,
  } as const;

  const mSecE = new THREE.LineSegments(gSecE, track(new THREE.ShaderMaterial({
    ...secUniforms,
    vertexShader: /* glsl */ `
      attribute float sid; attribute float sw;
      attribute vec4 spal; attribute vec4 scx;
      varying float vA;
      ${SF_CVAR}
      uniform float u_span;
      ${SPIN}
      ${PLACE}
      ${SF_GRAD}
      ${SF_CSET}
      void main(){
        float ad = abs(sid - u_sec);
        // position is already in UNIT hull space here — place() is what scales
        // it to the slot — so it is exactly what gradT wants
        setChord(spal, scx, position);
        // Visible for a few sections either side, brightest when current. How
        // many is per layout: a rail of short rows scrolls through five in the
        // time a full-height page covers one.
        vA = smoothstep(u_span, 0.0, ad);
        vec3 local = spin(position, sid * 1.7, u_t * 0.55);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(place(local, sid, sw), 1.0);
      }`,
    fragmentShader: /* glsl */ `
      varying float vA;
      ${SF_CVAR}
      ${SF_HUES}
      uniform float u_wash;
      ${SF_ROLE}
      ${SF_CHORD}
      // A strut is DIMMER than a node and DULLER than nothing else in the
      // layer except the chain — the same ladder the stations keep: nodes
      // brightest, struts filaments with presence, links almost background.
      void main(){ gl_FragColor = vec4(chord(vPal, vGT, 0.0), (0.10 + 0.42 * vA * vA) * u_wash); }`,
  })));
  mSecE.frustumCulled = false;
  mSecE.renderOrder = 8;
  secGroup.add(mSecE);

  /* The joint's vertex stage, shared by the white core and by its halo — the
     halo is the SAME 42 points per section drawn a second time, wider and
     fainter, over the SAME buffer. One more draw call, not one more byte, and
     it is how this layer gets a glow with no post-processing: bloom went into
     this scene and came straight back out, because these are raw ShaderMaterials
     writing final display values and a pass that re-encodes them lifts the dark
     tones instead of blooming the bright ones. See the note in Canvas.tsx.
     `k` is the size multiplier. */
  const secJointVert = (k: number) => /* glsl */ `
    attribute float sid; attribute float sw;
    attribute vec4 spal; attribute vec4 scx;
    varying float vA;
    ${SF_CVAR}
    uniform float u_span; uniform vec2 u_res;
    ${SPIN}
    ${PLACE}
    ${SF_GRAD}
    ${SF_CSET}
    void main(){
      float ad = abs(sid - u_sec);
      setChord(spal, scx, position);
      vA = smoothstep(u_span, 0.0, ad);
      vec3 local = spin(position, sid * 1.7, u_t * 0.55);
      gl_Position = projectionMatrix * modelViewMatrix * vec4(place(local, sid, sw), 1.0);
      gl_PointSize = (1.6 + 2.6 * vA) * (u_res.y / 900.0 + 0.6) * ${k.toFixed(2)};
    }`;

  const mSecJ = new THREE.Points(gSecJ, track(new THREE.ShaderMaterial({
    ...secUniforms,
    vertexShader: secJointVert(1),
    fragmentShader: /* glsl */ `
      varying float vA;
      ${SF_CVAR}
      ${SF_HUES}
      uniform float u_wash;
      ${SF_ROLE}
      ${SF_CHORD}
      void main(){
        float d = length(gl_PointCoord - 0.5);
        if (d > 0.5) discard;
        /* WHITE core inside a COLOURED halo, exactly as a station's joint —
           the reference image's nodes are white points sitting in a coloured
           bloom, not coloured dots with a highlight. The old joint mixed 50%
           toward white over the inner third and read as a pale accent. */
        float core = smoothstep(0.20, 0.0, d);
        float wide = pow(max(0.0, 1.0 - d * 2.0), 2.2);
        vec3 col = mix(chord(vPal, vGT, 0.0), vec3(1.0), core * 0.75);
        // Nodes are the brightest thing in the layer; struts and the chain are
        // scaled under them.
        gl_FragColor = vec4(col, (core * 0.85 + wide * 0.30) * (0.25 + 0.7 * vA) * u_wash);
      }`,
  })));
  mSecJ.frustumCulled = false;
  mSecJ.renderOrder = 9;
  secGroup.add(mSecJ);

  // …and the halo: the same points, three times as wide, coloured, additive,
  // faint. The glow is a second Points, never a pass.
  const mSecH = new THREE.Points(gSecJ, track(new THREE.ShaderMaterial({
    ...secUniforms,
    vertexShader: secJointVert(3.2),
    fragmentShader: /* glsl */ `
      varying float vA;
      ${SF_CVAR}
      ${SF_HUES}
      uniform float u_wash;
      ${SF_ROLE}
      ${SF_CHORD}
      void main(){
        float d = length(gl_PointCoord - 0.5);
        if (d > 0.5) discard;
        float g = pow(max(0.0, 1.0 - d * 2.0), 2.2);
        gl_FragColor = vec4(chord(vPal, vGT, 0.0), g * 0.16 * (0.25 + 0.7 * vA) * u_wash);
      }`,
  })));
  mSecH.frustumCulled = false;
  mSecH.renderOrder = 8;
  secGroup.add(mSecH);

  /* The interior population — the trait that makes this a cluster rather than a
     cage. `moteLocals` returns offsets for a UNIT hull, which is exactly what
     `place()` wants: a section's radius is a slot measured at runtime, so there
     is nothing to bake in. One merged Points for the whole page. */
  const mSecM = new THREE.Points(gSecM, track(new THREE.ShaderMaterial({
    ...secUniforms,
    vertexShader: /* glsl */ `
      attribute float sid; attribute float sw;
      attribute vec4 spal; attribute vec4 scx;
      attribute float mh;
      varying float vA; varying float vH;
      ${SF_CVAR}
      uniform float u_span; uniform vec2 u_res;
      ${SPIN}
      ${PLACE}
      ${SF_GRAD}
      ${SF_CSET}
      void main(){
        setChord(spal, scx, position); vH = mh;
        vA = smoothstep(u_span, 0.0, abs(sid - u_sec));
        vec3 local = spin(position, sid * 1.7, u_t * 0.55);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(place(local, sid, sw), 1.0);
        gl_PointSize = (0.9 + 1.5 * vA) * (u_res.y / 900.0 + 0.6);
      }`,
    fragmentShader: /* glsl */ `
      varying float vA; varying float vH;
      ${SF_CVAR}
      ${SF_HUES}
      uniform float u_wash;
      ${SF_ROLE}
      ${SF_CHORD}
      void main(){
        float d = length(gl_PointCoord - 0.5);
        if (d > 0.5) discard;
        /* THE INTERNAL NETWORK IS FOUR POPULATIONS, in the split
           cluster_spec.py holds and all three renderers read: most of it cool,
           a quarter magenta, a tenth gold, a few white-hot. Gold is an ACCENT,
           never the dominant colour. */
        vec3 col = chord(vPal, clamp(mix(0.05, 0.55, vH / ${CLUSTER.FILAMENT_MIX[0]}), 0.0, 1.0), 0.0);
        col = mix(col, roleCol(2.0), step(${CLUSTER.FILAMENT_MIX[0]}, vH) * 0.85);
        col = mix(col, u_warn, step(${CLUSTER.FILAMENT_MIX[1]}, vH) * 0.9);
        col = mix(col, vec3(1.0), step(${CLUSTER.FILAMENT_MIX[2]}, vH) * 0.9);
        gl_FragColor = vec4(col,
          (1.0 - smoothstep(0.1, 0.5, d)) * (0.10 + 0.26 * vA) * u_wash);
      }`,
  })));
  mSecM.frustumCulled = false;
  mSecM.renderOrder = 8;
  secGroup.add(mSecM);

  /* The chain. One segment per linked pair, each end placed by the same
     `place()` the solids use — so the link cannot drift away from what it links,
     whatever the layout is. This is what makes the sections read as a tree rather
     than as a row of separate objects, and it is why the zig-zag on /changelog
     needed no code at all: the slots moved, the chain followed. */
  const gSecL = track(new THREE.BufferGeometry());
  const mSecL = new THREE.LineSegments(gSecL, track(new THREE.ShaderMaterial({
    ...secUniforms,
    vertexShader: /* glsl */ `
      attribute float sid; attribute float sw;
      attribute float osid; attribute float osw;
      attribute vec4 spal; attribute vec4 scx;
      varying float vA;
      ${SF_CVAR}
      uniform float u_span;
      ${SPIN}
      ${PLACE}
      ${SF_GRAD}
      ${SF_CSET}
      void main(){
        // each END carries its own cluster's chord, so the segment interpolates
        // from one to the other. The position is a placeholder here (both ends
        // are computed below), so the gradient walk is evaluated at a fixed
        // mid-hull radius rather than at a point that does not exist yet.
        setChord(spal, scx, vec3(0.0, 0.62, 0.0));
        vA = smoothstep(u_span + 0.2, 0.0, abs(sid - u_sec));
        // Centre to centre is what made these look wrong: the line ran straight
        // through both solids and out the other side. Each end starts on its own
        // solid's SURFACE instead — pulled toward the far centre by the radius it
        // is actually drawn at, so the join stays seamless at every size, depth
        // and layout.
        vec3 a = place(vec3(0.0), sid, sw);
        vec3 b = place(vec3(0.0), osid, osw);
        vec3 dir = normalize(b - a);
        gl_Position = projectionMatrix * modelViewMatrix
          * vec4(a + dir * drawnRadius(sid, sw) * 1.04, 1.0);
      }`,
    fragmentShader: /* glsl */ `
      varying float vA;
      ${SF_CVAR}
      ${SF_HUES}
      uniform float u_wash;
      ${SF_ROLE}
      ${SF_CHORD}
      // The dullest thing in the layer. An inter-cluster link is thinner AND
      // duller than a hull strut; WebGL line width is 1px whatever you ask for,
      // so "thinner" is spent as alpha — the right currency anyway.
      void main(){ gl_FragColor = vec4(chord(vPal, vGT, 0.0), (0.06 + 0.30 * vA) * u_wash); }`,
  })));
  mSecL.frustumCulled = false;
  mSecL.renderOrder = 7;
  secGroup.add(mSecL);

  /** Rebuild both buffers for a page's sections. Called once per page, not per
   *  frame — the weights only change when the document does. */
  let radii: number[] = [];
  const buildSections = (weights: number[], layout: LayoutName) => {
    const n = Math.min(weights.length, MAX_SLOTS);
    secGroup.visible = n > 1;
    if (!secGroup.visible) return;

    const hi = Math.max(1, ...weights);
    // A one-paragraph section still gets a solid you can see; it is just not the
    // biggest one on the page. sqrt so a very long section does not dwarf
    // everything else in the document.
    // Normalised 0..1: this is how much of its SLOT the solid fills, so a weight
    // decides importance and the page's own grid decides the space. Nothing here
    // knows about viewports.
    const rad = weights.slice(0, n).map((x) => 0.52 + 0.48 * Math.sqrt(Math.max(0, x) / hi));
    radii = rad;

    const ep: number[] = [], ei: number[] = [], ew: number[] = [], eh: number[] = [];
    const jp: number[] = [], ji: number[] = [], jw: number[] = [], jh: number[] = [];
    const mp: number[] = [], mi: number[] = [], mw: number[] = [];
    const mth: number[] = [], mhash: number[] = [];
    const ecx: number[] = [], jcx: number[] = [], mcx: number[] = [];
    /* A section's cluster wears a CHORD, exactly as a station's does — four
       role indices and a gradient axis, pushed per vertex. `eh` used to be one
       tone, i.e. one colour for a whole cluster, which is the rule the brief
       calls the most important and the one every renderer here broke. */
    const chord4 = (out: number[], cxOut: number[], k: number) => {
      const q = chordOf(secSeed(k)), a = axisOf((k * 5) % 7 + 11);
      out.push(q[0], q[1], q[2], q[3]);
      cxOut.push(a[0], a[1], a[2], secSeed(k));
    };
    for (let s = 0; s < n; s++) {
      for (const v of S_EDGE) {
        ep.push(v.x, v.y, v.z); ei.push(s); ew.push(rad[s]); chord4(eh, ecx, s);
      }
      for (const v of S_VERT) {
        jp.push(v.x, v.y, v.z); ji.push(s); jw.push(rad[s]); chord4(jh, jcx, s);
      }
      // The interior. `rad[s]` is already relative — how much of its slot this
      // cluster fills, 0.52..1 — so it is exactly the `q` moteCount wants, and a
      // one-paragraph section holds a hundred motes where the page's longest
      // holds two hundred and fifty.
      const q = moteLocals(moteCount(rad[s]), s);
      for (let k = 0; k < q.length; k += 4) {
        mp.push(q[k], q[k + 1], q[k + 2]);
        mi.push(s); mw.push(rad[s]); chord4(mth, mcx, s); mhash.push(q[k + 3]);
      }
    }
    const set3 = (g: THREE.BufferGeometry, p: number[], i: number[], w: number[],
                  h: number[], cx: number[]) => {
      g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3));
      g.setAttribute('sid', new THREE.Float32BufferAttribute(i, 1));
      g.setAttribute('sw', new THREE.Float32BufferAttribute(w, 1));
      g.setAttribute('spal', new THREE.Float32BufferAttribute(h, 4));
      g.setAttribute('scx', new THREE.Float32BufferAttribute(cx, 4));
    };
    set3(gSecE, ep, ei, ew, eh, ecx);
    set3(gSecJ, jp, ji, jw, jh, jcx);
    set3(gSecM, mp, mi, mw, mth, mcx);
    gSecM.setAttribute('mh', new THREE.Float32BufferAttribute(mhash, 1));

    // The chain: two vertices per link. Each end carries BOTH its own section and
    // the one at the far end, which is what lets the shader start the line on the
    // surface of its own solid rather than at its centre.
    const lp: number[] = [], li: number[] = [], lw: number[] = [];
    const lo: number[] = [], low: number[] = [], lh: number[] = [], lcx: number[] = [];
    /* Each end of the chain carries its OWN cluster's chord, so the line
       interpolates from one to the other exactly as the GUI's conduit does —
       the brief's "the connection inherits colour information from the clusters
       it connects", and the thing a single accent could never say. */
    const push = (self: number, other: number) => {
      lp.push(0, 0, 0);
      li.push(self); lw.push(rad[self]);
      lo.push(other); low.push(rad[other]);
      chord4(lh, lcx, self);
    };
    // Topology is the one thing a layout changes on the CPU. A community is a
    // mesh, not a queue: /community chords all three to each other. Everything
    // else is a chain, because it is a sequence you read in order.
    if (layout === 'triad') {
      for (let a = 0; a < n; a++) for (let b = a + 1; b < n; b++) { push(a, b); push(b, a); }
    } else {
      for (let s = 0; s < n - 1; s++) { push(s, s + 1); push(s + 1, s); }
    }
    gSecL.setAttribute('position', new THREE.Float32BufferAttribute(lp, 3));
    gSecL.setAttribute('sid', new THREE.Float32BufferAttribute(li, 1));
    gSecL.setAttribute('sw', new THREE.Float32BufferAttribute(lw, 1));
    gSecL.setAttribute('osid', new THREE.Float32BufferAttribute(lo, 1));
    gSecL.setAttribute('osw', new THREE.Float32BufferAttribute(low, 1));
    gSecL.setAttribute('spal', new THREE.Float32BufferAttribute(lh, 4));
    gSecL.setAttribute('scx', new THREE.Float32BufferAttribute(lcx, 4));
  };
  secGroup.visible = false;

  /* ── driving it ─────────────────────────────────────────────────────────── */
  const smooth = (x: number) => x * x * (3 - 2 * x);
  const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);

  /** Progress 0..1 → position in station space, with a HOLD at each station.
   *  A continuous glide reads as a library demo; arriving and settling reads as
   *  an exhibition. The camera travels over the middle 56% of each segment and
   *  is parked for the rest, which is what gives that section's DOM content the
   *  screen to itself. */
  function stationSpace(p: number): number {
    const seg = clamp01(p) * (STATION_COUNT - 1);
    const i = Math.min(STATION_COUNT - 2, Math.floor(seg));
    const local = seg - i;
    // Travel over the middle 72%, park for the rest. The first cut travelled
    // over 56% and the hold was long enough that the page felt stopped rather
    // than settled — the camera has to still be arriving while you read the
    // first line.
    return i + smooth(clamp01((local - 0.14) / 0.72));
  }

  /** 1 when parked at station k, falling off as the camera leaves. */
  const near = (s: number, k: number) => smooth(clamp01(1 - Math.abs(s - k) / 0.9));

  const camPos = new THREE.Vector3();
  const lookAt = new THREE.Vector3();
  const set = (k: string, v: number) => { u[k].value = v; };

  /** Re-anchor the section solids to the camera and publish the frustum's half
   *  extents at the focal plane, which is all `place()` needs to turn a slot rect
   *  into a position. The group carries the camera's own transform, so everything
   *  inside it is in CAMERA space and the solids hold their place on screen no
   *  matter what the journey camera is doing. */
  let layoutName: LayoutName = 'beside';
  let halfW = 1, halfH = 1;
  const anchorSections = (camera: THREE.PerspectiveCamera) => {
    halfH = Math.tan((camera.fov * Math.PI) / 360) * FOCAL;
    halfW = halfH * camera.aspect;
    secGroup.position.copy(camera.position);
    secGroup.quaternion.copy(camera.quaternion);
    set('u_halfW', halfW);
    set('u_halfH', halfH);
  };

  /* ── the CPU mirror, for the hit test ──────────────────────────────────────
     `arrange()` above and `arrangeAt()` here are the same function in two
     languages, over the same RECEDE/FOCAL constants. They have to be: a solid you
     can see two sections away from where the cursor must be is worse than one you
     cannot click at all. The numbers are interpolated into the GLSL from these
     objects, so only the branch structure is written twice. */
  const arrangeAt = (d: number, r: number, t: number, sx: number) => {
    const ad = Math.abs(d);
    const z = RECEDE[layoutName] * ((ad * ad) / (0.6 + ad)) * FOCAL;
    let ox = 0, oy = 0;
    if (layoutName === 'beside') ox = sx * Math.min(ad, 2) * 0.35;
    if (layoutName === 'orbit') {
      const a = t * 0.42 + d * 2.1;
      const m = r * 0.55 * Math.min(ad, 1);
      ox = Math.cos(a) * m;
      oy = Math.sin(a) * m;
    }
    if (layoutName === 'triad') ox = Math.sin(t * 0.3 + d * 2.0) * r * 0.18;
    return { ox, oy, z };
  };

  const slots = u.u_slot.value as Float32Array;
  let slotCount = 0;
  let secNow = 0;
  let scrollNow = 0;
  let vw = 1, vh = 1;
  let clockNow = 0;

  /** A section's drawn centre and radius, in camera space. The same arithmetic
   *  `place()` does, in the same order — see arrangeAt. */
  const solidAt = (i: number) => {
    const sx = slots[i * 4], sy = slots[i * 4 + 1], sr = slots[i * 4 + 2];
    const w = radii[i] ?? 1;
    const d = i - secNow;
    const r = (sr / vh) * 2 * halfH * w;
    const x = ((sx / vw) * 2 - 1) * halfW;
    const y = (1 - ((sy - scrollNow) / vh) * 2) * halfH;
    const a = arrangeAt(d, r, clockNow, x);
    const depth = FOCAL + a.z;
    const k = depth / FOCAL;
    return { x: (x + a.ox) * k, y: (y + a.oy) * k, z: -depth, r };
  };

  const ndc = new THREE.Vector4();
  /** Project a camera-space point straight through the projection matrix — the
   *  section group's model-view IS the identity, by construction above. */
  const toNdc = (camera: THREE.PerspectiveCamera, x: number, y: number, z: number) => {
    ndc.set(x, y, z, 1).applyMatrix4(camera.projectionMatrix);
    return ndc.w !== 0 ? { x: ndc.x / ndc.w, y: ndc.y / ndc.w } : null;
  };

  const world = new THREE.Vector3();
  const worldR = new THREE.Vector3();
  const camRight = new THREE.Vector3();
  const order: number[] = [];

  return {
    group,
    update(camera, t, progress, lit, px = 0, py = 0, section = 0, scroll = 0) {
      const s = stationSpace(progress);
      const tt = s / (STATION_COUNT - 1);

      CAM_CURVE.getPoint(tt, camPos);
      LOOK_CURVE.getPoint(tt, lookAt);
      camera.position.copy(camPos);
      // Idle drift plus pointer parallax, applied to the position and NOT to the
      // target, so the station stays framed and only the parallax moves. Without
      // this a parked camera is a still image: the solids spin, nothing else
      // does, and the page reads as stopped. Amplitude is deliberately under
      // half a unit — enough that the depth separates, never enough that the
      // copy beside it appears to move.
      camera.position.x += Math.sin(t * 0.21) * 0.30 + px * 1.15;
      camera.position.y += Math.cos(t * 0.17) * 0.22 + py * 0.85;
      camera.lookAt(lookAt);

      set('u_t', t);
      set('u_prog', tt);
      set('u_lit', lit);
      set('u_frag', near(s, 1));
      set('u_mem', near(s, 2));
      set('u_shot', near(s, 3));
      set('u_pkt', near(s, 4));
      set('u_web', near(s, 5));

      // The section solids. Two uniforms decide everything: which section is at
      // the focal plane, and how far the page has scrolled — the slots are in
      // document space, so that second one is what keeps a solid level with its
      // own copy rather than with the middle of the frame.
      clockNow = t;
      secNow = section;
      scrollNow = scroll;
      if (secGroup.visible) {
        anchorSections(camera);
        set('u_sec', section);
        set('u_scroll', scroll);
      }

      for (const sh of shots) {
        const k = near(s, sh.station);
        sh.mat.opacity = 0.92 * k;
        sh.plane.visible = k > 0.01;
        sh.frame.visible = sh.plane.visible;
        // the plane turns to face the camera as it resolves
        sh.plane.rotation.y = (1 - k) * 1.25;
        sh.frame.rotation.y = sh.plane.rotation.y;
        sh.uniform.value = k;
      }
    },
    setSections(w, layout = 'beside') {
      layoutName = layout;
      set('u_layout', Math.max(0, LAYOUTS.indexOf(layout)));
      set('u_span', SPAN[layout]);
      buildSections(w, layout);
    },
    setSlots(list) {
      slotCount = Math.min(list.length, MAX_SLOTS);
      for (let i = 0; i < slotCount; i++) {
        slots[i * 4] = list[i].x;
        slots[i * 4 + 1] = list[i].y;
        slots[i * 4 + 2] = list[i].r;
        slots[i * 4 + 3] = 0;
      }
      // A slot beyond the measured list would read whatever was left there by
      // the last page; parking the rest on the final one keeps a stale index
      // harmless rather than throwing a solid across the screen.
      for (let i = slotCount; i < MAX_SLOTS; i++) {
        slots[i * 4] = slotCount ? slots[(slotCount - 1) * 4] : 0;
        slots[i * 4 + 1] = slotCount ? slots[(slotCount - 1) * 4 + 1] : 0;
        slots[i * 4 + 2] = 0;
        slots[i * 4 + 3] = 0;
      }
    },
    setStations(on) {
      stations.visible = on;
    },
    hit(camera, nx, ny) {
      // Nearest section first: the one at the focal plane is the one in front,
      // and the far ones are behind it on screen as well as in depth.
      if (secGroup.visible && slotCount > 1) {
        // Reused, not rebuilt: this runs once a frame to decide the cursor, and
        // two fresh arrays per frame is churn for nothing.
        order.length = slotCount;
        for (let i = 0; i < slotCount; i++) order[i] = i;
        order.sort((a, b) => Math.abs(a - secNow) - Math.abs(b - secNow));
        for (const i of order) {
          const p = solidAt(i);
          const c = toNdc(camera, p.x, p.y, p.z);
          const ex = toNdc(camera, p.x + p.r, p.y, p.z);
          const ey = toNdc(camera, p.x, p.y + p.r, p.z);
          if (!c || !ex || !ey) continue;
          const rx = Math.abs(ex.x - c.x), ry = Math.abs(ey.y - c.y);
          if (rx <= 0 || ry <= 0) continue;
          const dx = (nx - c.x) / rx, dy = (ny - c.y) / ry;
          if (dx * dx + dy * dy <= 1) return { kind: 'section' as const, index: i };
        }
      }
      if (stations.visible) {
        // The offset rides the camera's own right vector — column 0 of its world
        // matrix — so this is a screen-space radius whatever it is looking at.
        camRight.setFromMatrixColumn(camera.matrixWorld, 0);
        // Nearest station to the camera first: they overlap in the finale.
        order.length = STATION_COUNT;
        for (let i = 0; i < STATION_COUNT; i++) order[i] = i;
        order.sort((a, b) =>
          STATIONS[a].distanceToSquared(camera.position)
          - STATIONS[b].distanceToSquared(camera.position));
        for (const i of order) {
          world.copy(STATIONS[i]).project(camera);
          if (world.z > 1) continue;
          worldR.copy(STATIONS[i]).addScaledVector(camRight, RADII[i]).project(camera);
          const r = Math.hypot(worldR.x - world.x, worldR.y - world.y);
          if (r > 0 && Math.hypot(nx - world.x, ny - world.y) <= r) {
            return { kind: 'station' as const, index: i };
          }
        }
      }
      return null;
    },
    resize(w, h, cssW, cssH) {
      (u.u_res.value as THREE.Vector2).set(w, h);
      vw = Math.max(1, cssW);
      vh = Math.max(1, cssH);
      set('u_vw', vw);
      set('u_vh', vh);
      // No empty half on a narrow viewport, so no slot is measured there and the
      // layer is off. If a page does give one, it stays well under the copy.
      set('u_wash', cssW < 1024 ? 0.45 : 1);
    },
    dispose() {
      for (const d of disposables) d.dispose();
    },
  };
}
