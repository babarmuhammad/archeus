/**
 * The journey scene.
 *
 * Ported from archeus's own `graph` background world (claude_sessions/web/stage.js).
 * Same vocabulary, same reasons:
 *   - wireframe dodecahedra (20 vertices, 30 edges) spinning on two axes at
 *     T*0.5 and T*0.37 with a per-node phase, exactly as connections.py's
 *     drawDodec does;
 *   - a lit joint at every vertex;
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

/* Rotate about the solid's own centre, exactly as drawDodec does: ay around Y,
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

/** Node hues, from connections.TYPE_COLORS. */
const HUES = ['#7dcfff', '#9d7bff', '#f7768e', '#73daca', '#e0af68', '#7ee787'];

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
});

/** The 20 distinct vertices of a dodecahedron, deduplicated from the triangle
 *  soup three hands back — the joints have to light in a stable order, and 108
 *  overlapping points cannot give one. */
function dodecVertices(): THREE.Vector3[] {
  const g = new THREE.DodecahedronGeometry(1, 0);
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

  /* ── 1. the six solids, one merged LineSegments ─────────────────────────── */
  const base = new THREE.DodecahedronGeometry(1, 0);
  const wire = new THREE.EdgesGeometry(base);
  const wp = wire.getAttribute('position');
  base.dispose();

  const ePos: number[] = [], eCtr: number[] = [], eNd: number[] = [], eMid: number[] = [];
  for (let s = 0; s < STATION_COUNT; s++) {
    const c = STATIONS[s], r = RADII[s], ph = (s * 1.7) % 6.283, tone = s / STATION_COUNT;
    for (let v = 0; v < wp.count; v += 2) {
      const a = new THREE.Vector3().fromBufferAttribute(wp, v).multiplyScalar(r);
      const b = new THREE.Vector3().fromBufferAttribute(wp, v + 1).multiplyScalar(r);
      // The direction an edge flies off in when the solid fragments: outward
      // from the centre, along its own midpoint.
      const mid = a.clone().add(b).multiplyScalar(0.5).normalize();
      for (const q of [a, b]) {
        ePos.push(q.x, q.y, q.z);
        eCtr.push(c.x, c.y, c.z);
        eNd.push(ph, tone, s);
        eMid.push(mid.x, mid.y, mid.z);
      }
    }
  }
  wire.dispose();

  const gEdges = track(new THREE.BufferGeometry());
  gEdges.setAttribute('position', new THREE.Float32BufferAttribute(ePos, 3));
  gEdges.setAttribute('ctr', new THREE.Float32BufferAttribute(eCtr, 3));
  gEdges.setAttribute('nd', new THREE.Float32BufferAttribute(eNd, 3));
  gEdges.setAttribute('emid', new THREE.Float32BufferAttribute(eMid, 3));

  const mEdges = new THREE.LineSegments(
    gEdges,
    track(new THREE.ShaderMaterial({
      uniforms: u,
      transparent: true,
      depthWrite: false,
      vertexShader: /* glsl */ `
        attribute vec3 ctr; attribute vec3 nd; attribute vec3 emid;
        varying vec2 vN; varying float vD; varying float vS;
        uniform float u_t, u_frag;
        ${SPIN}
        void main(){
          vN = nd.xy; vS = nd.z;
          // Station 02 is the one that comes apart: its edges fly outward and
          // the solid stops being a solid.
          float fr = (abs(nd.z - 1.0) < 0.5) ? u_frag : 0.0;
          vec3 local = position + emid * fr * 2.6;
          vec3 p = ctr + spin(local, nd.x, u_t * (1.0 - 0.55 * fr));
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          vD = clamp(1.0 - (-mv.z) / 46.0, 0.0, 1.0);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        varying vec2 vN; varying float vD; varying float vS;
        uniform vec3 u_acc, u_acc2;
        uniform float u_frag, u_web;
        void main(){
          float fr = (abs(vS - 1.0) < 0.5) ? u_frag : 0.0;
          vec3 col = mix(u_acc, u_acc2, vN.y);
          float a = (0.30 + 0.44 * vD) * (1.0 - 0.62 * fr) * (0.86 + 0.30 * u_web);
          gl_FragColor = vec4(col, a);
        }`,
    })),
  );
  mEdges.frustumCulled = false;
  mEdges.renderOrder = 2;
  stations.add(mEdges);

  /* ── 2. the lit joint at every vertex ───────────────────────────────────── */
  const verts = dodecVertices();
  const jPos: number[] = [], jCtr: number[] = [], jNd: number[] = [], jOrd: number[] = [];
  for (let s = 0; s < STATION_COUNT; s++) {
    const c = STATIONS[s], r = RADII[s], ph = (s * 1.7) % 6.283, tone = s / STATION_COUNT;
    verts.forEach((v, k) => {
      jPos.push(v.x * r, v.y * r, v.z * r);
      jCtr.push(c.x, c.y, c.z);
      jNd.push(ph, tone, s);
      jOrd.push(k / verts.length);
    });
  }
  const gJoint = track(new THREE.BufferGeometry());
  gJoint.setAttribute('position', new THREE.Float32BufferAttribute(jPos, 3));
  gJoint.setAttribute('ctr', new THREE.Float32BufferAttribute(jCtr, 3));
  gJoint.setAttribute('nd', new THREE.Float32BufferAttribute(jNd, 3));
  gJoint.setAttribute('ord', new THREE.Float32BufferAttribute(jOrd, 1));

  const mJoint = new THREE.Points(
    gJoint,
    track(new THREE.ShaderMaterial({
      uniforms: u,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: /* glsl */ `
        attribute vec3 ctr; attribute vec3 nd; attribute float ord;
        varying vec2 vN; varying float vD; varying float vA;
        uniform float u_t, u_lit, u_frag, u_web; uniform vec2 u_res;
        ${SPIN}
        void main(){
          vN = nd.xy;
          vec3 p = ctr + spin(position, nd.x, u_t);
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          vD = clamp(1.0 - (-mv.z) / 46.0, 0.0, 1.0);
          // Station 01 lights its joints one by one on arrival; station 02 loses
          // them as it comes apart; the finale brings every one back up.
          float lit = (abs(nd.z) < 0.5) ? smoothstep(ord, ord + 0.22, u_lit) : 1.0;
          float dim = (abs(nd.z - 1.0) < 0.5) ? (1.0 - 0.88 * u_frag) : 1.0;
          vA = lit * dim * (0.85 + 0.45 * u_web);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = (2.2 + 3.4 * vD) * (u_res.y / 900.0 + 0.6);
        }`,
      fragmentShader: /* glsl */ `
        varying vec2 vN; varying float vD; varying float vA;
        uniform vec3 u_acc, u_acc2;
        void main(){
          float d = length(gl_PointCoord - 0.5);
          if (d > 0.5) discard;
          vec3 col = mix(u_acc, u_acc2, vN.y);
          // the white highlight drawDodec puts in the middle of each joint
          col = mix(col, vec3(1.0), smoothstep(0.28, 0.0, d) * 0.45);
          float a = (1.0 - smoothstep(0.30, 0.5, d)) * (0.30 + 0.42 * vD) * vA;
          gl_FragColor = vec4(col, a);
        }`,
    })),
  );
  mJoint.frustumCulled = false;
  mJoint.renderOrder = 3;
  stations.add(mJoint);

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

  /* Where the trunk is INSIDE a solid. The curve runs through every station
     centre, so the tube skewered each dodecahedron and came out the far side —
     the link never read as arriving anywhere. 1 at a centre, 0 at that solid's
     surface; the fragment shader fades it out over the outer third, so the trunk
     stops on the wireframe. Measured once at build, not per frame. */
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
      // chain already fixed, and the reason these ran through both solids and out
      // the far side. DodecahedronGeometry(1) has circumradius 1, so RADII is
      // exactly where the wireframe is, at every spin angle.
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

  /* ── 7. ONE SOLID PER SECTION, arriving from the background ───────────────
     Not a background field, and not one object that morphs. Every section owns
     its own dodecahedron, sized by that section's weight and coloured by its
     place in the palette. The solid you are reading is in the foreground beside
     the copy; the others wait behind it, further back the further away their
     section is, and each travels forward as you reach it.

     All of it happens in the vertex shader from one uniform (`u_sec`), and all
     of them are one merged buffer — so N sections still cost two draw calls, and
     nothing is animated on the CPU. The group is re-anchored to the camera every
     frame, which makes these positions CAMERA-SPACE: the solids hold their place
     on screen no matter what the journey camera is doing. */
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
      // it — which is exactly what "the dodecahedra do not anchor" was.
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

  /** Unit dodecahedron edges and vertices, reused for every section's solid. */
  const sBase = new THREE.DodecahedronGeometry(1, 0);
  const sWire = new THREE.EdgesGeometry(sBase);
  const swp = sWire.getAttribute('position');
  const S_EDGE = Array.from({ length: swp.count }, (_, i) =>
    new THREE.Vector3().fromBufferAttribute(swp, i));
  sBase.dispose();
  sWire.dispose();
  const S_VERT = dodecVertices();

  const gSecE = track(new THREE.BufferGeometry());
  const gSecJ = track(new THREE.BufferGeometry());

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
      attribute float sid; attribute float sw; attribute vec3 shue;
      varying float vA; varying vec3 vC;
      uniform float u_span;
      ${SPIN}
      ${PLACE}
      void main(){
        float ad = abs(sid - u_sec);
        vC = shue;
        // Visible for a few sections either side, brightest when current. How
        // many is per layout: a rail of short rows scrolls through five in the
        // time a full-height page covers one.
        vA = smoothstep(u_span, 0.0, ad);
        vec3 local = spin(position, sid * 1.7, u_t * 0.55);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(place(local, sid, sw), 1.0);
      }`,
    fragmentShader: /* glsl */ `
      varying float vA; varying vec3 vC;
      uniform float u_wash;
      void main(){ gl_FragColor = vec4(vC, (0.10 + 0.42 * vA * vA) * u_wash); }`,
  })));
  mSecE.frustumCulled = false;
  mSecE.renderOrder = 8;
  secGroup.add(mSecE);

  const mSecJ = new THREE.Points(gSecJ, track(new THREE.ShaderMaterial({
    ...secUniforms,
    vertexShader: /* glsl */ `
      attribute float sid; attribute float sw; attribute vec3 shue;
      varying float vA; varying vec3 vC;
      uniform float u_span; uniform vec2 u_res;
      ${SPIN}
      ${PLACE}
      void main(){
        float ad = abs(sid - u_sec);
        vC = shue;
        vA = smoothstep(u_span, 0.0, ad);
        vec3 local = spin(position, sid * 1.7, u_t * 0.55);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(place(local, sid, sw), 1.0);
        gl_PointSize = (1.6 + 2.6 * vA) * (u_res.y / 900.0 + 0.6);
      }`,
    fragmentShader: /* glsl */ `
      varying float vA; varying vec3 vC;
      uniform float u_wash;
      void main(){
        float d = length(gl_PointCoord - 0.5);
        if (d > 0.5) discard;
        vec3 col = mix(vC, vec3(1.0), smoothstep(0.30, 0.0, d) * 0.5);
        gl_FragColor = vec4(col, (1.0 - smoothstep(0.28, 0.5, d)) * (0.25 + 0.7 * vA) * u_wash);
      }`,
  })));
  mSecJ.frustumCulled = false;
  mSecJ.renderOrder = 9;
  secGroup.add(mSecJ);

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
      attribute vec3 shue;
      varying float vA; varying vec3 vC;
      uniform float u_span;
      ${SPIN}
      ${PLACE}
      void main(){
        vC = shue;
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
      varying float vA; varying vec3 vC;
      uniform float u_wash;
      void main(){ gl_FragColor = vec4(vC, (0.06 + 0.30 * vA) * u_wash); }`,
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
    for (let s = 0; s < n; s++) {
      const c = new THREE.Color(HUES[s % HUES.length]);
      for (const v of S_EDGE) {
        ep.push(v.x, v.y, v.z); ei.push(s); ew.push(rad[s]); eh.push(c.r, c.g, c.b);
      }
      for (const v of S_VERT) {
        jp.push(v.x, v.y, v.z); ji.push(s); jw.push(rad[s]); jh.push(c.r, c.g, c.b);
      }
    }
    const set3 = (g: THREE.BufferGeometry, p: number[], i: number[], w: number[], h: number[]) => {
      g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3));
      g.setAttribute('sid', new THREE.Float32BufferAttribute(i, 1));
      g.setAttribute('sw', new THREE.Float32BufferAttribute(w, 1));
      g.setAttribute('shue', new THREE.Float32BufferAttribute(h, 3));
    };
    set3(gSecE, ep, ei, ew, eh);
    set3(gSecJ, jp, ji, jw, jh);

    // The chain: two vertices per link. Each end carries BOTH its own section and
    // the one at the far end, which is what lets the shader start the line on the
    // surface of its own solid rather than at its centre.
    const lp: number[] = [], li: number[] = [], lw: number[] = [];
    const lo: number[] = [], low: number[] = [], lh: number[] = [];
    const push = (self: number, other: number) => {
      const c = new THREE.Color(HUES[self % HUES.length]);
      lp.push(0, 0, 0);
      li.push(self); lw.push(rad[self]);
      lo.push(other); low.push(rad[other]);
      lh.push(c.r, c.g, c.b);
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
    gSecL.setAttribute('shue', new THREE.Float32BufferAttribute(lh, 3));
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
