'use strict';
/* ── stage: the background ──────────────────────────────────────────────────
   ONE canvas, full viewport, behind everything, for the whole app.

   Read the history before changing this, because it looks like a rule this
   project already broke once. The layer that was deleted was 26 generative
   renderers mounted into ~30 places — a band above every page PLUS a micro
   canvas in every sidebar row, nav item, header chip and quota meter — each
   looping at 6-30fps whether or not anything had happened. The complaint was
   "animated everywhere", and it was correct.

   This is the opposite shape:

     ONE surface, not thirty.   Nothing inside a row, card or chip animates.
     Behind, not between.       z-index:-1, pointer-events:none, aria-hidden.
     Driven by state, not free. Idle crawls; a running job accelerates it; a
                                launch shocks it; navigation ripples it. The
                                motion means something or it does not happen.
     It stops.                  Hidden, blurred (Qt minimise), motion:off,
                                stage:off, reduced-motion, context lost.

   Cost discipline, given that QtWebEngine composites through a GPU hardware
   surface and this adds a second one:

     · Opaque canvas (alpha:false). A transparent surface has to be blended with
       the page underneath on every composite; an opaque one is a straight blit,
       and the scene clears to --bg so the result is identical.
     · No CSS filter / backdrop-filter / mix-blend-mode anywhere near it. All
       glow is done in GL, which is precisely why bloom is affordable here and a
       CSS blur never was (tests/test_gui_flicker.py forbids the CSS form).
     · Render scale below 1 and devicePixelRatio deliberately IGNORED. A soft
       full-screen field does not need 4x the fill on a 4K panel — unlike the
       instruments' hairline arcs, which is why those clamp to 2 instead.
     · Every scene is ONE or TWO draw calls over a pre-built merged geometry,
       animated entirely in the vertex/fragment shader. Per frame the CPU sets a
       handful of uniforms and nothing else. No per-object matrix updates, no
       per-particle JS, no allocation.
     · Instancing is done by merging rather than InstancedMesh, on purpose: a
       raw ShaderMaterial plus InstancedMesh puts you at the mercy of whether
       three injects `attribute mat4 instanceMatrix` into your prefix, which has
       moved between versions. A merged buffer is one draw call either way.
     · No second rAF chain. The stage registers into MO.frame like everything
       else, and MO.frame is also what drives anime's engine.

   Fail-open at every step: no vendor bundle, no WebGL, or a lost context all
   land on the static CSS gradient (html.stage-off) with the app untouched. */

const STAGE_SCALE = 0.75;      // render scale; scenes may raise it for crisp lines
/* Idle fps. Two knobs govern the background and they are NOT the same thing:

     calm  = how BRIGHT it is   (per skin, --sk-calm / u_calm)
     flow  = how much it MOVES  (per skin, scales the scene clock)

   Conflating them is a mistake worth documenting because it was made here. The
   complaint was "overstimulating, confonde" — a brightness/contrast problem —
   and the first fix turned both down, dropping idle to 12fps at 0.12x time. The
   result was a background that had stopped being animated at all. Brightness
   stays capped; motion is back. A dim field that moves is atmosphere, a dim
   field that is frozen is just a gradient. */
const STAGE_FPS_IDLE = 24;     // still smooth enough that motion reads as motion
const STAGE_FPS_BUSY = 34;     // a job is running
const STAGE_ENERGY_TAU = 0.9;  // seconds for energy to close ~63% of a change
const STAGE_SHOCK_S = 1.15;    // launch shockwave decay
const STAGE_PULSE_S = 0.8;     // navigation ripple decay

/* Per-page character. The canvas is global and never restarts across
   navigation — that is what makes it one stage rather than seven wallpapers —
   but each page tilts it. `d` is density/intensity, `c` biases the camera. */
const STAGE_PAGES = {
  home:     {d: 1.00, c: 0.00},
  sessions: {d: 0.92, c: 0.35},
  usage:    {d: 0.86, c: -0.30},
  memory:   {d: 0.80, c: 0.15},
  plan:     {d: 0.95, c: 0.55},
  settings: {d: 0.78, c: -0.55},
  help:     {d: 0.76, c: -0.20},
};
// The floor is 0.72, not 0.3. The first cut dropped Settings to 0.34 and Help to
// 0.30, which is most of why the background looked absent — you are usually ON
// one of those pages when you go looking for it. A page may lean the scene back;
// it may not switch it off.
function stagePage(name) { return STAGE_PAGES[name] || {d: 0.82, c: 0.1}; }

/* Shared vertex shader for the screen-filling backdrop each scene sits on.
   Writes clip space directly, so it fills the viewport whatever the camera is
   doing, and never needs to be positioned or culled. */
const SV_FULL = `
varying vec2 vUv;
void main(){ vUv = uv; gl_Position = vec4(position.xy * 2.0, 0.999, 1.0); }`;

/* Small GLSL toolbox shared by the scenes. Value noise rather than simplex:
   a background does not need the quality and this compiles fast everywhere. */
const SF_LIB = `
float h11(float p){ return fract(sin(p * 127.1) * 43758.5453123); }
float h21(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }
float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(h21(i), h21(i + vec2(1,0)), u.x),
             mix(h21(i + vec2(0,1)), h21(i + vec2(1,1)), u.x), u.y);
}
float fbm(vec2 p){
  float v = 0.0, a = 0.5;
  for(int i = 0; i < 4; i++){ v += a * vnoise(p); p *= 2.03; a *= 0.5; }
  return v;
}`;

const STAGE = {
  /* cinematic | lite | off. `lite` drops bloom (and with it two extra render
     targets), which is the first thing to try if the Qt shell ever tears. */
  tier: 'cinematic',
  scene: 'hud',
  ok: false,          // a live GL scene is mounted
  failed: false,      // gave up for this page load; never retry in a loop

  _pal: null, _pageKey: 'home',
  _E: 0, _Etgt: 0, _shock: 0, _pulse: 0, _dens: 1, _densTgt: 1, _cam: 0, _camTgt: 0,
  // _T is scene time; _Tw is the rendered time it was advanced over, so
  // _T/_Tw is the clock multiplier itself — observable without counting
  // frames, which is what a software rasteriser makes meaningless.
  _T: 0, _Tw: 0, _acc: 0, _job: null,
  _th: null, _ren: null, _post: null, _sc: null, _canvas: null,

  /* ── lifecycle ────────────────────────────────────────────────────────── */
  boot() {
    if (this.failed || this.ok) return;
    const TH = window.THREE;
    const cv = document.getElementById('stage');
    if (!TH || !cv) return;
    if (this.tier === 'off' || !MO.on) { this._static(); return; }
    try {
      const ren = new TH.WebGLRenderer({
        canvas: cv, alpha: false, antialias: false, depth: true, stencil: false,
        powerPreference: 'high-performance', preserveDrawingBuffer: false,
        failIfMajorPerformanceCaveat: false,
      });
      ren.setPixelRatio(STAGE_SCALE);
      ren.autoClear = true;
      this._th = TH; this._ren = ren; this._canvas = cv;
      // QtWebEngine does lose contexts (tab suspend, driver reset). Losing the
      // background must never take the app with it.
      cv.addEventListener('webglcontextlost', e => {
        e.preventDefault(); this._giveUp('context lost');
      }, {once: true});
      this.ok = true;
      this.build();
    } catch (e) {
      console.warn('[stage] WebGL unavailable', e);
      this._giveUp('no webgl');
    }
  },

  /* the fallback is not a degraded stage, it is the static gradient the app
     shipped with — body::before/::after, still in app.css for exactly this.

     Those washes are the DEFAULT, not the exception: they paint from first
     byte, and `stage-on` is only added once GL has actually rendered a frame.
     That ordering is deliberate — the vendor bundle is deferred, so the
     alternative is a second of flat --bg before the scene appears. */
  _static() {
    const r = document.documentElement;
    r.classList.remove('stage-on'); r.classList.add('stage-off');
  },
  _live() {
    const r = document.documentElement;
    r.classList.remove('stage-off'); r.classList.add('stage-on');
  },
  _giveUp(why) {
    this.failed = true; this.ok = false;
    this._teardown();
    if (this._ren) { try { this._ren.dispose(); } catch (e) {} this._ren = null; }
    this._static();
    if (why !== 'off') console.warn('[stage] disabled:', why);
  },

  _teardown() {
    if (this._sc && this._sc.dispose) { try { this._sc.dispose(); } catch (e) {} }
    this._sc = null;
    if (this._post) { try { this._post.dispose(); } catch (e) {} this._post = null; }
  },

  /* (re)build for the current skin + palette. Called on theme change, skin
     change and tier change — i.e. every time the picker is hovered, so the
     teardown above has to actually free the GPU buffers. */
  build() {
    if (!this.ok || !this._ren) return;
    const TH = this._th;
    this._teardown();
    const mk = STAGE_SCENES[this.scene] || STAGE_SCENES.hud;
    try {
      this._sc = mk(TH, this._colors());
    } catch (e) { this._giveUp('scene build failed: ' + e.message); return; }
    this._ren.setPixelRatio(this._sc.scale || STAGE_SCALE);
    this._ren.setClearColor(this._colors().bg, 1);
    this.resize();
    this._mkPost();
    this.kick();
  },

  /* bloom, cinematic tier only. Two extra render targets, so `lite` skips the
     composer entirely rather than setting its strength to zero.

     The threshold matters more than the strength. At 0.2 essentially every lit
     pixel blooms, and a neon scene turns into an undifferentiated colour spill —
     you can see the glow but not the city. At 0.55 only the genuinely bright
     things (window rows, rooftop edges, the radar sweep) bleed, which is what
     bloom is for. */
  _mkPost() {
    this._post = null;
    const P = window.THREE_POST, sc = this._sc;
    if (!P || this.tier !== 'cinematic' || !sc) return;
    // the skin's value wins: themes.py owns how hot each look runs
    const strength = this.bloomOf != null ? this.bloomOf : sc.bloom;
    if (!strength) return;
    try {
      const TH = this._th, r = this._ren;
      const sz = new TH.Vector2(); r.getSize(sz);
      const c = new P.EffectComposer(r);
      c.addPass(new P.RenderPass(sc.scene, sc.camera));
      c.addPass(new P.UnrealBloomPass(sz, strength, 0.5, 0.55));
      c.addPass(new P.OutputPass());
      c.setSize(sz.x, sz.y);
      this._post = c;
    } catch (e) { console.warn('[stage] bloom unavailable', e); this._post = null; }
  },

  _colors() {
    const TH = this._th, p = this._pal || {};
    const C = h => new TH.Color(h || '#7dcfff');
    return {
      acc: C(p.accent), acc2: C(p.accent2), glow: C(p.glow || p.accent),
      bg: C(p.bg), panel: C(p.panel || p.bg), warn: C(p.warn),
      light: p.mode === 'light',
    };
  },

  /* ── inputs from the app ──────────────────────────────────────────────── */
  setTheme(pal) { this._pal = pal; if (this.ok) this.build(); },
  setSkin(name, skin) {
    const next = (skin && skin.stage) || 'hud';
    this.bloomOf = skin ? skin.bloom : 1;
    this.calmOf = skin && skin.calm != null ? skin.calm : 0.3;
    this.flowOf = skin && skin.flow != null ? skin.flow : 1;
    if (next === this.scene && this.ok) return;
    this.scene = next;
    if (this.ok) this.build();
  },
  setTier(tier) {
    this.tier = tier || 'cinematic';
    if (this.tier === 'off') {
      this.stop(); this._teardown(); this.ok = false; this._painted = false;
      this._static();
      return;
    }
    document.documentElement.classList.remove('stage-off');
    // an explicit re-enable clears a previous give-up: the user is asking again,
    // and the reason (a lost context, a driver hiccup) may well have passed
    this.failed = false;
    if (!this.ok) this.boot(); else { this._mkPost(); this.kick(); }
  },

  /* 0..1, how busy the workspace is. Pushed by the renderers that already have
     the numbers — the stage never issues a request of its own, same rule the
     instruments follow. */
  energy(n) {
    n = Math.max(0, Math.min(1, Number(n) || 0));
    if (Math.abs(n - this._Etgt) < 0.01) return;
    this._Etgt = n;
    this.kick();
  },
  /* the launch moment */
  shock() { this._shock = 1; this.kick(); },
  /* navigation */
  impulse() { this._pulse = 1; this.kick(); },
  page(name) {
    const p = stagePage(name);
    this._pageKey = name; this._densTgt = p.d; this._camTgt = p.c;
    this.kick();
  },

  /* ── the frame job ────────────────────────────────────────────────────────
     Registered into MO.frame and kept there while the stage is on. It does NOT
     unregister on blur — MO's own loop already refuses to reschedule while
     hidden or !vis, so the chain parks and resumes without the stage knowing.
     It returns false only when the stage genuinely stops. */
  kick() {
    if (!this.ok || this._job || !MO.on || this.tier === 'off') return;
    this._job = MO.frame(dt => this._tick(dt));
  },
  stop() {
    if (this._job) { MO.unframe(this._job); this._job = null; }
  },

  /* ── unfocused: take the surface DOWN, do not just stop drawing to it ──────
     The tearing you see when archeus is in the background comes from exactly
     that distinction. On blur the frame chain stops (setVis -> MO.stop), which
     is right — but the canvas stayed *visible* while no longer being redrawn,
     and with preserveDrawingBuffer:false the WebGL backbuffer is undefined
     after it has been presented. Qt then recomposites an unfocused window
     against a surface with nothing valid in it, and you get artefacts.

     Hiding it removes the surface from the composite entirely, which also means
     zero GPU for the app while you are working in another one — strictly better
     than a paused-but-present canvas. The static CSS wash takes over, so the
     window still looks like itself if you glance at it.

     `preserveDrawingBuffer: true` would also fix it, and was rejected: it costs
     a buffer copy on every single frame to repair a state nobody is looking at. */
  blur(on) {
    if (!this._canvas) return;
    document.documentElement.classList.toggle('stage-blur', !!on);
    // repaint once on return: the buffer we hid is not guaranteed to survive
    if (!on && this.ok) { this._acc = 1; this.kick(); }
  },

  _tick(dt) {
    if (!this.ok || !this._ren || !this._sc || this.tier === 'off' || !MO.on) {
      this._job = null; return false;
    }
    // energy first: it sets the frame cap, so a burst of work speeds up the
    // very frame that notices it
    const k = 1 - Math.exp(-dt / STAGE_ENERGY_TAU);
    this._E += (this._Etgt - this._E) * k;
    this._dens += (this._densTgt - this._dens) * k;
    this._cam += (this._camTgt - this._cam) * k;
    if (this._shock > 0) this._shock = Math.max(0, this._shock - dt / STAGE_SHOCK_S);
    if (this._pulse > 0) this._pulse = Math.max(0, this._pulse - dt / STAGE_PULSE_S);

    const fps = STAGE_FPS_IDLE + (STAGE_FPS_BUSY - STAGE_FPS_IDLE) * this._E;
    this._acc += dt;
    if (this._acc < 1 / fps) return true;
    const fdt = this._acc; this._acc = 0;

    // Scene time: always moving, and clearly faster when the workspace is busy.
    // The idle term is the baseline "this thing is alive"; the energy term is
    // what makes "the workspace is working" legible at a glance. `flow` is the
    // per-skin amplitude — Terminal drifts, Cyberpunk runs.
    const flow = this.flowOf != null ? this.flowOf : 1;
    this._T += fdt * flow * (0.55 + 1.7 * this._E + 1.2 * this._shock);
    this._Tw += fdt;

    const sc = this._sc;
    try {
      sc.update({t: this._T, dt: fdt, e: this._E, shock: this._shock,
                 pulse: this._pulse, dens: this._dens, cam: this._cam,
                 calm: this.calmOf != null ? this.calmOf : 0.3});
      if (this._post) this._post.render(fdt);
      else this._ren.render(sc.scene, sc.camera);
    } catch (e) { this._giveUp('render failed: ' + e.message); return false; }
    // only now is it safe to drop the static wash — a frame has landed
    if (!this._painted) { this._painted = true; this._live(); }
    return true;
  },

  resize() {
    if (!this.ok || !this._ren || !this._sc) return;
    const w = window.innerWidth, h = window.innerHeight;
    this._ren.setSize(w, h, false);
    if (this._sc.resize) this._sc.resize(w, h);
    if (this._post) {
      const sz = new this._th.Vector2(); this._ren.getSize(sz);
      this._post.setSize(sz.x, sz.y);
    }
  },
};

/* ── scene toolkit ────────────────────────────────────────────────────────── */

/* One draw call, screen-filling, always behind. Every scene lays its
   foreground over one of these rather than showing the flat clear colour. */
function sBackdrop(TH, frag, uniforms) {
  const m = new TH.ShaderMaterial({
    vertexShader: SV_FULL, fragmentShader: frag, uniforms,
    depthTest: false, depthWrite: false,
  });
  const q = new TH.Mesh(new TH.PlaneGeometry(1, 1), m);
  q.frustumCulled = false;
  q.renderOrder = -10;
  return q;
}

/* Merge n copies of a template geometry into one buffer, tagging each copy with
   per-copy attributes. This is how every "instanced" scene here is built: one
   draw call, and the per-copy data lives in attributes the vertex shader reads,
   so animating 4000 boxes costs one uniform write. */
function sMerge(TH, tmpl, n, attrs, place) {
  const pos = tmpl.getAttribute('position');
  const nrm = tmpl.getAttribute('normal');
  const idx = tmpl.getIndex();
  const vc = pos.count;
  const iCount = idx ? idx.count : 0;
  const P = new Float32Array(vc * n * 3);
  const N = nrm ? new Float32Array(vc * n * 3) : null;
  const I = iCount ? new Uint32Array(iCount * n) : null;
  const A = {};
  for (const k in attrs) A[k] = new Float32Array(vc * n * attrs[k]);

  const o = {p: [0, 0, 0], s: [1, 1, 1], a: {}};
  for (let i = 0; i < n; i++) {
    o.p[0] = o.p[1] = o.p[2] = 0; o.s[0] = o.s[1] = o.s[2] = 1; o.a = {};
    place(i, o);
    for (let v = 0; v < vc; v++) {
      const d = (i * vc + v) * 3;
      P[d]     = pos.getX(v) * o.s[0] + o.p[0];
      P[d + 1] = pos.getY(v) * o.s[1] + o.p[1];
      P[d + 2] = pos.getZ(v) * o.s[2] + o.p[2];
      if (N) { N[d] = nrm.getX(v); N[d + 1] = nrm.getY(v); N[d + 2] = nrm.getZ(v); }
      for (const k in attrs) {
        const w = attrs[k], src = o.a[k];
        for (let c = 0; c < w; c++) A[k][(i * vc + v) * w + c] = src ? src[c] : 0;
      }
    }
    if (I) for (let e = 0; e < iCount; e++) I[i * iCount + e] = idx.getX(e) + i * vc;
  }
  const g = new TH.BufferGeometry();
  g.setAttribute('position', new TH.BufferAttribute(P, 3));
  if (N) g.setAttribute('normal', new TH.BufferAttribute(N, 3));
  for (const k in attrs) g.setAttribute(k, new TH.BufferAttribute(A[k], attrs[k]));
  if (I) g.setIndex(new TH.BufferAttribute(I, 1));
  return g;
}

/* every scene returns this shape; dispose() has to free everything it made,
   because the settings picker rebuilds on hover */
function sScene(TH, camera, bloom, scale) {
  const scene = new TH.Scene();
  const bag = [];
  return {
    scene, camera, bloom, scale,
    add(o) { scene.add(o); bag.push(o); return o; },
    dispose() {
      for (const o of bag) {
        scene.remove(o);
        if (o.geometry) o.geometry.dispose();
        if (o.material) o.material.dispose();
      }
      bag.length = 0;
    },
  };
}
function sU(TH, c) {
  return {
    u_t: {value: 0}, u_e: {value: 0}, u_shock: {value: 0}, u_pulse: {value: 0},
    u_dens: {value: 1}, u_res: {value: new TH.Vector2(1, 1)},
    u_calm: {value: 0.3},
    u_acc: {value: c.acc}, u_acc2: {value: c.acc2}, u_glow: {value: c.glow},
    u_bg: {value: c.bg}, u_panel: {value: c.panel}, u_warn: {value: c.warn},
    u_light: {value: c.light ? 1 : 0},
  };
}
function sFeed(u, f) {
  u.u_t.value = f.t; u.u_e.value = f.e; u.u_shock.value = f.shock;
  u.u_pulse.value = f.pulse; u.u_dens.value = f.dens; u.u_calm.value = f.calm;
}

/* THE CEILING. Every scene's final colour passes through this before it leaves
   the fragment shader, mixing back toward the page background by (1 - calm).

   This exists because the first cut of the stage was correct and unusable:

     "sto sfondo non mi fa impazzire, un po' overstimulating confonde"

   …and both users then switched to the one skin that had no background at all.
   The scenes are not the problem; their amplitude was. `calm` is per-skin
   (themes.py) and none of them go above ~0.45, so the background is always a
   ground for the interface rather than a competitor to it. A scene that wants
   to be brighter should say so in its skin, not by skipping this call. */
const SF_CALM = `
vec3 calm(vec3 col, vec3 bg, float k){ return mix(bg, col, clamp(k, 0.0, 1.0)); }`;

/* ── the seven scenes ─────────────────────────────────────────────────────── */

const STAGE_SCENES = {

  /* HUD — an instrument horizon. A wireframe ground plane racing to a vanishing
     point, concentric range rings, and a radar sweep that comes round faster
     the busier the workspace is. */
  hud(TH, c) {
    // 1.0 scale: this scene is all 1px lines, which is the one case where the
    // reduced render scale is visible as mush
    const cam = new TH.PerspectiveCamera(62, 1, 0.1, 90);
    const S = sScene(TH, cam, 0.55, 1.0);
    const u = sU(TH, c);

    S.add(sBackdrop(TH, `
      ${SF_LIB}
      ${SF_CALM}
      varying vec2 vUv; uniform vec3 u_bg,u_acc,u_acc2;
      uniform float u_t,u_e,u_light,u_calm;
      void main(){
        vec2 p = vUv - 0.5;
        float sky = smoothstep(-0.05, 0.55, vUv.y);
        vec3 col = mix(u_bg, mix(u_bg, u_acc2, 0.16), sky);
        // horizon bloom, brighter when there is work happening
        col += u_acc * (0.14 + 0.22 * u_e) * exp(-abs(vUv.y - 0.5) * 9.0);
        col += u_acc2 * 0.05 * fbm(p * 3.0 + u_t * 0.03);
        gl_FragColor = vec4(calm(col, u_bg, u_calm), 1.0);
      }`, u));

    // ground grid — one LineSegments, scrolled in the vertex shader
    const N = 46, EXT = 34;
    const gp = [];
    for (let i = 0; i <= N; i++) {
      const x = -EXT + (2 * EXT) * (i / N);
      gp.push(x, 0, -EXT, x, 0, EXT);
      const z = -EXT + (2 * EXT) * (i / N);
      gp.push(-EXT, 0, z, EXT, 0, z);
    }
    const gg = new TH.BufferGeometry();
    gg.setAttribute('position', new TH.Float32BufferAttribute(gp, 3));
    const grid = new TH.LineSegments(gg, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false,
      vertexShader: `
        varying float vF; varying vec3 vP;
        uniform float u_t,u_e;
        void main(){
          vec3 p = position;
          p.z = mod(p.z + u_t * (1.4 + 5.0 * u_e) + 34.0, 68.0) - 34.0;
          vP = p;
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          vF = clamp(1.0 - (-mv.z) / 34.0, 0.0, 1.0);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        varying float vF; varying vec3 vP;
        uniform vec3 u_acc,u_acc2; uniform float u_e,u_shock,u_calm;
        void main(){
          float a = pow(vF, 2.2) * (0.42 + 0.3 * u_e);
          // the shockwave: a bright ring expanding out of the origin
          float r = length(vP.xz);
          a += u_shock * exp(-abs(r - (1.0 - u_shock) * 30.0) * 0.8) * 1.4;
          vec3 col = mix(u_acc, u_acc2, clamp(vP.x * 0.02 + 0.5, 0.0, 1.0));
          gl_FragColor = vec4(col * (1.0 + u_shock), a);
        }`,
    }));
    grid.position.y = -1.5;
    S.add(grid);

    // range rings + sweep, lying on the plane ahead
    const rp = [];
    for (let k = 1; k <= 5; k++) {
      const rad = k * 2.6, seg = 96;
      for (let i = 0; i < seg; i++) {
        const a0 = (i / seg) * Math.PI * 2, a1 = ((i + 1) / seg) * Math.PI * 2;
        rp.push(Math.cos(a0) * rad, 0, Math.sin(a0) * rad,
                Math.cos(a1) * rad, 0, Math.sin(a1) * rad);
      }
    }
    const rg = new TH.BufferGeometry();
    rg.setAttribute('position', new TH.Float32BufferAttribute(rp, 3));
    const rings = new TH.LineSegments(rg, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false,
      vertexShader: `
        varying vec3 vP; void main(){ vP = position;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: `
        varying vec3 vP; uniform vec3 u_acc; uniform float u_t,u_e,u_dens;
        void main(){
          // the sweep: a bright arc rotating round the rings
          float ang = atan(vP.z, vP.x);
          float sweep = fract((ang + 3.14159) / 6.28318 + u_t * (0.05 + 0.16 * u_e));
          float lit = pow(1.0 - sweep, 7.0);
          float a = (0.13 + 0.75 * lit) * u_dens;
          gl_FragColor = vec4(u_acc * (0.8 + lit), a);
        }`,
    }));
    rings.position.set(0, -1.48, -9);
    S.add(rings);

    S.update = f => {
      sFeed(u, f);
      cam.position.set(Math.sin(f.t * 0.05) * 1.6 + f.cam * 2.4, 1.1 + f.cam * 0.5, 7.5);
      cam.lookAt(0, -0.9, -12);
    };
    S.resize = (w, h) => {
      u.u_res.value.set(w, h); cam.aspect = w / h; cam.updateProjectionMatrix();
    };
    return S;
  },

  /* Anime — a cel-shaded sky. Flat quantised bands, hard-edged halftone dots,
     and ONE soft element (the bloom behind them) so the flatness reads as a
     choice. No gradients inside the bands: cel shading quantises, it does not
     blend, which the reference is explicit about. */
  anime(TH, c) {
    const cam = new TH.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const S = sScene(TH, cam, .35, STAGE_SCALE);
    const u = sU(TH, c);
    S.add(sBackdrop(TH, `
      ${SF_LIB}
      ${SF_CALM}
      varying vec2 vUv;
      uniform vec3 u_bg,u_acc,u_acc2; uniform vec2 u_res;
      uniform float u_t,u_e,u_shock,u_pulse,u_dens,u_calm;
      void main(){
        float asp = u_res.x / max(1.0, u_res.y);
        vec2 p = vec2(vUv.x * asp, vUv.y);
        // quantised sky: three flat bands, edges that move but never blur
        float band = fbm(vec2(p.x * 1.2, p.y * 2.2) + vec2(u_t * 0.05, 0.0));
        float lvl = floor(band * 3.0) / 3.0;
        vec3 col = mix(u_bg, u_acc2, lvl * 0.5);
        // halftone: hard dots, radius by band level. The signature of the look.
        vec2 g = p * 40.0;
        float d = length(fract(g) - 0.5);
        float r = 0.13 + 0.26 * (1.0 - lvl);
        col = mix(col, u_acc, step(d, r) * 0.35);
        // speed lines sweep once on a launch, never on idle
        float sl = step(0.986, fract(p.y * 26.0 + u_t * 0.5));
        col = mix(col, u_acc, sl * u_shock * 0.8);
        col += u_acc2 * u_pulse * 0.12 * step(0.5, fract(p.x * 3.0 - u_t));
        gl_FragColor = vec4(calm(col, u_bg, u_calm * u_dens), 1.0);
      }`, u));
    S.update = f => sFeed(u, f);
    S.resize = (w, h) => u.u_res.value.set(w, h);
    return S;
  },

  /* Cyberpunk — the neon flythrough, rebuilt darker. Same infinite instanced
     skyline as before (that part worked: the buildings read as buildings once
     the faces stayed unlit), now under the calm ceiling with a scanline pass
     and a chromatic split at the edges of the frame. */
  cyber(TH, c) {
    const cam = new TH.PerspectiveCamera(72, 1, 0.1, 130);
    const S = sScene(TH, cam, .7, STAGE_SCALE);
    const u = sU(TH, c);
    const SPAN = 120;
    S.add(sBackdrop(TH, `
      ${SF_LIB}
      ${SF_CALM}
      varying vec2 vUv; uniform vec3 u_bg,u_acc,u_acc2;
      uniform float u_t,u_e,u_calm; uniform vec2 u_res;
      void main(){
        vec3 col = mix(u_bg, mix(u_bg, u_acc2, 0.13), pow(vUv.y, 1.8));
        col += u_acc * 0.05 * exp(-abs(vUv.y - 0.42) * 9.0);
        // scanlines, the cheapest honest cyberpunk tell
        col *= 0.94 + 0.06 * sin(vUv.y * u_res.y * 1.2);
        gl_FragColor = vec4(calm(col, u_bg, u_calm), 1.0);
      }`, u));

    const N = 260;
    const tmpl = new TH.BoxGeometry(1, 1, 1);
    const g = sMerge(TH, tmpl, N, {bx: 4}, (i, o) => {
      const side = i % 2 ? 1 : -1;
      const lane = 5.5 + Math.random() * 16;
      const hgt = 3 + Math.pow(Math.random(), 1.7) * 26;
      o.s[0] = 1.6 + Math.random() * 3.2;
      o.s[1] = hgt;
      o.s[2] = 1.6 + Math.random() * 3.2;
      o.p[0] = side * lane;
      o.p[1] = hgt / 2 - 6;
      o.p[2] = -Math.random() * SPAN;
      o.a.bx = [Math.random(), hgt, Math.random(), side];
    });
    const city = new TH.Mesh(g, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: true,
      vertexShader: `
        attribute vec4 bx; varying vec4 vB; varying vec3 vL; varying float vFog;
        uniform float u_t,u_e,u_shock,u_dens;
        void main(){
          vec3 p = position;
          float sp = u_t * (3.0 + 14.0 * u_e + 26.0 * u_shock);
          p.z = mod(p.z + sp, ${SPAN}.0) - ${SPAN}.0 + 8.0;
          vB = bx; vL = position;
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          vFog = clamp(1.0 - (-mv.z) / ${SPAN}.0, 0.0, 1.0);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        ${SF_LIB}
        ${SF_CALM}
        varying vec4 vB; varying vec3 vL; varying float vFog;
        uniform vec3 u_acc,u_acc2,u_bg; uniform float u_t,u_e,u_dens,u_calm;
        void main(){
          float rows = step(0.55, fract(vL.y * 2.6));
          float cols = step(0.45, fract(vL.x * 3.1 + vB.x * 10.0));
          float lit = rows * cols * step(0.35, h11(floor(vL.y * 2.6) * 13.0 + vB.z * 91.0));
          vec3 neon = mix(u_acc, u_acc2, vB.w * 0.5 + 0.5);
          // faces stay dark; only windows and the rooftop rim carry light
          vec3 col = u_bg * 0.7;
          col = mix(col, neon, lit * (0.7 + 0.3 * u_e));
          col += neon * smoothstep(0.46, 0.5, vL.y) * (0.9 + 0.7 * u_e);
          gl_FragColor = vec4(calm(col, u_bg, u_calm), pow(vFog, 1.3) * u_dens);
        }`,
    }));
    S.add(city);
    S.update = f => {
      sFeed(u, f);
      cam.position.set(f.cam * 3.0, 1.6 + Math.sin(f.t * 0.11) * 0.7, 6);
      cam.rotation.z = Math.sin(f.t * 0.07) * 0.03 + f.pulse * 0.05;
      cam.lookAt(f.cam * 1.2, 1.0, -40);
    };
    S.resize = (w, h) => {
      u.u_res.value.set(w, h); cam.aspect = w / h; cam.updateProjectionMatrix();
    };
    return S;
  },

  /* Deck — a flight deck's substrate. A hairline grid on a visible rhythm plus
     sparse telemetry ticks. The FUI reference's actual point: it reads
     functional because the grid has consistent logic, not because anything is
     ornamented. Almost nothing moves until the workspace is busy. */
  deck(TH, c) {
    const cam = new TH.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const S = sScene(TH, cam, .3, 1.0);
    const u = sU(TH, c);
    S.add(sBackdrop(TH, `
      ${SF_LIB}
      ${SF_CALM}
      varying vec2 vUv;
      uniform vec3 u_bg,u_acc,u_acc2; uniform vec2 u_res;
      uniform float u_t,u_e,u_shock,u_pulse,u_dens,u_calm;
      void main(){
        float asp = u_res.x / max(1.0, u_res.y);
        vec2 p = vec2(vUv.x * asp, vUv.y);
        vec3 col = u_bg;
        // two-level grid: fine cells inside coarse blocks
        vec2 f1 = abs(fract(p * 26.0) - 0.5);
        vec2 f2 = abs(fract(p * 6.5) - 0.5);
        float fine   = 1.0 - smoothstep(0.0, 0.03, min(f1.x, f1.y));
        float coarse = 1.0 - smoothstep(0.0, 0.012, min(f2.x, f2.y));
        col += u_acc * fine * 0.06;
        col += u_acc * coarse * 0.14;
        // a sweep line: the only thing that moves, and it tracks energy
        float sweep = fract(p.x * 0.5 - u_t * (0.02 + 0.12 * u_e));
        col += u_acc2 * pow(1.0 - sweep, 24.0) * (0.10 + 0.35 * u_e);
        // telemetry ticks along the bottom edge, stepped
        float tick = step(0.7, fract(p.x * 60.0)) * step(p.y, 0.035);
        col += u_acc * tick * 0.25;
        col += u_acc2 * u_shock * 0.25 * coarse;
        col += u_acc * u_pulse * 0.10 * fine;
        gl_FragColor = vec4(calm(col, u_bg, u_calm * u_dens), 1.0);
      }`, u));
    S.update = f => sFeed(u, f);
    S.resize = (w, h) => u.u_res.value.set(w, h);
    return S;
  },

  /* Graph — the homage. A force-graph field: nodes at fixed solved positions
     (deterministic, so it is stable to look at across reloads, the same reason
     the flow-map instrument solves from the index) with edges between near
     neighbours. Node colours come from the palette lifted out of
     connections.TYPE_COLORS, so the background is drawn in the exact hues the
     project's real architecture graph uses. */
  /* Graph — THE homage. This is not "a graph-ish field": it is the same thing
     connections.py draws for the real architecture view — wireframe dodecahedra
     (20 vertices, 30 edges) rotating on two axes, joined by hairline links, with
     a lit joint at every vertex. Even the rotation matches: drawDodec spins at
     T*0.5 and T*0.37 with a per-node phase, and so does this.

     Three draw calls, all merged, all animated in the vertex shader:
       1. the solids' 30 edges each, rotated about their own centre
       2. the links between centres
       3. the vertex joints, as points

     Node positions are a deterministic golden-angle spiral — no Math.random —
     so the constellation is identical on every reload. Same reasoning as the
     flow-map instrument: a layout that reshuffles reads as noise. */
  graph(TH, c) {
    const cam = new TH.PerspectiveCamera(55, 1, 0.1, 60);
    const S = sScene(TH, cam, .5, 1.0);
    const u = sU(TH, c);

    // ── node field ──
    const N = 40;
    const nodes = [];
    for (let i = 0; i < N; i++) {
      const ang = i * 2.399963;                       // golden angle
      const rad = 1.0 + 5.6 * Math.sqrt(i / N);
      // Size follows a LONG TAIL, not a uniform spread: a handful of large hubs
      // among many small leaves. Cubing a flat hash is what does it — a linear
      // ramp gives forty solids of forgettably similar size, which is what the
      // first cut had. Same read the real architecture graph gives, where a
      // module dwarfs a leaf. Deterministic hash, so the field is identical on
      // every reload.
      const h = ((i * 9301 + 49297) % 233280) / 233280;
      const r = 0.13 + Math.pow(h, 3) * 1.15;
      nodes.push({
        x: Math.cos(ang) * rad * 1.85,
        y: Math.sin(ang) * rad * 0.98,
        z: -1.5 - ((i * 7) % 11) * 0.62,
        r,
        // mass by volume. Without this the collision below is equal-mass and a
        // pea deflects a boulder, which looks wrong the moment sizes differ.
        m: r * r * r,
        ph: (i * 1.7) % 6.283,
        tone: (i % 5) / 5,
      });
    }

    /* ── the solids drift, and they bump into each other ────────────────────
       Live positions in a uniform array, integrated on the CPU. This is the one
       scene that does per-frame CPU work, and it is a deliberate exception to
       the "uniforms only" rule at the top of this file: 40 bodies is 780 pair
       checks, which is nothing, and the alternative — baking a canned path into
       the shader — cannot produce a collision.

       Deterministic seeding, no Math.random: the lattice must settle the same
       way on every reload, for the same reason the layout does. */
    const POS = new Float32Array(N * 3);
    const VEL = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      POS[i * 3] = nodes[i].x; POS[i * 3 + 1] = nodes[i].y; POS[i * 3 + 2] = nodes[i].z;
      // golden-ratio seeded drift — slow, and no two alike
      const a = i * 2.399963, b = i * 0.7548777;
      VEL[i * 3]     = Math.cos(a) * 0.22 + Math.sin(b) * 0.08;
      VEL[i * 3 + 1] = Math.sin(a) * 0.16 + Math.cos(b) * 0.07;
      VEL[i * 3 + 2] = Math.sin(b * 1.7) * 0.10;
    }
    u.u_np = {value: Array.from({length: N}, (_, i) =>
      new TH.Vector3(POS[i * 3], POS[i * 3 + 1], POS[i * 3 + 2]))};

    const BOUND = [11.5, 6.2, 5.0];     // the box they are kept inside
    function physics(dt, e) {
      const sp = 0.45 + 0.9 * e;        // busier workspace, livelier lattice
      // pairwise soft collision: separate, then swap the normal velocity
      for (let i = 0; i < N; i++) {
        for (let j = i + 1; j < N; j++) {
          const dx = POS[j * 3] - POS[i * 3];
          const dy = POS[j * 3 + 1] - POS[i * 3 + 1];
          const dz = POS[j * 3 + 2] - POS[i * 3 + 2];
          const d2 = dx * dx + dy * dy + dz * dz;
          const rr = (nodes[i].r + nodes[j].r) * 1.35;
          if (d2 >= rr * rr || d2 < 1e-6) continue;
          const d = Math.sqrt(d2), nx = dx / d, ny = dy / d, nz = dz / d;
          // separate them, and let the heavier one hold its ground
          const mi = nodes[i].m, mj = nodes[j].m, mt = mi + mj;
          const gap = rr - d;
          const pi = gap * (mj / mt), pj = gap * (mi / mt);
          POS[i * 3] -= nx * pi; POS[i * 3 + 1] -= ny * pi; POS[i * 3 + 2] -= nz * pi;
          POS[j * 3] += nx * pj; POS[j * 3 + 1] += ny * pj; POS[j * 3 + 2] += nz * pj;
          // elastic exchange along the contact normal, weighted by mass and
          // damped so the field keeps jostling instead of heating up until
          // everything flies apart. A big hub now plows through a small leaf and
          // the leaf pings off it, which is the whole reason sizes vary.
          const vi = VEL[i * 3] * nx + VEL[i * 3 + 1] * ny + VEL[i * 3 + 2] * nz;
          const vj = VEL[j * 3] * nx + VEL[j * 3 + 1] * ny + VEL[j * 3 + 2] * nz;
          if (vi - vj <= 0) continue;            // already separating
          const ti = (2 * mj / mt) * (vj - vi) * 0.9;
          const tj = (2 * mi / mt) * (vi - vj) * 0.9;
          VEL[i * 3] += nx * ti; VEL[i * 3 + 1] += ny * ti; VEL[i * 3 + 2] += nz * ti;
          VEL[j * 3] += nx * tj; VEL[j * 3 + 1] += ny * tj; VEL[j * 3 + 2] += nz * tj;
        }
      }
      for (let i = 0; i < N; i++) {
        for (let k = 0; k < 3; k++) {
          const a = i * 3 + k;
          POS[a] += VEL[a] * dt * sp;
          // Reflect at the wall, and clamp back inside so a body can never
          // escape and drift off screen for the rest of the session. The limit
          // is inset by the radius, or a large solid half-leaves the frame while
          // its centre is still legally inside.
          const lim = Math.max(0.5, BOUND[k] - nodes[i].r);
          if (POS[a] > lim) { POS[a] = lim; VEL[a] = -Math.abs(VEL[a]); }
          else if (POS[a] < -lim) { POS[a] = -lim; VEL[a] = Math.abs(VEL[a]); }
          VEL[a] *= 0.9995;               // a whisper of drag
        }
        u.u_np.value[i].set(POS[i * 3], POS[i * 3 + 1], POS[i * 3 + 2] - 3.0);
      }
    }

    /* rotate about the node's own centre, exactly as drawDodec does:
         ay spins around Y, then ax around X. */
    const SPIN = `
      vec3 spin(vec3 local, float ph, float t){
        float ax = t * 0.5 + ph, ay = t * 0.37 + ph * 1.7;
        float ca = cos(ax), sa = sin(ax), cb = cos(ay), sb = sin(ay);
        float x = local.x * cb + local.z * sb;
        float z = -local.x * sb + local.z * cb;
        float y2 = local.y * ca - z * sa;
        float z2 = local.y * sa + z * ca;
        return vec3(x, y2, z2);
      }`;

    // 1 ── the wireframe solids, one merged LineSegments
    const solid = new TH.DodecahedronGeometry(1, 0);
    const wire = new TH.EdgesGeometry(solid);
    // Positions live in a uniform array so the CPU can move them; the geometry
    // holds each vertex's LOCAL offset plus its node index. One buffer, one draw
    // call, and drifting 40 solids costs 40 vec3 uniform writes a frame.
    const gEdges = sMerge(TH, wire, N, {nd: 3}, (i, o) => {
      const n = nodes[i];
      o.p[0] = o.p[1] = o.p[2] = 0;              // local space
      o.s[0] = o.s[1] = o.s[2] = n.r;
      o.a.nd = [n.ph, n.tone, i];
    });
    solid.dispose(); wire.dispose();

    const wireMat = new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false,
      vertexShader: `
        attribute vec3 nd;
        varying vec2 vN; varying float vD;
        uniform float u_t; uniform vec3 u_np[${N}];
        ${SPIN}
        void main(){
          vN = nd.xy;
          vec3 p = u_np[int(nd.z)] + spin(position, nd.x, u_t);
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          vD = clamp(1.0 - (-mv.z) / 26.0, 0.0, 1.0);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        ${SF_CALM}
        varying vec2 vN; varying float vD;
        uniform vec3 u_acc,u_acc2,u_bg;
        uniform float u_e,u_dens,u_calm,u_shock;
        void main(){
          vec3 col = mix(u_acc, u_acc2, vN.y);
          col += vec3(u_shock * 0.6);
          float a = (0.40 + 0.44 * vD) * u_dens * (0.75 + 0.35 * u_e);
          gl_FragColor = vec4(calm(col, u_bg, u_calm + 0.35), a);
        }`,
    });
    const mEdges = new TH.LineSegments(gEdges, wireMat);
    /* Every one of the three objects below is placed by u_np in the vertex
       shader, so its `position` attribute is a LOCAL offset and the bounding
       sphere three derives from it describes nothing. Frustum culling has to be
       off or the renderer discards them based on geometry that is not where they
       are — and the links go first, because with every position at (0,0,0) their
       bounding sphere has radius ZERO. That is why the connecting lines
       disappeared the moment the solids started moving. sBackdrop does the same
       thing for the same reason. */
    mEdges.frustumCulled = false;
    S.add(mEdges);

    // 2 ── links between neighbouring centres
    // Three near neighbours plus one long chord each: a spiral linked only to
    // i+1/i+2 reads as a chain, not a graph.
    //
    // `position` is a placeholder — every endpoint is placed by u_np[li] in the
    // vertex shader so the links follow their solids as those drift. Both
    // attributes are REQUIRED: a declared-but-absent attribute reads as 0, which
    // pins every segment to node 0 and gives it zero length, so the lines vanish
    // without a single error anywhere. That is exactly what happened here.
    const lp = [], la = [], li = [], ls = [];
    let seg = 0;
    for (let i = 0; i < N; i++) {
      for (const k of [1, 2, 3, 8]) {
        const j = i + k;
        if (j >= N) continue;
        lp.push(0, 0, 0, 0, 0, 0);
        la.push(0, 1);
        li.push(i, j);
        // one seed per SEGMENT (identical on both endpoints, so it survives
        // interpolation) — it de-synchronises the packets travelling each link.
        // Without it every edge pulses in lockstep and reads as a strobe.
        const sd = ((seg * 9301 + 49297) % 233280) / 233280;
        ls.push(sd, sd);
        seg++;
      }
    }
    const gLink = new TH.BufferGeometry();
    gLink.setAttribute('position', new TH.Float32BufferAttribute(lp, 3));
    gLink.setAttribute('lt', new TH.Float32BufferAttribute(la, 1));
    gLink.setAttribute('li', new TH.Float32BufferAttribute(li, 1));
    gLink.setAttribute('lsd', new TH.Float32BufferAttribute(ls, 1));
    const mLink = new TH.LineSegments(gLink, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false,
      vertexShader: `
        attribute float lt; attribute float li; attribute float lsd;
        varying float vT; varying float vD; varying float vS;
        uniform vec3 u_np[${N}];
        void main(){ vT = lt; vS = lsd;
          vec4 mv = modelViewMatrix * vec4(u_np[int(li)], 1.0);
          vD = clamp(1.0 - (-mv.z) / 26.0, 0.0, 1.0);
          gl_Position = projectionMatrix * mv; }`,
      fragmentShader: `
        ${SF_CALM}
        varying float vT; varying float vD; varying float vS;
        uniform vec3 u_acc,u_acc2,u_bg;
        uniform float u_t,u_e,u_pulse,u_dens,u_calm;
        // a packet: a bright head with a short tail behind it, like the
        // particles connections.py runs along its edges
        float packet(float at, float head){
          float d = at - head;
          float dot_  = pow(max(0.0, 1.0 - abs(d) * 26.0), 2.0);
          float tail  = d < 0.0 ? pow(max(0.0, 1.0 + d * 7.0), 3.0) * 0.35 : 0.0;
          return dot_ + tail;
        }
        void main(){
          // DATA TRAVELLING. Always running — this is the graph showing that the
          // links carry something — but faster and denser when the workspace is
          // busy, so it is still telling you something rather than decorating.
          float sp = 0.16 + 0.42 * u_e;
          float p1 = packet(vT, fract(u_t * sp + vS));
          float p2 = packet(vT, fract(u_t * sp * 0.72 + vS + 0.53)) * 0.7;
          float data = p1 + p2;
          // …plus the one-shot surge when you navigate
          float surge = pow(1.0 - abs(fract(u_t * 0.2) - vT), 26.0) * u_pulse;
          vec3 col = mix(u_acc, mix(u_acc2, vec3(1.0), 0.45), clamp(data, 0.0, 1.0));
          float a = (0.26 + 0.23 * vD + 0.78 * data + 0.6 * surge) * u_dens;
          gl_FragColor = vec4(calm(col, u_bg, u_calm + 0.34), a);
        }`,
    }));
    mLink.frustumCulled = false;
    S.add(mLink);

    // 3 ── the lit joint at every vertex, as drawDodec draws them
    const dv = new TH.DodecahedronGeometry(1, 0);
    const dvPos = dv.getAttribute('position');
    const jp = [], jc = [], jn = [];
    for (let i = 0; i < N; i++) {
      const n = nodes[i];
      for (let v = 0; v < dvPos.count; v++) {
        jp.push(dvPos.getX(v) * n.r, dvPos.getY(v) * n.r, dvPos.getZ(v) * n.r);
        jc.push(0, 0, 0);
        jn.push(n.ph, n.tone, i);
      }
    }
    dv.dispose();
    const gJoint = new TH.BufferGeometry();
    gJoint.setAttribute('position', new TH.Float32BufferAttribute(jp, 3));
    gJoint.setAttribute('ctr', new TH.Float32BufferAttribute(jc, 3));
    gJoint.setAttribute('nd', new TH.Float32BufferAttribute(jn, 3));
    const mJoint = new TH.Points(gJoint, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false,
      blending: TH.AdditiveBlending,
      vertexShader: `
        attribute vec3 nd;
        varying vec2 vN; varying float vD;
        uniform float u_t; uniform vec2 u_res; uniform vec3 u_np[${N}];
        ${SPIN}
        void main(){
          vN = nd.xy;
          vec3 p = u_np[int(nd.z)] + spin(position, nd.x, u_t);
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          vD = clamp(1.0 - (-mv.z) / 26.0, 0.0, 1.0);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = (1.6 + 2.0 * vD) * (u_res.y / 900.0 + 0.6);
        }`,
      fragmentShader: `
        ${SF_CALM}
        varying vec2 vN; varying float vD;
        uniform vec3 u_acc,u_acc2,u_bg; uniform float u_dens,u_calm;
        void main(){
          float d = length(gl_PointCoord - 0.5);
          if(d > 0.5) discard;
          vec3 col = mix(u_acc, u_acc2, vN.y);
          // the white highlight drawDodec puts in the middle of each joint
          col = mix(col, vec3(1.0), smoothstep(0.28, 0.0, d) * 0.4);
          float a = (1.0 - smoothstep(0.32, 0.5, d)) * (0.13 + 0.21 * vD) * u_dens;
          gl_FragColor = vec4(calm(col, u_bg, u_calm + 0.4), a);
        }`,
    }));
    mJoint.frustumCulled = false;
    S.add(mJoint);

    S.__nodes = nodes;          // read by tools/ probes
    S.update = f => {
      sFeed(u, f);
      physics(Math.min(0.05, f.dt), f.e);
      // a slow orbit, so the solids are seen turning against a moving camera
      cam.position.set(Math.sin(f.t * 0.06) * 2.2 + f.cam * 2.0,
                       Math.cos(f.t * 0.045) * 1.2,
                       11 - f.e * 1.2);
      cam.lookAt(0, 0, -2);
    };
    S.resize = (w, h) => {
      u.u_res.value.set(w, h); cam.aspect = w / h; cam.updateProjectionMatrix();
    };
    return S;
  },

  /* Terminal — a curved phosphor screen. This one genuinely is a single
     full-screen shader: barrel distortion, scanlines, a rolling refresh bar,
     grain and a vignette, all of which are per-pixel by nature. */
  crt(TH, c) {
    const cam = new TH.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const S = sScene(TH, cam, 0, 1.0);
    const u = sU(TH, c);
    S.add(sBackdrop(TH, `
      ${SF_LIB}
      ${SF_CALM}
      varying vec2 vUv;
      uniform vec3 u_bg,u_acc,u_acc2; uniform vec2 u_res;
      uniform float u_t,u_e,u_shock,u_pulse,u_dens,u_light,u_calm;
      void main(){
        // barrel: the glass is curved, so the raster is too
        vec2 p = vUv * 2.0 - 1.0;
        p *= 1.0 + 0.055 * dot(p, p);
        vec2 uv = p * 0.5 + 0.5;
        if(uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0){
          gl_FragColor = vec4(u_bg * 0.35, 1.0); return;
        }
        vec3 col = u_bg;
        // drifting phosphor field — what the tube shows with no signal. This
        // has to be genuinely visible: a CRT you can only see in a screenshot
        // if you know where to look is not a CRT, it is a dark rectangle.
        float f = fbm(uv * vec2(3.0, 8.0) + vec2(u_t * 0.05, u_t * 0.11));
        col = mix(col, u_acc, f * (0.30 + 0.22 * u_e) * u_dens);
        // aperture grille: the vertical triads a real tube is made of
        col *= 0.72 + 0.28 * sin(uv.x * u_res.x * 1.05);
        // character-cell ghosts, marching a row at a time
        float cells = step(0.72 , fract(uv.x * 90.0)) * step(0.55, fract(uv.y * 42.0));
        col += u_acc * cells * 0.22 * u_dens
             * step(0.55, h21(floor(uv * vec2(90.0, 42.0)) + floor(u_t * 3.0)));
        // scanlines
        col *= 0.72 + 0.28 * sin(uv.y * u_res.y * 1.4);
        // rolling refresh bar — one pass down the tube, faster when busy
        float roll = fract(uv.y + u_t * (0.06 + 0.22 * u_e));
        col += u_acc * (0.22 + 0.2 * u_e) * pow(1.0 - roll, 9.0);
        // the launch shock: the whole raster overbrightens and snaps back
        col += u_acc2 * u_shock * 0.45;
        col += u_acc * u_pulse * 0.18 * step(0.5, fract(uv.y * 3.0 - u_t));
        // grain + vignette
        col += (h21(uv * u_res + fract(u_t) * 300.0) - 0.5) * 0.05;
        col *= 1.0 - 0.45 * pow(length(p) * 0.62, 3.0);
        gl_FragColor = vec4(calm(col, u_bg, u_calm), 1.0);
      }`, u));
    S.update = f => sFeed(u, f);
    S.resize = (w, h) => u.u_res.value.set(w, h);
    return S;
  },

  /* Brutalist — a monochrome halftone grid. No colour, no bloom, no easing.
     Dots scale from a rippling field; an impulse throws a hard ring across it. */
  brutal(TH, c) {
    const cam = new TH.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const S = sScene(TH, cam, 0, 1.0);
    const u = sU(TH, c);
    S.add(sBackdrop(TH, `
      ${SF_CALM}
      varying vec2 vUv;
      uniform vec3 u_bg,u_acc; uniform vec2 u_res;
      uniform float u_t,u_e,u_shock,u_pulse,u_dens,u_light,u_calm;
      void main(){
        float asp = u_res.x / max(1.0, u_res.y);
        vec2 p = vec2(vUv.x * asp, vUv.y);
        float grid = 34.0;
        vec2 cell = fract(p * grid) - 0.5;
        vec2 id = floor(p * grid);
        // radius per dot: a slow wave, a shock ring, a nav pulse. All stepped —
        // this skin does not ease anything.
        float wave = sin(id.x * 0.4 + u_t * (0.5 + 1.6 * u_e))
                   * cos(id.y * 0.35 - u_t * (0.4 + 1.2 * u_e));
        float r = 0.22 + 0.17 * wave;
        vec2 ctr = vec2(asp * 0.5, 0.5);
        float d = distance(p, ctr);
        r += u_shock * 0.34 * exp(-abs(d - (1.0 - u_shock) * 0.9) * 9.0);
        r += u_pulse * 0.18 * step(fract(d * 6.0 - u_t), 0.4);
        r *= u_dens;
        float dot_ = step(length(cell), r);
        // hard two-tone at real contrast: brutalism is not a whisper. No
        // gradient, no antialiasing on the dot edge, one ink colour.
        vec3 ink = mix(u_acc, vec3(1.0) - u_bg, 0.35);
        gl_FragColor = vec4(calm(mix(u_bg, ink, dot_ * 0.62), u_bg,
                                 0.35 + 0.65 * u_calm), 1.0);
      }`, u));
    S.update = f => sFeed(u, f);
    S.resize = (w, h) => u.u_res.value.set(w, h);
    return S;
  },
};

/* ── wiring ───────────────────────────────────────────────────────────────
   The stage only exists once the deferred module bootstrap in index.html has
   resolved. Until then (and forever, if it never does) the static CSS gradient
   is the background and nothing here has run. */
window.addEventListener('vendor-ready', () => {
  if (window.STAGE_WANT !== false) STAGE.boot();
});
window.addEventListener('vendor-failed', () => STAGE._static());
window.addEventListener('resize', () => STAGE.resize());

window.STAGE = STAGE;
