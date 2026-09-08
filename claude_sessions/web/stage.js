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
     · Render scale below 1 and the display ratio deliberately IGNORED. A soft
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

       THE GRAPH SCENE IS THE NAMED EXCEPTION, and it is worth reading why
       before applying either rule to it. It is the only scene here built
       against a supplied 3D model rather than a photograph, and its subject is
       glass tubes with specular highlights meeting at glass junctions — an
       object, not a field. Every pass in it used to be additive with
       depthWrite off, and an additive scene with no depth cannot have a
       silhouette: nothing occludes anything, so the frame that IS the
       recognisable part of a cluster was invisible inside its own cluster. Its
       solids are InstancedMesh over MeshPhysicalMaterial now, with a lighting
       model and an environment map, and the version fragility above is pinned
       by three being vendored here at a known revision rather than resolved.
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
  //: brightness preference, 0 = follow the skin. See setGlow()/_calm().
  glowPct: 0, _zen: false, _zenTier: null,
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
      /* EVERY SHADER IN THIS FILE WRITES FINAL DISPLAY VALUES, so three must
         not colour-manage them. It is the same fact the site's journey scene
         already records as the reason it cannot have a bloom pass — and here
         it was showing up as a bug with a much more confusing symptom.

         With colour management on, the composer path and the direct path
         disagree. lite renders straight to the canvas and is correct;
         cinematic renders into a linear render target and the blit to screen
         encodes it to sRGB a second time, which lifts the DARK values hardest:
         the page's own #0a0c10 background came out at #3a3f4b. What that looks
         like is a flat grey sheet over the whole scene that appears the moment
         bloom is switched on — measured, not guessed: (13,15,21) on lite
         against (58,63,75) on cinematic, from the same frame.

         Turning it off is what makes the two tiers agree. It is not a
         concession for six of the seven scenes: they have no lighting model,
         no textures and no colours arriving from anywhere but the palette, so
         there is nothing for a linear working space to be more correct about.

         The graph scene DOES have one, and it does not need the working space
         either — what it needs is a tone curve, which is a different thing and
         is set immediately below. Its lit materials opt into ACES; its raw
         shaders, like every other scene's, are untouched by it. */
      if (TH.ColorManagement) TH.ColorManagement.enabled = false;
      if (TH.LinearSRGBColorSpace) ren.outputColorSpace = TH.LinearSRGBColorSpace;
      /* ACES, and ONLY the graph scene's lit solids opt into it.

         Everything above is about colour SPACE; this is about what happens
         above 1.0, and it is the problem this file has been solving by hand
         for rounds. "Two pale colours added together are white" is the note on
         four separate passes, and the answer each time was another pow() on
         the hue before it was summed — an approximation of a tone curve,
         written out four times. A filmic curve rolls the highlight off with
         its hue intact instead of clipping every channel to 1 at a different
         point, which is exactly what turned a violet cluster white the moment
         it was lit.

         three applies it per material, to materials that ask (`toneMapped`),
         so it reaches the graph scene's MeshPhysicalMaterials and NOTHING
         else: the six raw-ShaderMaterial scenes are untouched, on both tiers,
         and the lite/cinematic agreement measured above still holds. */
      if (TH.ACESFilmicToneMapping) ren.toneMapping = TH.ACESFilmicToneMapping;
      ren.toneMappingExposure = 1.0;
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
      // the renderer goes in because the graph scene builds an environment
      // map with PMREMGenerator, which needs one. Every other scene ignores it.
      this._sc = mk(TH, this._colors(), this._ren);
    } catch (e) { this._giveUp('scene build failed: ' + e.message); return; }
    this._ren.setPixelRatio(this._ratio());
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
      // Radius 0.28, not 0.5. The threshold rule already recorded here is
      // "0.55, because at 0.2 a neon scene becomes an undifferentiated colour
      // spill" — the radius is the same argument one step later. At 0.5 the
      // glow off a hull's 42 white beads merges into a single white ball and
      // the cage inside it stops having a colour at all, which is how a field
      // of violet, gold, green and cyan clusters came out uniformly white-blue.
      // Tight glow keeps the flare ON the bead and leaves the hull its hue.
      c.addPass(new P.UnrealBloomPass(sz, strength, 0.28, 0.55));
      c.addPass(new P.OutputPass());
      c.setSize(sz.x, sz.y);
      this._post = c;
    } catch (e) { console.warn('[stage] bloom unavailable', e); this._post = null; }
  },

  /* HOW MANY PIXELS THE SCENE IS DRAWN INTO.
     Outside zen this is unchanged: STAGE_SCALE (0.75), the display ratio ignored
     — a background is a soft full-screen field and paying for a 4K one behind
     opaque cards is waste. That is still the right call, and it is the opposite
     of the instruments' clamp-to-2, which exists because they draw hairline
     arcs.

     Zen is where that reasoning inverts, and the scene changed under it too.
     The app is hidden, nothing else is competing for the frame, and what is on
     screen is now thin glass rods and 42 small beads per cage — hairlines, in
     other words, and at 0.75 they crawl and stair-step. So zen supersamples:
     the display's own ratio, floored at 1.5 so a plain 1x monitor still gets
     more than one sample per pixel, capped at 2 because past that it is
     quadratic cost for nothing anyone can see.

     Supersampling and not MSAA on purpose: antialias can only be chosen when
     the context is created, and it does not reach EffectComposer's render
     targets anyway — so it would sharpen the tier that has no bloom and leave
     the one that does exactly as it was. */
  _ratio() {
    const base = (this._sc && this._sc.scale) || STAGE_SCALE;
    if (!this._zen) return base;
    const dpr = window.devicePixelRatio || 1;
    return Math.min(2, Math.max(1.5, dpr));
  },

  _colors() {
    const TH = this._th, p = this._pal || {};
    const C = h => new TH.Color(h || '#7dcfff');
    return {
      acc: C(p.accent), acc2: C(p.accent2), glow: C(p.glow || p.accent),
      bg: C(p.bg), panel: C(p.panel || p.bg), warn: C(p.warn),
      ok: C(p.ok || p.accent),
      // THE MAGENTA. The reference cluster holds violet AND magenta at once,
      // and until this line the stage had no uniform that could be one — every
      // hue it could reach was cool, gold or green. `err` is the palette's
      // existing magenta/pink and it is a ROLE here, exactly as warn is gold
      // and ok is green: no palette gets a colour baked into it.
      err: C(p.err || p.accent2),
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
  /* THE ONE THING ALLOWED TO LIFT THE CEILING — see SF_CALM below.
     calm keeps the scene a ground rather than a competitor to the interface.
     In zen there is no interface: the app is hidden and this canvas is the
     only thing on screen, so the ceiling that makes it a background is exactly
     what makes it invisible. It RAISES the skin's own value rather than
     replacing it, so a quiet skin stays quieter than a loud one, and it is
     capped below 1 so a bright skin cannot wash out to flat colour.

     The lift is SMALL — 0.12 on the ceiling and 1.12 on the gain — and it was
     briefly 0.4 and 1.7. That first cut was compensating for two real bugs
     elsewhere: the depth haze started at 7 units when nothing in the field is
     closer than 15, and the composer path was sRGB-encoding an already-encoded
     frame. With both fixed the scene is bright at rest, and zen cranking it
     further just blew it out ("it gets really bright and doesn't look as
     good"). Zen is the same theme with nothing on top of it, not a louder one;
     if someone wants louder there is a slider for that.

     Three knobs, not one, because tier and density matter as much as colour:
       · dens is the per-PAGE density, and in zen there is no page — every
         route dims the field by up to a fifth for content that is not there.
       · lite is the default tier and it drops EffectComposer entirely, so
         there is no bloom pass at all. Every white-hot bead in the reference
         image is a bloom artefact. Zen is the one moment nothing else is
         competing for the frame budget, so it can afford the full tier.
     off is left alone deliberately: zen must not switch a stage back on that
     the user turned off. */
  /* How bright the background is allowed to be, as a percentage of what the
     skin authored. 0 means "follow the skin", the same convention surface
     uses for panel opacity, and for the same reason: this is a taste question
     — it was tuned to one verdict ("overstimulating, confonde") and then to its
     opposite ("too dim, I can't see anything"), which is what a constant
     standing in for a preference looks like. */
  setGlow(pct) {
    const v = Math.max(0, Math.min(240, Number(pct) || 0));
    if (v === this.glowPct) return;
    this.glowPct = v;
    this.kick();
  },
  /* THE CEILING, resolved — the one place the three inputs meet, and the order
     they compose in is deliberate:
       the skin's authored value is the BASE,
       the user's preference SCALES it, so a preference means the same thing on
         every skin instead of flattening them all to one number,
       zen ADDS on top, because it is a mode and not a taste.
     Capped below 1 whatever they say: a scene that reaches 1.0 has stopped
     being mixed toward the page at all, and a bright skin washes out flat. */
  _calm() {
    const base = this.calmOf != null ? this.calmOf : 0.3;
    const k = this.glowPct > 0 ? this.glowPct / 100 : 1;
    return Math.min(0.95, base * k + (this._zen ? 0.12 : 0));
  },
  /* The OTHER half of brightness, and the half the first cut missed.
     calm decides how far a colour comes up off the page background, and it
     SATURATES: the graph scene at zen already sits at the 0.95 cap, its colours
     already full strength — and it still read as dim. Because in an
     alpha-composited scene what you actually see is colour x alpha over a
     near-black page, and every pass there spends most of its alpha on depth.
     Full-strength colour at 0.2 alpha over black is a dark pixel.

     So gain multiplies dens, which every scene already folds into its alpha
     for exactly this reason — no new uniform, no shader that has to know about
     it, and the two scenes that write opaque pixels are unaffected because
     alpha is not what they are modulating. */
  _gain() {
    const k = this.glowPct > 0 ? this.glowPct / 100 : 1;
    return Math.min(2.2, k * (this._zen ? 1.12 : 1));
  },
  zen(on) {
    on = !!on;
    if (on === !!this._zen) return;
    this._zen = on;
    if (on) {
      this._zenTier = this.tier;
      this._densTgt = 1;
      if (this.tier === 'lite') this.setTier('cinematic');
    } else {
      this._densTgt = stagePage(this._pageKey).d;
      if (this._zenTier && this._zenTier !== this.tier) this.setTier(this._zenTier);
      this._zenTier = null;
    }
    // the render scale changes with the mode, and setPixelRatio alone does not
    // resize the drawing buffer — resize() is what actually re-allocates it,
    // and the composer's two targets with it
    if (this._ren) { this._ren.setPixelRatio(this._ratio()); this.resize(); }
    this.kick();
  },
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
                 pulse: this._pulse, dens: this._dens * this._gain(),
                 cam: this._cam, calm: this._calm()});
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
  const bag = [], extra = [];
  return {
    scene, camera, bloom, scale,
    add(o) { scene.add(o); bag.push(o); return o; },
    dispose() {
      for (const o of bag) {
        scene.remove(o);
        /* traverse(), not a two-line check on the object itself. The graph
           scene's solids are a THREE.Group of InstancedMesh, and a Group has
           neither .geometry nor .material — so the version that looked only at
           the top object freed nothing, on the one path that runs every time
           the theme picker is hovered. */
        o.traverse ? o.traverse(k => {
          if (k.geometry) k.geometry.dispose();
          if (k.material) k.material.dispose();
        }) : 0;
      }
      for (const f of extra) { try { f(); } catch (e) {} }
      extra.length = 0;
      bag.length = 0;
    },
    //: anything else the scene made that is not in the graph — an environment
    //: map, a PMREM generator. Freed in the same pass, so a scene has ONE place
    //: to give things back.
    onDispose(f) { extra.push(f); },
  };
}
function sU(TH, c) {
  return {
    u_t: {value: 0}, u_e: {value: 0}, u_shock: {value: 0}, u_pulse: {value: 0},
    u_dens: {value: 1}, u_res: {value: new TH.Vector2(1, 1)},
    u_calm: {value: 0.3},
    u_acc: {value: c.acc}, u_acc2: {value: c.acc2}, u_glow: {value: c.glow},
    u_bg: {value: c.bg}, u_panel: {value: c.panel}, u_warn: {value: c.warn},
    u_ok: {value: c.ok}, u_err: {value: c.err || c.acc2},
    // white is a role like any other, so a shader never writes a bare vec3(1)
    // and the six roles can be indexed by a single number. See SF_ROLE.
    u_white: {value: new TH.Color(0xffffff)},
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

/* The constellation's five hues, in the weights the reference image has: violet,
   indigo, cyan, gold, green — five sevenths cool, two sevenths warm, so gold and
   green read as accents and not as a second family.

   u_warn has been bound by sU() since the stage was written and no shader in the
   graph scene ever read it; u_ok is bound now for the same reason. That is why
   adding two hues to the field costs a step chain and no new plumbing.

   step() rather than a branch chain, and the caller's t is constant across a
   cage, so interpolation lands on an exact stop rather than between two. Whoever
   passes t must keep it below 1.0 — fract() sends 1.0 back to the first stop. */
const SF_HUE5 = `
vec3 hue5(float t){
  float k = fract(t);
  vec3 col = u_acc2;
  col = mix(col, mix(u_acc2, u_acc, 0.55), step(0.125, k));
  col = mix(col, u_acc,  step(0.375, k));
  col = mix(col, u_warn, step(0.625, k));
  col = mix(col, u_ok,   step(0.875, k));
  return col;
}`;

/* THE SIX ROLES, INDEXED. A cluster wears a CHORD of four of them, and the
   chord is carried as four indices in one attribute rather than four colours —
   which is what keeps a per-cluster palette to one vec4 instead of four vec3s
   per vertex, and what lets the same number mean the same hue in all three
   renderers (claude_sessions/cluster_spec.py owns the numbering).

   step() rather than a branch chain: the index is constant across an instance,
   so nothing interpolates and every comparison lands on an exact value. */
const SF_ROLE = `
uniform vec3 u_acc, u_acc2, u_err, u_warn, u_ok, u_white;
vec3 roleCol(float r){
  vec3 c = u_acc;
  c = mix(c, u_acc2, step(0.5, r));
  /* the magenta role, pulled a third of the way toward the violet accent.
     err is a SALMON in most palettes (#f7768e here) because its real job is
     to read as a failure against body text, and used raw it made every cluster
     coral. The reference's magenta is violet-leaning — pushing the role rather
     than naming a colour keeps all 32 palettes working and lands the hue where
     the render has it. */
  c = mix(c, mix(u_err, u_acc2, 0.45), step(1.5, r));
  c = mix(c, u_warn, step(2.5, r));
  c = mix(c, u_ok,   step(3.5, r));
  c = mix(c, u_white, step(4.5, r));
  return c;
}`;

/* NEVER REDUCE A CLUSTER TO A SINGLE FLAT COLOUR — the whole reason this
   function replaced hue5().

   hue5(tone) took one number that was CONSTANT across a cluster, so a cluster
   was one hue by construction and no amount of tuning inside that could produce
   the reference, where a single cluster runs violet into magenta into cyan with
   gold picking out individual struts. chord() takes the cluster's four roles
   and a position-derived t, so the colour varies ACROSS the geometry.

   Three stops and a highlight, not four equal quarters: a four-way even blend
   is a stripe, and the transitions have to overlap or the boundaries read as
   bands. The highlight is a GATE, not a stop — it is what puts a few white-hot
   and gold pixels on an otherwise violet cluster. */
const SF_CHORD = `
vec3 chord(vec4 pal, float t, float hot){
  vec3 a = roleCol(pal.x), b = roleCol(pal.y), c = roleCol(pal.z);
  /* Weighted, not three even thirds. Counted off the reference: a violet
     cluster is roughly six parts its primary, three its secondary and one its
     accent — an even split put as much magenta on it as violet and the field
     came out pink. The overlap between the two stops is what keeps it a blend
     rather than two bands. */
  vec3 col = mix(a, b, smoothstep(0.52, 0.88, t));
  col = mix(col, c, smoothstep(0.86, 1.0, t));
  return mix(col, roleCol(pal.w), clamp(hot, 0.0, 1.0));
}`;

/* Where a fragment sits in its cluster's gradient, in 0..1. Every input the
   brief names is in here and each one is doing a different job:

     angular   dot(dir, axis)  — the gradient has a DIRECTION, per cluster, so
                                 two clusters wearing the same chord still do
                                 not look like the same object rotated
     radial    length(local)   — the centre is a different colour from the rim,
                                 which is what "internally illuminated" means
     noise     value noise     — the break-up. Without it the blend is a clean
                                 sweep, and a clean sweep reads as a stripe;
                                 this is the difference between a gradient and
                                 something that looks lit from inside
     seed                      — offsets the noise per cluster, so the SAME
                                 chord is still a different picture

   3D value noise and not the 2D one in SF_LIB: this samples a position on a
   sphere, and a 2D noise projected onto one has a visible seam down the axis
   it dropped. Cheap hash, four lerps — a background does not need gradients. */
const SF_GRAD = `
float h31(vec3 p){ return fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453); }
float vnoise3(vec3 p){
  vec3 i = floor(p), f = fract(p);
  vec3 u = f * f * (3.0 - 2.0 * f);
  float a = mix(mix(mix(h31(i), h31(i + vec3(1,0,0)), u.x),
                    mix(h31(i + vec3(0,1,0)), h31(i + vec3(1,1,0)), u.x), u.y),
                mix(mix(h31(i + vec3(0,0,1)), h31(i + vec3(1,0,1)), u.x),
                    mix(h31(i + vec3(0,1,1)), h31(i + vec3(1,1,1)), u.x), u.y), u.z);
  return a;
}
float gradT(vec3 local, vec3 axis, float seed, float scale){
  vec3 d = local / max(length(local), 1e-4);
  float ang = dot(d, axis) * 0.5 + 0.5;
  float rad = clamp(length(local), 0.0, 1.2);
  float n = vnoise3(local * scale + seed * 31.7);
  return clamp(ang * 0.58 + rad * 0.20 + n * 0.34 - 0.06, 0.0, 1.0);
}`;

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

  /* Graph — THE homage, and the only scene in this file built against a
     supplied model rather than against a photograph.

     `notes/reference/cluster.glb` and `connection.glb` were measured into
     `claude_sessions/cluster_spec.py`, which generates `web/cluster-spec.js`
     (the `CLUSTER` object below) and `www/lib/cluster-spec.ts`. All three
     renderers of this object read those numbers, so "the GUI, the site and the
     architecture graph all draw the same cluster" is a fact the build enforces
     rather than a claim three files make separately.

     WHAT A CLUSTER IS, in the order the eye reads it:

       the frame     twelve big glass junctions joined by thirty tubes along an
                     icosahedron's edges, plus twenty spokes from a lit centre.
                     SOLID geometry, depth-written — this is the object.
       the centre    a white core with a gold seed in it, inside its own glass.
       the mesh      480 hairline rods and 162 small beads on the hull, and a
                     second 480-rod cage at 0.53 R inside it. Additive haze,
                     depth-TESTED against the frame so the frame occludes it.
       the interior  a population of motes and gold orbiters: nodes made of
                     nodes, which is the shape of this project's memory graph.

     THE TWO THINGS THIS REWRITE FIXED, and both were structural rather than a
     number that needed tuning:

     1. EVERY PASS WAS `depthWrite: false` AND ADDITIVE. An additive scene with
        no depth cannot have a silhouette: nothing occludes anything, so forty
        overlapping translucent things sum into one smear and the frame — the
        most recognisable feature of the reference — was invisible inside its
        own cluster. The frame, the junctions and the centre are now real
        instanced solids with a real lighting model, and the haze draws behind
        them. That is what turns a cloud of light into an object.

     2. A CLUSTER WAS ONE HUE BY CONSTRUCTION. `hue5(n.tone)` took a number that
        was constant across the cluster, so no amount of tuning inside it could
        produce the reference, where ONE cluster runs violet into magenta into
        cyan with gold picking out individual struts. Every cluster now wears a
        CHORD of four roles (cluster_spec.PALETTE_FAMILIES) and every pass reads
        `chord(pal, gradT(...), hot)` — a colour that varies across the geometry
        by angular position, radius and noise. The rule the brief calls the most
        important is the one this file broke: never reduce a cluster to a single
        flat colour.

     Cost: five InstancedMesh solids and five merged-buffer haze passes, all
     placed from uniform arrays in the vertex shader. The CPU integrates 40
     bodies and writes uniforms; it touches no geometry per frame.

     Node positions are deterministic — no Math.random anywhere — so the
     constellation is identical on every reload. A layout that reshuffles reads
     as noise. */
  graph(TH, c, ren) {
    const cam = new TH.PerspectiveCamera(55, 1, 0.1, 60);
    const S = sScene(TH, cam, .5, 1.0);
    const u = sU(TH, c);
    //: every measurement of the cluster and the conduit, generated from
    //: claude_sessions/cluster_spec.py. Referenced directly and not defensively:
    //: if it is missing the bundle is broken, and the scene build failing lands
    //: on the static background, which is the right answer to a broken bundle.
    const CL = CLUSTER;

    // ── node field ──
    const N = 40;
    const R_MAX = 1.60;
    //: the near face of the drift box (see BOUND below). The hero starts
    //: here so it is the closest thing to the camera from the first frame.
    const BOUND_Z_NEAR = 2.6;
    const nodes = [];
    /* WHERE THE CAGES START — a jittered 3D lattice, not a spiral.
       The spiral (golden angle, radius growing as sqrt(i/N)) is the right tool
       for spreading points on a DISC, and that is what it did: every body ended
       up on a ring with an empty middle, and once the links became "join your
       nearest neighbours" the picture was a necklace. The reference image is a
       volume — clusters at every depth, the near ones large and overlapping the
       far ones — so the seeding has to fill a box.

       5 x 4 x 2 is exactly N cells, so every cell gets one body and none
       collide at t=0; the jitter (±40% of a cell) is what stops it reading as
       a grid. Three DIFFERENT hash multipliers, and none of them is the one the
       radius uses: sharing a hash would correlate a cage's size with its
       position and put every large hull down one edge of the box. */
    const GX = 5, GY = 4, GZ = 2;
    /* THE CHORD A CLUSTER WEARS. Four ROLE indices — primary, secondary,
       accent, highlight — picked from cluster_spec.PALETTE_FAMILIES by a
       deterministic hash. The family weights are counted off the reference
       field rather than balanced by eye: violet is not merely first, it is
       forty per cent, and what the field has to read as is a violet field with
       other colours in it rather than a blue field with violet in it.

       This is the direct replacement for TONES + hue5(). A tone was ONE stop on
       a shared ramp and therefore one colour for a whole cluster; a chord is
       four, and `chord()` in the shader walks between them by position. */
    const FAM = CL.PALETTE_FAMILIES;
    const FAM_TOTAL = FAM.reduce((t, f) => t + f[0], 0);
    const famFor = seed => {
      let at = (seed - Math.floor(seed)) * FAM_TOTAL, acc = 0;
      for (const f of FAM) { acc += f[0]; if (at < acc) return f; }
      return FAM[FAM.length - 1];
    };
    for (let i = 0; i < N; i++) {
      const gx = i % GX, gy = Math.floor(i / GX) % GY, gz = Math.floor(i / (GX * GY));
      const j1 = (((i * 4657 + 12345) % 233280) / 233280 - 0.5) * 0.8;
      const j2 = (((i * 7919 + 104729) % 233280) / 233280 - 0.5) * 0.8;
      const j3 = (((i * 2749 + 30011) % 233280) / 233280 - 0.5) * 0.8;
      // Size follows a LONG TAIL, not a uniform spread: a handful of large hubs
      // among many small leaves. Raising a flat hash to a power is what does it
      // — a linear ramp gives forty cages of forgettably similar size, which is
      // what the first cut had. Same read the real architecture graph gives,
      // where a module dwarfs a leaf. The exponent is 4 and not 3 because the
      // reference constellation's tail is longer than the old one's: mean 0.40
      // against a maximum of 1.60 is what "three or four dominant hulls among
      // dozens of specks" measures as. Deterministic hash, so the field is
      // identical on every reload.
      //
      // The hash is fract(sin(i * 12.9898) * 43758.5453), the same one every
      // shader in this file uses, and NOT the linear-congruential
      // (i*9301+49297) % 233280 that was here. That one is not random enough
      // over 40 consecutive integers to be used as one: it put the only three
      // values above the hub threshold at i = 17, 18, 19 — three adjacent
      // lattice cells — so all three large hulls appeared in one corner of the
      // box and the rest of the frame was specks. Measured, after the lattice
      // seeding made it visible.
      const sh = Math.sin(i * 12.9898) * 43758.5453;
      const h = sh - Math.floor(sh);
      // Floor 0.16 and exponent 3.4, not 0.10 and 4. The tail is still long
      // — three or four dominant hulls among dozens — but the reference FIELD
      // is a packed frame, and at the old floor half the field was specks with
      // nothing but bare conduit between them. Raising the floor fills the
      // frame without moving bodies closer together, which is the thing the
      // drift cannot absorb: the lattice already packs 40 bodies densely and
      // the old speeds turned a drift into a permanent collision cascade.
      const r = 0.16 + Math.pow(h, 3.4) * 1.44;
      // A THIRD hash, independent of both the position jitter and the radius:
      // sharing one would tie a cluster's colour to its size, and the reference
      // field has large gold clusters and tiny violet ones.
      const sp = Math.sin(i * 45.233 + 7.13) * 21473.7;
      const seed = sp - Math.floor(sp);
      const fam = famFor(seed);
      // the gradient's DIRECTION, per cluster. Two clusters wearing the same
      // chord still must not look like the same object rotated, and this is
      // the cheapest thing that separates them.
      const a1 = seed * 6.2831853, a2 = ((i * 2.399963) % 3.14159265);
      nodes.push({
        x: ((gx + 0.5 + j1) / GX * 2.0 - 1.0) * 10.0,
        y: ((gy + 0.5 + j2) / GY * 2.0 - 1.0) * 5.2,
        /* THE BOX IS DEEP, and that is where the background network comes
           from. The brief asks for distant clusters — smaller, dimmer, fading
           into darkness rather than a flat starfield — and at a span of 3.4
           there was no BACK of the field: every cage sat within a couple of
           units of the camera plane, so the frame had a foreground and empty
           black behind it. 6.6 deep and pushed back 4.6 puts a third of them
           past 18 units, where vFar and the LOD ladder already make them
           small, soft and mixed toward the ground with nothing new to draw. */
        z: ((gz + 0.5 + j3) / GZ * 2.0 - 1.0) * 6.6 - 4.6,
        r,
        // mass by volume. Without this the collision below is equal-mass and a
        // pea deflects a boulder, which looks wrong the moment sizes differ.
        m: r * r * r,
        ph: (i * 1.7) % 6.283,
        seed,
        fam: fam[1],
        pal: fam[2],
        axis: [Math.cos(a1) * Math.sin(a2), Math.cos(a2), Math.sin(a1) * Math.sin(a2)],
        // how coarse the noise that breaks the gradient up is. Per cluster, so
        // one is mottled and its neighbour is smooth.
        ns: 1.8 + seed * 3.2,
        //: kept for tools/inspect_cluster.py, which prints it
        tone: seed,
      });
    }

    /* Satellites — a hub with its own retinue.
       In the reference image the small hulls are not scattered independently:
       they hang just off the big ones, sometimes touching. The long-tail radius
       already gives the right SIZES, but every body is placed by the same
       spiral, so the RELATIONSHIP never appears and the field reads as forty
       unrelated objects of assorted size.

       A third of the leaves get tethered to a hub. The tether is a weak spring
       in physics() and not a fixed offset, because a fixed offset would be a
       rigid body: the collision term still decides how close a satellite may
       get, and the drift still makes each orbit irregular. */
    const HUB_R = 0.9, LEAF_R = 0.45;
    const hubs = [];
    for (let i = 0; i < N; i++) if (nodes[i].r >= HUB_R) hubs.push(i);
    for (let i = 0; i < N; i++) {
      const n = nodes[i];
      n.sat = -1;
      if (!hubs.length || n.r > LEAF_R || i % 3 !== 0) continue;
      const h = hubs[i % hubs.length];
      if (h === i) continue;
      n.sat = h;
      const a = i * 2.399963, d = (nodes[h].r + n.r) * 1.9;
      n.x = nodes[h].x + Math.cos(a) * d;
      n.y = nodes[h].y + Math.sin(a) * d * 0.7;
      n.z = nodes[h].z + Math.sin(a * 1.7) * d * 0.5;
    }

    /* THE HERO — one cluster brought to the front, close enough to read.
       Every cage was at roughly the same distance, so every cage was roughly
       the same size on screen and none of them could be LOOKED at: the cage,
       the population inside it and the beads on its surface are three separate
       pieces of structure and at 40px across they are one grey speck. Depth
       exists in this scene precisely so that something can be near.

       It is the largest cage, not a 41st body: adding one would break the
       5x4x2 lattice, and the biggest hull is the one whose interior is worth
       coming close to. It keeps its physics — it drifts, it collides, its
       satellites still orbit it — but at a quarter speed, so it stays in the
       foreground for minutes rather than wandering off in seconds. */
    let hero = 0;
    for (let i = 1; i < N; i++) if (nodes[i].r > nodes[hero].r) hero = i;
    nodes[hero].hero = true;
    nodes[hero].x *= 0.45;                      // off the exact centre, not out of frame
    nodes[hero].y *= 0.35;
    nodes[hero].z = BOUND_Z_NEAR;               // the near face of the box

    //: LOD by the cluster's own size, from the spec's ladder. A 480-rod shell
    //: inside eight pixels is a solid disc — the same failure the GIF renderer
    //: had to fix by apparent size.
    for (const n of nodes) {
      n.lod = n.r < CL.LOD_BREAKS[0] ? 0 : n.r < CL.LOD_BREAKS[1] ? 1 : 2;
    }

    /* PER-CLUSTER DATA AS UNIFORM ARRAYS, not as vertex attributes.
       Four numbers describe a cluster's look — its chord, its gradient axis,
       its phase/seed/noise scale and its radius — and every one of the ten
       passes needs all of them. Carried per vertex that is seven floats on
       roughly a quarter of a million vertices; carried as uniforms indexed by
       the node number it is 120 vectors, once, and the passes then differ only
       in which index they look up. Same argument as u_np, which already had to
       exist because the physics moves the clusters every frame. */
    u.u_pal = {value: nodes.map(n => new TH.Vector4(n.pal[0], n.pal[1], n.pal[2], n.pal[3]))};
    u.u_axis = {value: nodes.map(n => new TH.Vector3(n.axis[0], n.axis[1], n.axis[2]))};
    u.u_nd = {value: nodes.map(n => new TH.Vector4(n.ph, n.seed, n.ns, n.r))};

    /* ── the cages drift, and they bump into each other ────────────────────
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
      // A THIRD of what this was. The seeding changed from a spiral on a disc
      // to a 5x4x2 lattice inside a smaller box, which packs the same 40 bodies
      // far more densely — so the same starting speeds turned a slow drift into
      // a permanent collision cascade, and the field read as jittering rather
      // than moving. Density and speed are one dial with two names.
      VEL[i * 3]     = Math.cos(a) * 0.075 + Math.sin(b) * 0.028;
      VEL[i * 3 + 1] = Math.sin(a) * 0.055 + Math.cos(b) * 0.024;
      VEL[i * 3 + 2] = Math.sin(b * 1.7) * 0.034;
    }
    u.u_np = {value: Array.from({length: N}, (_, i) =>
      new TH.Vector3(POS[i * 3], POS[i * 3 + 1], POS[i * 3 + 2]))};

    const BOUND = [11.5, 6.2, 11.5];    // the box they are kept inside
    function physics(dt, e) {
      // busier workspace, livelier lattice — but the floor is a drift, not a
      // scurry. The energy term still doubles it, which is the part that has to
      // stay legible; what was wrong was the resting speed underneath it.
      const sp = 0.18 + 0.5 * e;
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
          // restitution 0.35, not 0.9: nearly elastic bodies in a dense box
          // trade momentum forever. These are drifting cages, not billiards.
          const ti = (2 * mj / mt) * (vj - vi) * 0.35;
          const tj = (2 * mi / mt) * (vi - vj) * 0.35;
          VEL[i * 3] += nx * ti; VEL[i * 3 + 1] += ny * ti; VEL[i * 3 + 2] += nz * ti;
          VEL[j * 3] += nx * tj; VEL[j * 3 + 1] += ny * tj; VEL[j * 3 + 2] += nz * tj;
        }
      }
      // the satellite tether: pull toward the hub when the drift has taken it
      // too far, push away when the collision has jammed it too close. Applied
      // to VELOCITY and not to position, so the retinue keeps orbiting rather
      // than snapping onto a shell.
      for (let i = 0; i < N; i++) {
        const h = nodes[i].sat;
        if (h < 0) continue;
        const dx = POS[h * 3] - POS[i * 3];
        const dy = POS[h * 3 + 1] - POS[i * 3 + 1];
        const dz = POS[h * 3 + 2] - POS[i * 3 + 2];
        const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1e-4;
        const f = (d - (nodes[h].r + nodes[i].r) * 1.9) * 0.10 * dt;
        VEL[i * 3] += (dx / d) * f;
        VEL[i * 3 + 1] += (dy / d) * f;
        VEL[i * 3 + 2] += (dz / d) * f;
      }
      for (let i = 0; i < N; i++) {
        // the hero drifts at a quarter speed: it is there to be looked at, and
        // something you are looking at should not leave while you look at it
        const spi = nodes[i].hero ? sp * 0.25 : sp;
        for (let k = 0; k < 3; k++) {
          const a = i * 3 + k;
          POS[a] += VEL[a] * dt * spi;
          // Reflect at the wall, and clamp back inside so a body can never
          // escape and drift off screen for the rest of the session. The limit
          // is inset by the radius, or a large solid half-leaves the frame while
          // its centre is still legally inside.
          const lim = Math.max(0.5, BOUND[k] - nodes[i].r);
          if (POS[a] > lim) { POS[a] = lim; VEL[a] = -Math.abs(VEL[a]); }
          else if (POS[a] < -lim) { POS[a] = -lim; VEL[a] = Math.abs(VEL[a]); }
          // Real drag, not a whisper. At 0.9995 a body kept whatever a
          // collision gave it for minutes, so the field accumulated energy
          // from its own bumps and never settled. 0.994 lets a knock decay in
          // a few seconds, which is what makes a collision read as an EVENT
          // rather than as the permanent state of the scene.
          VEL[a] *= 0.994;
        }
        u.u_np.value[i].set(POS[i * 3], POS[i * 3 + 1], POS[i * 3 + 2] - 3.0);
      }
    }

    /* rotate about the node's own centre, exactly as drawDodec does:
         ay spins around Y, then ax around X. A pure rotation, so the same
         function is valid for a NORMAL as for a position — which is what lets
         the solid pass spin its geometry in the shader and still be lit. */
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

    /* the geometry of an icosahedron, read off three rather than written down
       so a frame and the beads at its corners cannot disagree about where a
       corner is. EDGES(d) is the wireframe at detail d; CORNERS(d) is its
       distinct vertices, deduplicated out of the triangle soup — three hands
       back 240 positions for 42 corners, and drawing the soup would stack five
       or six copies on every one of them. */
    const EDGES = d => {
      const g = new TH.IcosahedronGeometry(1, d);
      const w = new TH.EdgesGeometry(g), wp = w.getAttribute('position');
      const out = [];
      for (let e = 0; e < wp.count; e += 2) {
        out.push([wp.getX(e), wp.getY(e), wp.getZ(e),
                  wp.getX(e + 1), wp.getY(e + 1), wp.getZ(e + 1)]);
      }
      g.dispose(); w.dispose();
      return out;
    };
    const CORNERS = d => {
      const g = new TH.IcosahedronGeometry(1, d), a = g.getAttribute('position');
      const seen = new Set(), out = [];
      for (let v = 0; v < a.count; v++) {
        const x = a.getX(v), y = a.getY(v), z = a.getZ(v);
        const key = x.toFixed(3) + '|' + y.toFixed(3) + '|' + z.toFixed(3);
        if (seen.has(key)) continue;
        seen.add(key); out.push([x, y, z]);
      }
      g.dispose();
      return out;
    };
    const SHELL = [EDGES(0), EDGES(1), EDGES(2)];
    const V_SHELL = CORNERS(2), V_FRAME = CORNERS(0);
    //: the 20 face centres — where a hub spoke points.
    const SPOKES = (() => {
      const g = new TH.IcosahedronGeometry(1, 0), a = g.getAttribute('position');
      const out = [];
      for (let f = 0; f < a.count; f += 3) {
        let x = 0, y = 0, z = 0;
        for (let k = 0; k < 3; k++) { x += a.getX(f + k); y += a.getY(f + k); z += a.getZ(f + k); }
        const L = Math.hypot(x, y, z) || 1;
        out.push([x / L, y / L, z / L]);
      }
      g.dispose();
      return out;
    })();

    /* ── LIGHT ────────────────────────────────────────────────────────────
       The rest of this file has no lighting model at all — every other scene
       writes final display values out of a raw ShaderMaterial, and that is
       still the right call for a soft full-screen field. A cluster is not a
       soft field: it is glass and metal tubes with specular highlights, and
       the single thing that separates the reference renders from every version
       we shipped is that theirs are LIT and ours were emissive smears.

       Three directional lights, not point lights: intensity is in candela for
       a point light and falls off with distance squared, so a scene whose
       bodies drift between 5 and 25 units away would have to re-tune its
       lights against the physics. A directional light is the same everywhere,
       which is what an art-directed key/fill/rim wants.

       The rim is MAGENTA. It is the reference's most obvious light and the
       cheapest way to get magenta onto a violet cluster without painting it
       there — a hue that arrives from a direction reads as illumination,
       where the same hue painted into the material reads as decoration. */
    /* A DEEP ALBEDO WITH A NARROW SPECULAR, not a bright albedo under a bright
       key. The references' tubes are saturated mid-dark blue and violet with a
       hot streak down one side; a pale albedo (these accents clear a contrast
       floor as TEXT) under a 1.05 white key is milk, which is what the field
       came out as the moment magenta stopped hiding it. The light lost a third
       and the albedo curve gained a half; the streak is the clearcoat's. */
    S.add(new TH.HemisphereLight(0xdfe9ff, 0x0a0e18, 0.09));
    const key = new TH.DirectionalLight(0xffffff, 0.72);
    key.position.set(-0.62, 0.78, 0.92);
    S.add(key);
    const fill = new TH.DirectionalLight(0x5fa8ff, 0.58);
    fill.position.set(0.86, -0.34, 0.52);
    S.add(fill);
    const rim = new TH.DirectionalLight(0xff4fd8, 0.85);
    rim.position.set(0.18, -0.72, -0.94);
    S.add(rim);

    /* ...and an ENVIRONMENT, which is what makes glass read as glass. A
       specular highlight from three lights gives three dots; a reflection
       gives the whole curved surface something to show. Generated with
       PMREMGenerator over a six-line gradient scene, so there is no asset to
       fetch and the GUI stays offline by construction — the same rule that
       forbids a webfont here. Built once, freed with the scene. */
    if (ren && TH.PMREMGenerator) {
      try {
        const pm = new TH.PMREMGenerator(ren);
        const es = new TH.Scene();
        const eg = new TH.SphereGeometry(12, 20, 14);
        const em = new TH.ShaderMaterial({
          side: TH.BackSide, depthWrite: false,
          uniforms: {u_acc: u.u_acc, u_acc2: u.u_acc2, u_err: u.u_err, u_bg: u.u_bg},
          vertexShader: `varying vec3 vP;
            void main(){ vP = normalize(position);
              gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
          fragmentShader: `varying vec3 vP;
            uniform vec3 u_acc, u_acc2, u_err, u_bg;
            void main(){
              // a cool sky, a violet floor and one magenta quadrant: three
              // things for a curved surface to reflect, which is all a
              // reflection needs to stop reading as a flat tint
              float up = vP.y * 0.5 + 0.5;
              vec3 col = mix(u_acc2 * 0.55, u_acc * 0.85, smoothstep(0.25, 0.95, up));
              col = mix(col, u_err * 1.1, smoothstep(0.35, 0.95, vP.x) * 0.55);
              gl_FragColor = vec4(mix(u_bg, col, 0.85), 1.0);
            }`,
        });
        es.add(new TH.Mesh(eg, em));
        const rt = pm.fromScene(es, 0.03);
        S.scene.environment = rt.texture;
        eg.dispose(); em.dispose(); pm.dispose();
        S.onDispose(() => { S.scene.environment = null; rt.dispose(); });
      } catch (e) { console.warn('[stage] no environment map', e); }
    }

    /* ── the solid pass ───────────────────────────────────────────────────
       Six InstancedMesh, two placement families, one shader injection.

       PLACEMENT IS IN THE SHADER, and `instanceMatrix` carries only where a
       part sits INSIDE its cluster. The cluster itself moves every frame (the
       physics above) and spins about its own centre, so a baked world matrix
       would have to be rewritten forty times a frame for nothing. So the
       standard `<project_vertex>` is replaced: it would apply instanceMatrix
       in world space, and we need it applied BEFORE the spin and the offset.

       `<defaultnormal_vertex>` is replaced for the same reason — a PBR
       material with an unrotated normal is lit as if the cluster were still,
       and the whole point of going lit is that the highlights travel across
       the tubes as they turn. It runs BEFORE `<begin_vertex>` in three's
       vertex shader (checked against the vendored r185, not assumed), which is
       why the conduit's axis frame is computed there and left in globals. */
    /* GLSL has no implicit int-to-float, so `${o.alpha}` for an alpha of 1
       emits `1` and every expression it lands in fails to compile — with the
       symptom being a scene that never appears and one console line. Every
       number substituted into a shader goes through this. */
    const F = v => (Number(v) || 0).toFixed(4);

    const N_UNI = `
      uniform float u_t; uniform vec3 u_np[${N}]; uniform vec3 u_axis[${N}];
      uniform vec4 u_pal[${N}]; uniform vec4 u_nd[${N}];
      attribute vec4 aI;`;

    //: the conduit's own frame, filled once per vertex and read by both chunks
    const LINK_FRAME = `
      vec3 gAx, gSx, gSz, gA, gB; float gSpan;
      void linkFrame(){
        int ia = int(aI.x), ib = int(aI.y);
        vec3 pa = u_np[ia], pb = u_np[ib];
        vec3 dv = pb - pa;
        float L = max(length(dv), 1e-4);
        gAx = dv / L;
        // the endpoint is pushed out of its own centre toward the other end,
        // and CLAMPED at a fraction of the gap: without that, two overlapping
        // hulls invert the segment and the conduit turns inside out
        gA = pa + gAx * min(u_nd[ia].w * ${F(CL.CONDUIT_REACH)}, L * ${F(CL.CONDUIT_CLAMP)});
        gB = pb - gAx * min(u_nd[ib].w * ${F(CL.CONDUIT_REACH)}, L * ${F(CL.CONDUIT_CLAMP)});
        gSpan = max(length(gB - gA), 1e-3);
        vec3 upv = abs(gAx.y) > 0.95 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 1.0, 0.0);
        gSx = normalize(cross(upv, gAx));
        gSz = cross(gAx, gSx);
      }`;

    /* ONE MATERIAL FACTORY. Every solid in the scene is a MeshPhysicalMaterial
       with the same injection and a different set of numbers, so "a junction is
       glass and a frame tube is not" is a config line rather than a shader.

       customProgramCacheKey is REQUIRED, not hygiene: three caches compiled
       programs by material type plus that key, so without it the first variant
       compiled would be handed to every other one and the whole cluster would
       draw with the junction's shader. */
    /* THE INJECTED CHUNKS, each a named string rather than a template nested
       inside the one it lands in.

       That is not style. `tests/test_shader_strings.py` reads a GLSL template
       literal as "everything between the line that opens one and the line that
       closes it", and a backtick inside that run is the bug it exists to catch:
       one written in a comment ends the string, the GLSL after it is parsed as
       JavaScript, and since the four web modules share one script scope the
       whole app dies with the loading screen showing forever. A nested template
       is indistinguishable from that bug to any textual reader — so the shader
       source is assembled by concatenating named pieces, and every template
       here opens and closes on its own terms. */
    const V_NORMAL_CLUSTER = `
            mat3 im = mat3(instanceMatrix);
            vec3 sn = objectNormal / vec3(dot(im[0], im[0]), dot(im[1], im[1]), dot(im[2], im[2]));
            vec3 transformedNormal = normalMatrix * spin(im * sn, u_nd[int(aI.x)].x, u_t);`;

    //: the conduit's frame is built HERE and left in globals, because three
    //: runs defaultnormal_vertex BEFORE begin_vertex (checked against the
    //: vendored r185) and both chunks need the same axis
    const V_NORMAL_LINK = `
            linkFrame();
            vec3 transformedNormal = normalMatrix *
              (gSx * objectNormal.x + gAx * objectNormal.y + gSz * objectNormal.z);`;

    const V_PLACE_CLUSTER = `
            vec3 lp = (instanceMatrix * vec4(position, 1.0)).xyz;
            int ni = int(aI.x);
            vec4 nd = u_nd[ni];
            vPal = u_pal[ni]; vPal2 = u_pal[ni];
            vT = clamp(gradT(lp / max(nd.w, 1e-4), u_axis[ni], nd.y, nd.z) + aI.y, 0.0, 1.0);
            vAng = atan(lp.z, lp.x);
            //: the spare slot, spent: how far this part is pulled to WHITE.
            //: A junction's hot core and the cluster's own centre are white in
            //: every reference cage whatever hue the cage wears, and the
            //: chord's highlight role cannot say that — it is gold on a violet
            //: cluster and green on a cyan one.
            vLay = aI.w;
            vHot = aI.z;
            vec3 transformed = u_np[ni] + spin(lp, nd.x, u_t);`;

    const V_PLACE_LINK = o => `
            int ia = int(aI.x), ib = int(aI.y);
            vPal = u_pal[ia]; vPal2 = u_pal[ib];
            vT = position.y + 0.5;
            vAng = atan(position.z, position.x);
            vLay = aI.w;
            vHot = ${F(o.hot)};
            vec3 transformed = gA + gAx * ((position.y + 0.5) * gSpan)
                             + (gSx * position.x + gSz * position.z) * aI.z;`;

    //: an endpoint piece wears the chord of the cluster it lands ON, not a
    //: blend of both: it is on that hull, not between them. A torus lies in
    //: its own XY plane with the hole along Z, so x maps to the side, y to the
    //: other side and z to the conduit's axis.
    const V_PLACE_LINK_END = o => `
            int ia = int(aI.x), ib = int(aI.y);
            vPal = u_pal[ia]; vPal2 = u_pal[ib];
            vT = aI.w;
            vAng = atan(position.z, position.x);
            vLay = 0.0;
            vHot = ${F(o.hot)};
            vec3 transformed = mix(gA, gB, step(0.5, aI.w))
                             + gAx * (mix(1.0, -1.0, step(0.5, aI.w)) * ${F(o.endOff)} * aI.z)
                             + (gSx * position.x + gSz * position.y) * aI.z
                             + gAx * position.z * aI.z;`;

    const V_PROJECT = `
            vec4 mvPosition = modelViewMatrix * vec4(transformed, 1.0);
            gl_Position = projectionMatrix * mvPosition;
            /* depth haze, exponential: nothing in the field is closer than
               about 15 units, and starting it at 7 was a global half-dimmer
               wearing a depth cue's clothes. 16/0.042 and not 15/0.075 — the
               box is deep now (it is where the background network comes from)
               and at the old rate a cage at 22 units was a dark lump rather
               than a dim cluster. In cluster-render-field.png the far cages
               are about half the brightness of the near ones and still
               obviously coloured. */
            vFar = exp(-max(0.0, -mvPosition.z - 16.0) * 0.042);`;

    //: a conduit runs between two clusters and carries BOTH their chords, so a
    //: cyan cluster joined to a magenta one is joined by something that is cyan
    //: at one end and magenta at the other. This is the brief's "the connection
    //: inherits colour information from the clusters it connects".
    const CHORD_LINK = `mix(chord(vPal, mix(0.12, 0.84, vT), vHot),
                            chord(vPal2, mix(0.84, 0.12, vT), vHot),
                            smoothstep(0.12, 0.88, vT))`;
    const CHORD_CLUSTER = 'mix(chord(vPal, vT, vHot * (0.30 + 0.70 * fres)), u_white, vLay)';

    const F_SHADE = o => `
          #include <emissivemap_fragment>
          vec3 vd = normalize(vViewPosition);
          float fres = clamp(1.0 - abs(dot(normalize(normal), vd)), 0.0, 1.0);
          /* THE COLOUR VARIES ACROSS THE GEOMETRY. This is the line the whole
             rewrite exists for: vT is a position-derived walk through the
             cluster's chord, so one tube runs cyan into violet into magenta
             along its own length and one junction is a different colour on its
             lit side than on its shadowed one. */
          vec3 ch = ${o.link ? CHORD_LINK : CHORD_CLUSTER};
          /* DEEPEN AND SATURATE BEFORE LIGHTING IT.
             This palette's accents are PALE by design — they clear a contrast
             floor as TEXT (#7dcfff, #9d7bff) — and a pale albedo under a key,
             a fill and a rim is white. The first lit render came out uniformly
             pink-white for exactly that reason, on a field that is meant to be
             violet. pow() darkens without desaturating (it pulls the channels
             apart rather than scaling them together) and the mix away from
             luminance pushes the separation further. The raw-shader passes in
             this scene have carried the same pow() for rounds; this is the
             same correction where the light is. */
          ch = mix(vec3(dot(ch, vec3(0.30, 0.59, 0.11))), ch, 1.90);
          ch = clamp(ch, 0.0, 1.0);
          ch = mix(u_bg, ch, vFar);
          ch = calm(ch, u_bg, u_calm + ${F(o.calm)});
          diffuseColor.rgb *= pow(max(ch, vec3(0.0)), vec3(2.5))
                            * ${F(o.tint == null ? 1 : o.tint)};
          /* A GLASS SHELL IS A RIM, AND A RIM IS A BAND — not a ramp. The
             junctions used to fade pow(fres, 1.7) from the middle out, which
             is a soft bubble; in both references a junction is a clear sphere
             with a HARD bright ring at its silhouette that you read the pink
             core THROUGH. So the alpha is a narrow smoothstep with a low floor:
             the floor is what you see the core through, the band is the ring. */
          diffuseColor.a *= ${F(o.alpha)}
            * ${o.fresA ? '(0.10 + 1.30 * smoothstep(0.55, 0.96, fres))' : '1.0'} * vFar;
          /* ...and a TUBE is the mirror image of that, which is why fresE is a
             mode and not a flag. A cylinder's specular is a narrow line down
             the part that FACES you and its silhouette goes dark — which is
             exactly what the reference's tubes do and the opposite of a rim
             glow. Running the glass term on them is what made every strut a
             flat pale band with bright edges. */
          totalEmissiveRadiance = pow(max(ch, vec3(0.0)), vec3(2.05)) * ${F(o.emis)}
            * ${{1: '(0.25 + 0.95 * pow(fres, 2.0))',
                 2: '(0.05 + 2.30 * pow(1.0 - fres, 9.0))',
                 3: '(0.06 + 2.40 * smoothstep(0.55, 0.96, fres))'}[o.fresE] || '1.0'}
            * (0.82 + 0.30 * u_e) * (1.0 + u_shock * 0.8) * vFar * u_dens;
          ${o.over || ''}`;

    //: the varyings the two stages must agree about, written once so they
    //: cannot drift — a varying declared in one stage and not the other is a
    //: link error with no line number worth reading
    const VARYINGS = `
          varying vec4 vPal; varying vec4 vPal2;
          varying float vT; varying float vHot; varying float vFar; varying float vAng;
          varying float vLay;`;
    const F_UNIFORMS = `
          uniform vec3 u_bg; uniform float u_calm, u_dens, u_e, u_t, u_shock;`;
    const V_PRELUDE = o => N_UNI + VARYINGS + SPIN + SF_GRAD + (o.link ? LINK_FRAME : '');
    const F_PRELUDE = VARYINGS + F_UNIFORMS + SF_ROLE + SF_CHORD + SF_CALM;

    /* ONE MATERIAL FACTORY. Every solid in the scene is a MeshPhysicalMaterial
       with the same injection and a different set of numbers, so "a junction is
       glass and a frame tube is not" is a config line rather than a shader.

       customProgramCacheKey is REQUIRED, not hygiene: three caches compiled
       programs by material type plus that key, so without it the first variant
       compiled would be handed to every other one and the whole cluster would
       draw with the junction's shader. */
    const solidMat = o => {
      const m = new TH.MeshPhysicalMaterial({
        color: 0xffffff,
        roughness: o.rough, metalness: o.metal,
        clearcoat: o.cc || 0, clearcoatRoughness: 0.16,
        iridescence: o.irid || 0, iridescenceIOR: 1.55,
        envMapIntensity: o.env == null ? 1.1 : o.env,
        emissive: 0xffffff, emissiveIntensity: 1,
        transparent: !!o.glass,
        // A GLASS SHELL MUST NOT WRITE DEPTH and everything else MUST. That
        // one line is most of the difference between this scene and the smear
        // it replaced: with every pass depth-write-off and additive, nothing
        // occludes anything and forty translucent objects sum into one cloud.
        depthWrite: !o.glass, depthTest: true,
        side: o.glass ? TH.DoubleSide : TH.FrontSide,
        /* ...and these are the ONLY materials in the file that do. Every
           other scene writes final display values out of a raw shader and must
           not be touched; these are lit, they routinely exceed 1.0, and
           without the curve every one of them clips to white — which is what
           the first render of this pass did, uniformly, to a field that is
           meant to be violet. */
        toneMapped: true,
      });
      m.customProgramCacheKey = () => 'archeus-cluster-' + o.key;
      m.onBeforeCompile = sh => {
        for (const k of ['u_t', 'u_np', 'u_axis', 'u_pal', 'u_nd', 'u_e', 'u_dens',
                         'u_calm', 'u_bg', 'u_acc', 'u_acc2', 'u_err', 'u_warn',
                         'u_ok', 'u_white', 'u_shock', 'u_pulse']) sh.uniforms[k] = u[k];
        const place = o.link ? (o.ends ? V_PLACE_LINK_END(o) : V_PLACE_LINK(o))
                             : V_PLACE_CLUSTER;
        // the newline is load-bearing: three's own shader starts with
        // '#define STANDARD', a preprocessor directive has to begin a LINE,
        // and gluing it to the end of the prelude is an 'invalid character'
        // error a hundred lines away from anything this file wrote
        sh.vertexShader = (V_PRELUDE(o) + '\n' + sh.vertexShader)
          .replace('#include <defaultnormal_vertex>',
                   o.link ? V_NORMAL_LINK : V_NORMAL_CLUSTER)
          .replace('#include <begin_vertex>', place)
          .replace('#include <project_vertex>', V_PROJECT);
        sh.fragmentShader = (F_PRELUDE + '\n' + sh.fragmentShader)
          .replace('#include <emissivemap_fragment>', F_SHADE(o));
      };
      return m;
    };

    /* ONE InstancedMesh out of a template geometry and a list of rows. The
       geometry is cloned per call because the per-instance attributes live on
       it — two meshes sharing one geometry would share one instance list, and
       the second would draw the first's placements. */
    const SOLIDS = new TH.Group();
    SOLIDS.frustumCulled = false;
    const mkInst = (tmpl, mat, rows, order) => {
      if (!rows.length) return null;
      const geo = tmpl.clone();
      const m = new TH.InstancedMesh(geo, mat, rows.length);
      const A = new Float32Array(rows.length * 4);
      for (let k = 0; k < rows.length; k++) {
        m.setMatrixAt(k, rows[k].m);
        A.set(rows[k].i, k * 4);
      }
      m.instanceMatrix.needsUpdate = true;
      geo.setAttribute('aI', new TH.InstancedBufferAttribute(A, 4));
      m.frustumCulled = false;        // every position comes from u_np, so the
      m.renderOrder = order;          // bounding sphere describes nothing
      SOLIDS.add(m);
      return m;
    };

    //: place a part inside its cluster: local offset, orientation, scale
    const _q = new TH.Quaternion(), _up = new TH.Vector3(0, 1, 0),
          _d = new TH.Vector3(), _p = new TH.Vector3(), _s = new TH.Vector3();
    const at = (pos, quat, scale) => new TH.Matrix4().compose(pos, quat, scale);
    const ball = (v, r) => at(_p.set(v[0], v[1], v[2]), _q.identity(), _s.set(r, r, r));
    const tube = (a, b, half) => {
      _d.set(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
      const L = _d.length() || 1e-4;
      return at(_p.set((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2),
                _q.setFromUnitVectors(_up, _d.divideScalar(L)),
                _s.set(half, L, half));
    };

    /* the rows. `i` is the one per-instance attribute: for a cluster part it is
       (node, gradient bias, highlight gate, spare); for a conduit part it is
       (node A, node B, radius, which end). Two meanings for one attribute is
       normally a smell — here it is what keeps both families on one factory,
       and the two are never mixed in a single mesh. */
    const rFrame = [], rCore = [], rGlass = [];
    for (let i = 0; i < N; i++) {
      const n = nodes[i];
      if (n.lod > 0) {
        // THE FRAME. Thirty tubes along the icosahedron's edges with a big
        // glass junction at each of its twelve corners — the feature that
        // makes a cluster read as a built object rather than as a ball of
        // wire, and the one the .glb does not contain (see cluster_spec.py).
        for (const q of SHELL[0]) {
          rFrame.push({m: tube([q[0] * n.r, q[1] * n.r, q[2] * n.r],
                                [q[3] * n.r, q[4] * n.r, q[5] * n.r], CL.FRAME_HALF * n.r),
                       i: [i, 0.0, 0.30, 0]});
        }
        // the twenty spokes, from just outside the core to just inside the
        // hull. They stop short at BOTH ends: twenty rods meeting at a point
        // is a star brighter than anything the scene means, and a rod that
        // pierces its own hull has a flat end hanging outside it.
        for (const d of SPOKES) {
          rFrame.push({m: tube([d[0] * n.r * CL.SPOKE_IN, d[1] * n.r * CL.SPOKE_IN,
                                d[2] * n.r * CL.SPOKE_IN],
                               [d[0] * n.r * CL.SPOKE_OUT, d[1] * n.r * CL.SPOKE_OUT,
                                d[2] * n.r * CL.SPOKE_OUT], CL.SPOKE_HALF * n.r),
                       i: [i, 0.22, 0.18, 0]});
        }
        for (const v of V_FRAME) {
          const p = [v[0] * n.r, v[1] * n.r, v[2] * n.r];
          // A JUNCTION IS FOUR NESTED SPHERES, off the model's own part list
          // (Hub_HotCore / Hub_EnergyCore / Hub_GlassShell). The hot core and
          // the energy shell are opaque and go in the core mesh; the glass
          // housing is transparent and goes in the glass mesh, which draws
          // after so it blends over what it contains.
          // ...and the hot core is WHITE, from the fourth slot, not from the
          // chord's highlight role: that role is gold on a violet cluster and
          // green on a cyan one, and in both renders every junction core is
          // the same white whatever hue the cage around it wears.
          rCore.push({m: ball(p, CL.FRAME_BEAD_HOT * n.r), i: [i, 0.72, 0.30, 0.80]});
          rCore.push({m: ball(p, CL.FRAME_BEAD_ENERGY * n.r), i: [i, 0.52, 0.10, 0.14]});
          rGlass.push({m: ball(p, CL.FRAME_BEAD_R * n.r), i: [i, 0.08, 0.22, 0]});
        }
      }
      /* THE LIT CENTRE — a white core with a gold seed inside it, inside its
         own glass. The single thing the model's parts list says that no still
         image did, and the reason every version built before it was read had a
         hollow interior no amount of shell tuning could fix. The brief calls
         for a plasma: white at the middle, then magenta, then violet, then a
         cyan outer glow, which is exactly a chord walked from its highlight
         end — so the seed sits at the hot end of the gradient and the shell at
         the cool end. */
      rCore.push({m: ball([0, 0, 0], CL.CORE_ENERGY_R * n.r), i: [i, 0.50, 0.10, 0.10]});
      rCore.push({m: ball([0, 0, 0], CL.CORE_R * n.r), i: [i, 0.62, 0.35, 0.78]});
      rCore.push({m: ball([0, 0, 0], CL.SEED_R * n.r), i: [i, 0.86, 0.85, 0]});
      if (n.lod > 0) rGlass.push({m: ball([0, 0, 0], CL.CORE_SHELL_R * n.r), i: [i, 0.02, 0.35, 0]});
    }

    //: 12 segments and one height segment, open-ended: a frame tube is capped
    //: by the junction at each end, so its own caps are geometry nobody sees.
    const TUBE_G = new TH.CylinderGeometry(1, 1, 1, 12, 1, true);
    //: detail 2 for a junction (162 vertices) — it is the biggest thing on the
    //: cluster and a faceted silhouette on it reads as a bug, not as a style.
    const BALL_G = new TH.IcosahedronGeometry(1, 2);

    mkInst(TUBE_G, solidMat({
      /* exponent 7 on the specular line and env down to 0.6. A cylinder's
         normal turns as the SINE of the angle across it, so pow(1 - fres, 3)
         is still at 65% of full brightness half way to the silhouette — a
         broad pale band, which is what our tubes were. The reference's tube is
         a mid-dark saturated body with a thin hot line down it; 7 is where the
         same term is 32% at half width. The environment came down for the same
         reason: at 1.1 a metal 0.78 tube reflects most of its own brightness
         and the albedo curve underneath it stops mattering. */
      key: 'frame', rough: 0.22, metal: 0.78, cc: 0.9, irid: 0.35, env: 0.6,
      emis: 0.42, fresE: 2, fresA: 0, alpha: 1.0, calm: 0.34, hot: 0,
    }), rFrame, 0);

    mkInst(BALL_G, solidMat({
      key: 'core', rough: 0.10, metal: 0.05, cc: 0.4, irid: 0.2,
      // the cores are the only thing in the scene meant to clear the bloom
      // threshold on their own — 0.55, so only a near-white surface does
      emis: 0.95, fresE: 0, fresA: 0, alpha: 1.0, calm: 0.50, hot: 0, env: 0.5,
    }), rCore, 1);

    mkInst(BALL_G, solidMat({
      key: 'glass', glass: 1, rough: 0.08, metal: 0.15, cc: 1.0, irid: 0.65,
      // A GLASS SHELL IS ITS RIM. Alpha driven by the Fresnel term is what
      // makes the middle see-through and the edge solid, which is how a
      // transparent sphere is legible at all — a flat 40% sphere is a washer.
      // It is also why no backdrop-filter is needed anywhere near this app.
      // pow 1.25 and not 1.7 on the alpha, emissive up from 0.22, env up from
      // 1.6: in both references a junction is a CLEAR SPHERE with a hard bright
      // rim and a pink core visible inside it. At the old numbers the shell was
      // a grey ghost the core's bloom ate, and a junction read as a halo.
      emis: 0.62, fresE: 3, fresA: 1, alpha: 0.92, calm: 0.44, hot: 0, env: 2.2,
    }), rGlass, 2);

    /* ── the conduit ──────────────────────────────────────────────────────
       WHICH clusters are joined: the three nearest neighbours BY DISTANCE,
       taken once at rest and then held. The pairs used to be index offsets —
       i+1, i+2, i+3 and an i+8 chord — and the indices run along a lattice, so
       after the physics has moved anything "i+8" is an arbitrary partner on the
       far side of the box: a fan of long chords crossing the middle of the
       frame, which is what the field looked like and nothing like a lattice.
       Recomputing them every frame is the other wrong answer — the drift is
       supposed to stretch the structure, not rewire it. */
    const PAIRS = [];
    const seenPair = new Set();
    for (let i = 0; i < N; i++) {
      const near = [];
      for (let j = 0; j < N; j++) {
        if (j === i) continue;
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const dz = nodes[i].z - nodes[j].z;
        near.push([dx * dx + dy * dy + dz * dz, j]);
      }
      near.sort((a, b) => a[0] - b[0]);
      for (let k = 0; k < 4 && k < near.length; k++) {
        const j = near[k][1];
        const key2 = i < j ? i + ':' + j : j + ':' + i;
        if (seenPair.has(key2)) continue;
        seenPair.add(key2);
        PAIRS.push([i, j]);
      }
    }

    /* WHAT is drawn, and this is the second half of what the model settled.
       A link is a COAXIAL TRIPLE, not a tube: a dark housing that gives it a
       silhouette, a translucent glass layer you see threads through, and a hot
       filament at the axis — plus one luminous rail riding the OUTSIDE of the
       housing, a gold collar where it meets each hull, and a glass hub at each
       end. Every version before the model was read had ONE shell and the
       argument was only ever about its falloff: core-led it reads as a hairline
       with a glow, wall-led as an empty pipe. Neither is what the object is,
       and no amount of tuning one number was going to find three.

       Rh is the HUB radius, which is what the model's fractions are against —
       the hub's glass shell is 2.00 Rh, so a hub sphere is exactly Rh across
       its radius and the conduit inside it is a little over half that. */
    const rCond = [], rCollar = [], rHub = [];
    const I4 = new TH.Matrix4();
    for (const [i, j] of PAIRS) {
      // the conduit is sized by the SMALLER of the two clusters it joins: a
      // leaf tethered to a hub gets a conduit its own leaf can carry, which is
      // what stops one thick pipe from dominating a small cluster entirely.
      const Rh = 0.105 + 0.060 * Math.min(nodes[i].r, nodes[j].r);
      const lay = [CL.CONDUIT_HOUSING, CL.CONDUIT_GLASS, CL.CONDUIT_CORE];
      for (let k = 0; k < 3; k++) rCond.push({m: I4, i: [i, j, lay[k] * 0.5 * Rh, k]});
      for (let e = 0; e < 2; e++) {
        rCollar.push({m: I4, i: [i, j, Rh, e]});
        rHub.push({m: I4, i: [i, j, Rh, e]});
      }
    }

    //: a conduit's own placement is entirely in the shader (both its ends are
    //: moving), so instanceMatrix is the identity for every one of these and
    //: the cylinder is a unit one along Y.
    const COND_G = new TH.CylinderGeometry(1, 1, 1, 14, 1, true);
    const COLLAR_G = new TH.TorusGeometry(CL.COLLAR_D * 0.5, CL.COLLAR_THICK * 0.5, 8, 20);

    mkInst(COND_G, solidMat({
      /* env 0.35 and metal 0.25, down from 1.3 and 0.55 — THE GREY WAS A
         REFLECTION. The housing's own albedo is 30% chord over 70% background,
         i.e. nearly black, and it still rendered as a pale grey pipe: a metal
         0.55 clearcoat 0.9 surface under a 1.3 environment reflects the map,
         and a reflection does not go through the albedo the over-block sets.
         Tuning the alpha and the emissive (which is where this was looked for
         twice) could not have reached it. */
      /* NO IRIDESCENCE ON THE CONDUIT. A thin-film term replaces F0 with a
         broad pastel sheen over the WHOLE surface, and six stacked translucent
         faces (front and back of three coaxial layers) each add one — which is
         a warm white pipe whatever the albedo underneath it says. It is right
         on a junction, which is one convex sphere and wants the oil-on-water
         edge; it is wrong here. */
      //: ...and the environment goes with it, for the third time in this
      //: material. A rough 0.16 surface mirrors the PMREM map, the map is a
      //: pale sky, and an indirect specular is not multiplied by anything the
      //: over-block writes — so the NEAR conduits stayed pale while the far
      //: ones (which vFar mixes toward the background) were already right.
      key: 'conduit', link: 1, glass: 1, rough: 0.34, metal: 0.25,
      cc: 0.20, irid: 0.0, emis: 0.55, fresE: 1, fresA: 0, alpha: 1.0,
      calm: 0.42, hot: 0.0, env: 0.10,
      /* THE THREE LAYERS, told apart by the instance's own w. One mesh and one
         draw call for all three: they differ in radius, which is placement, and
         in how they shade, which is four lines. Three meshes would be three
         chances for the layers to disagree about where the axis is. */
      over: `
        float housing = 1.0 - step(0.5, vLay);
        float glass = step(0.5, vLay) * (1.0 - step(1.5, vLay));
        float core = step(1.5, vLay);
        /* the rail: ONE bright line on the outside of the housing, off-axis.
           Symmetry is what made every earlier conduit read as a smear — a real
           cylinder lit from somewhere has a top, and one off-centre highlight
           is the whole cue. Rail_Node beads ride it, spaced along vT. */
        float rail = exp(-pow((vAng - 2.05) / 0.20, 2.0)) * housing;
        float railn = rail * pow(max(0.0, 1.0 - abs(fract(vT * 7.0) - 0.5) * 9.0), 3.0);
        /* THE THREADS INSIDE THE GLASS — Internal_Filament (gold) and
           Internal_CrossLink (cyan) in the model's part list, and the thing
           that makes a conduit read as something with an INSIDE rather than as
           a lit pipe. In the reference you can see them spiralling behind the
           wall, which is the whole reason the middle layer is translucent.

           They cost no geometry: a helix on a cylinder is a straight line in
           (angle, length), so it is one fract() on two numbers the fragment
           already has. Two gold running one way and two cyan the other, so
           they cross — a single family of parallel threads reads as a texture,
           and it is the crossing that reads as a network. */
        float lam = 1.0 - step(0.5, abs(vLay - 1.0));
        float helA = 1.0 - min(fract(vAng * 0.3183099 - vT * 3.5), 1.0 - fract(vAng * 0.3183099 - vT * 3.5)) * 2.0;
        float helB = 1.0 - min(fract(vAng * 0.3183099 + vT * 4.5 + 0.37), 1.0 - fract(vAng * 0.3183099 + vT * 4.5 + 0.37)) * 2.0;
        float gold = pow(max(0.0, helA), 42.0) * lam;
        float cross = pow(max(0.0, helB), 34.0) * lam;
        // ...and beads riding the gold thread, the model's Energy_Particle
        float bead = gold * pow(max(0.0, 1.0 - abs(fract(vT * 9.0 - u_t * 0.10) - 0.5) * 11.0), 3.0);
        /* DATA TRAVELLING — always running, because this is the graph showing
           that the links carry something, but faster and denser when the
           workspace is busy. Slow: at 0.16 a packet crossed a link in about six
           seconds and read as a strobe rather than as something moving along a
           wire, and the whole point is that you can watch one travel. */
        float sp = 0.045 + 0.11 * u_e;
        float ph = fract(u_t * sp + float(int(vLay)) * 0.31);
        float pk = pow(max(0.0, 1.0 - abs(vT - ph) * 22.0), 2.0) * core;
        //: and the ends TAPER. The endpoint push is clamped at a fraction of
        //: the gap, so where a big hull exceeds that clamp the tube stops short
        //: of its own surface — and a flat end hanging in mid-air is exactly
        //: what read as "the collar is a hard cut".
        float ends = smoothstep(0.0, 0.05, vT) * (1.0 - smoothstep(0.95, 1.0, vT));
        /* THE GLASS IS THE CONDUIT'S OWN COLOUR, not the clusters'.
           The model names it Deep Blue Glass and the render agrees: the tube
           between two violet clusters is BLUE, and only the filament at its
           axis and the rail on its housing carry the hues of the things it
           joins. That is not a contradiction of "a connection inherits from
           the clusters it connects" — it is where the inheritance lives. A
           conduit whose every layer was the endpoint chord had no identity of
           its own and read as a stretched piece of cluster. */
        /* ...and it is BRIGHT. In connection-render.png the conduit is the
           brightest object in the frame — electric blue, brighter than either
           cage it joins — and ours read grey: the glass was only 70% of the way
           to the accent, carried a 0.30 emissive against the core's 2.10, and
           had a soft alpha ramp instead of a wall. All three are the same
           mistake, which is treating the middle layer as a veil over the core
           rather than as the object you are looking at. */
        //: ...and the blue is not the accent RAW. u_acc clears a contrast floor
        //: as text and is a pale cyan; the model names this layer Deep Blue
        //: Glass and the render is an electric blue, which is the accent a
        //: third of the way to the violet one.
        ch = mix(ch, mix(mix(u_acc, u_acc2, 0.34), ch, 0.14), glass * 0.92);
        ch = mix(mix(u_bg, ch, 0.30), ch, glass * 0.90 + core + rail);
        /* 2.6, the SAME curve every other solid in this scene gets. F_SHADE
           applies pow(ch, 2.5) to diffuseColor and this block ASSIGNS over it,
           so the conduit was the one lit surface running a 1.6 albedo — a
           full stop paler than the cages around it, under the same key. That
           is the whole of "the conduit reads grey next to the reference's
           bright blue": it was not grey, it was washed out. */
        diffuseColor.rgb = pow(max(ch, vec3(0.0)), vec3(2.6));
        diffuseColor.a = (housing * (0.06 + 0.62 * pow(fres, 2.2))
                        + glass * (0.20 + 0.95 * pow(fres, 1.1))
                        + core * 0.98 + rail * 0.95
                        + gold * 0.80 + cross * 0.65) * ends * vFar;
        // the threads are the one part of a conduit that is NOT the two
        // clusters' chord: gold and cyan whatever they join, exactly as the
        // collar is gold. It is what stops two conduits between differently
        // coloured clusters being the same picture in two inks.
        vec3 tc = mix(ch, u_warn, clamp(gold * 0.9 + bead * 0.6, 0.0, 1.0));
        tc = mix(tc, u_acc, clamp(cross * 0.85, 0.0, 1.0));
        /* THE AXIS FILAMENT IS NOT A WHITE ROD. At core 1.55 with a 0.45 pull
           to white it out-blooms the layer around it, and since bloom spreads
           the result is a white pipe with a blue edge — which is what the
           conduit read as through three rounds of tuning the GLASS. In
           connection-render.png the middle of a conduit is BLUE with threads
           and beads visible in it; the only white is the beads. */
        /* ...and the EMISSIVE takes the same curve, for the same reason and
           with more at stake. F_SHADE writes pow(ch, 2.05) and this block
           assigns over it, so the conduit emitted a PALE blue — and a pale
           blue past the bloom threshold spreads as WHITE, which is why three
           rounds of dimming and brightening this layer only ever moved it
           between grey and a white beam. Bloom does not desaturate a colour
           that was saturated going in. */
        totalEmissiveRadiance = pow(max(mix(tc, vec3(1.0),
              core * 0.16 + railn * 0.8 + pk * 0.7 + bead * 0.7), vec3(0.0)), vec3(2.05))
          * (housing * 0.05 + glass * 0.72 + core * 1.15 + rail * 1.30 + railn * 2.1
             + pk * 2.4 + gold * 1.15 + cross * 0.85 + bead * 2.2)
          * (0.82 + 0.30 * u_e) * ends * vFar * u_dens;`,
    }), rCond, 3);

    mkInst(COLLAR_G, solidMat({
      key: 'collar', link: 1, ends: 1, endOff: 0.95, rough: 0.22, metal: 0.85,
      // the collar is GOLD whatever the two clusters are wearing — the one
      // part of the conduit that is not the chord, which is what stops a gold
      // cluster and a violet one being the same picture in two inks
      emis: 0.55, fresE: 0, fresA: 0, alpha: 1.0, calm: 0.46, hot: 0, env: 1.4,
      over: `
        /* A COLLAR IS METAL, NOT A LAMP. At 0.65 emissive a gold torus clears
           the bloom threshold, and where several conduits converge on one small
           hull their collars stack into a cream haze that reads as a pale pipe
           — which is what the last three rounds of tuning the conduit's GLASS
           were chasing. In connection-render.png the ring at the hub is a dark
           metallic band with a gold edge, and the light in that area comes from
           the hub's plasma behind it. */
        vec3 gold = calm(mix(u_bg, u_warn, vFar), u_bg, u_calm + 0.46);
        diffuseColor.rgb = pow(max(gold, vec3(0.0)), vec3(1.7)) * 0.55;
        totalEmissiveRadiance = gold * 0.20 * (0.82 + 0.30 * u_e) * vFar * u_dens;`,
    }), rCollar, 3);

    mkInst(BALL_G, solidMat({
      key: 'hub', link: 1, ends: 1, glass: 1, rough: 0.07, metal: 0.2,
      cc: 1.0, irid: 0.7, emis: 0.30, fresE: 1, fresA: 1, alpha: 0.95,
      calm: 0.46, hot: 0.35, env: 1.7,
    }), rHub, 4);

    S.add(SOLIDS);

    /* ── the haze ─────────────────────────────────────────────────────────
       Everything the solids are not: the 480-rod hairline shell, the second
       480-rod cage inside it, the hull's tinted faces, the 162 small beads on
       the surface and the interior population. These stay merged-buffer raw
       ShaderMaterials — they are a quarter of a million hairline vertices with
       no specular anywhere on them, and the brief's own instruction is not to
       make the shader unnecessarily expensive.

       WHAT CHANGED IS THAT THEY ARE NOW BEHIND SOMETHING. Every pass here is
       depth-TESTED (and still never depth-WRITES), so the frame, the junctions
       and the centre occlude the mesh that used to swallow them. That is the
       whole difference between a cluster and a cloud.

       A GLSL prelude they all share: the same chord, the same gradient, read
       out of the same uniform arrays as the solids. One implementation of
       "what colour is this cluster here", not six. */
    const HAZE_V = `
      uniform float u_t; uniform vec3 u_np[${N}]; uniform vec3 u_axis[${N}];
      uniform vec4 u_pal[${N}]; uniform vec4 u_nd[${N}];`;

    /* 1 ── the shell and the inner web, as one merged ribbon buffer.
       A STRUT IS A TUBE, for the reason a link is: WebGL ignores lineWidth, so
       LineSegments can only ever draw a one-pixel hairline and there is not one
       hairline anywhere in the reference. Four vertices and two triangles per
       edge, expanded across the rod's own width in the vertex shader, still one
       draw call.

       The shell is 0.013 R and not the model's 0.0555. Four hundred and eighty
       rods at the model's thickness cover more than the whole surface of the
       hull — the arithmetic is in cluster_spec.py — and what that draws is the
       featureless blue sphere this scene shipped as. In the renders the fine
       mesh is a web you see the interior THROUGH. */
    const ep = [], eo = [], et = [], ew = [], ea = [], en = [], eidx = [];
    let erod = 0;
    const rod = (n, i, A, B, half, alpha) => {
      const base = erod * 4;
      for (const [t, side] of [[0, -1], [0, 1], [1, -1], [1, 1]]) {
        const me = t ? B : A, other = t ? A : B;
        ep.push(me[0], me[1], me[2]);
        eo.push(other[0], other[1], other[2]);
        et.push(t); ew.push(side); ea.push(alpha);
        en.push(i, half);
      }
      eidx.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
      erod++;
    };
    for (let i = 0; i < N; i++) {
      const n = nodes[i];
      const shell = SHELL[n.lod];
      //: per-rod alpha by HOW MANY there are: a 480-rod shell and a 30-rod one
      //: cannot share a number, and it is a property of the shell rather than
      //: of the shader
      const dens = CL.ROD_ALPHA_BY_EDGES[shell.length] || 0.3;
      for (const q of shell) {
        rod(n, i, [q[0] * n.r, q[1] * n.r, q[2] * n.r],
                  [q[3] * n.r, q[4] * n.r, q[5] * n.r], CL.SHELL_ROD_HALF * n.r, dens);
      }
      /* THE INNER WEB — the model's `Inner filament`, 257 of them at 0.53 R,
         each 0.16 R long. Those numbers name a shape rather than a scatter: a
         480-edge cage at 0.53 R has an edge length of 0.27 x 0.53 = 0.14 R,
         which is the measurement. So the interior is not a haze, it is a SECOND
         CAGE inside the first — nodes made of nodes, which is the argument the
         brand study makes about the memory graph and arrives at from the other
         direction. Only where it can be resolved: on a speck it is 480 more
         rods inside four pixels. */
      if (n.lod === 2) {
        const w = CL.WEB_R;
        for (const q of SHELL[2]) {
          rod(n, i, [q[0] * n.r * w, q[1] * n.r * w, q[2] * n.r * w],
                    [q[3] * n.r * w, q[4] * n.r * w, q[5] * n.r * w],
                    CL.WEB_ROD_HALF * n.r, 0.55);
        }
      }
    }
    const gEdges = new TH.BufferGeometry();
    gEdges.setAttribute('position', new TH.Float32BufferAttribute(ep, 3));
    gEdges.setAttribute('eo', new TH.Float32BufferAttribute(eo, 3));
    gEdges.setAttribute('et', new TH.Float32BufferAttribute(et, 1));
    gEdges.setAttribute('ew', new TH.Float32BufferAttribute(ew, 1));
    gEdges.setAttribute('ea', new TH.Float32BufferAttribute(ea, 1));
    gEdges.setAttribute('nd', new TH.Float32BufferAttribute(en, 2));
    gEdges.setIndex(eidx);
    const mEdges = new TH.Mesh(gEdges, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false, depthTest: true,
      side: TH.DoubleSide, blending: TH.AdditiveBlending,
      vertexShader: `
        attribute vec3 eo; attribute float et; attribute float ew;
        attribute float ea; attribute vec2 nd;
        varying vec4 vPal; varying float vT; varying float vD; varying float vF;
        varying float vX; varying float vA;
        ${HAZE_V}
        ${SPIN}
        ${SF_GRAD}
        void main(){
          int ni = int(nd.x);
          vec4 ndv = u_nd[ni];
          vPal = u_pal[ni]; vX = ew; vA = ea;
          /* THE ROD GRADIENTS ALONG ITS OWN LENGTH. gradT is evaluated at THIS
             end's local position, so the two ends of one rod get different
             values and the fragment interpolates between them — cyan into
             violet into magenta over a single strut, which is what the brief
             asks for and what a per-cage tone could never produce. */
          vT = clamp(gradT(position / max(ndv.w, 1e-4), u_axis[ni], ndv.y, ndv.z), 0.0, 1.0);
          vec3 org = u_np[ni];
          vec3 pa = org + spin(position, ndv.x, u_t);
          vec3 pb = org + spin(eo, ndv.x, u_t);
          vec4 mv = modelViewMatrix * vec4(pa, 1.0);
          vec3 bv = (modelViewMatrix * vec4(pb, 1.0)).xyz;
          // across the rod, camera-facing: perpendicular to the rod and to the
          // view axis. Width is in world units, so a distant rod is genuinely
          // thinner rather than a constant-width ribbon fighting every other
          // depth cue in the scene.
          vec3 side = normalize(cross(normalize(bv - mv.xyz), normalize(-mv.xyz)));
          mv.xyz += side * ew * nd.y;
          float dist = -mv.z;
          vD = clamp(1.0 - dist / 26.0, 0.0, 1.0);
          vF = exp(-max(0.0, dist - 16.0) * 0.042);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        ${SF_CALM}
        ${SF_ROLE}
        ${SF_CHORD}
        varying vec4 vPal; varying float vT; varying float vD; varying float vF;
        varying float vX; varying float vA;
        uniform vec3 u_bg; uniform float u_e, u_dens, u_calm, u_shock;
        void main(){
          float ax = abs(vX);
          // a hairline rod has room for exactly two terms: the body of the
          // material and the wall where it turns away. A core term at this
          // width IS the hairline the tube was built to replace, drawn inside
          // its own replacement.
          float body = pow(max(0.0, 1.0 - ax * ax), 1.3);
          float rim  = smoothstep(0.55, 0.92, ax) * (1.0 - smoothstep(0.92, 1.0, ax));
          vec3 col = chord(vPal, vT, 0.08 + 0.30 * rim);
          /* DEEPEN THE HUE BEFORE SUMMING IT. Every rod here is additively
             blended and a cage shows its far side through its near side, so two
             or three overlap on most pixels — and this palette's accents are
             pale by design, because they clear a contrast floor as TEXT. Two
             pale colours added are white, which is why a field of violet, gold
             and teal cages kept coming out white-blue whatever the alphas were.
             pow(c, 1.6) darkens without desaturating: it pulls the channels
             apart rather than scaling them together. */
          /* pow 2.4, not 1.6. Measured against the reference at cage scale:
             its MEDIAN pixel is (23, 27, 113) — near-black in red and green
             with the blue still up — and ours was (115, 117, 176), a grey
             lavender fog. Six hundred additive rods do not make a picture too
             bright so much as too DESATURATED: each sum pulls red and green up
             toward the blue, and the exponent is the only term that pulls the
             channels apart instead of scaling them together. */
          col = pow(max(col, vec3(0.0)), vec3(2.4));
          col += vec3(u_shock * 0.5);
          col = mix(u_bg, col, vF);          // depth, BEFORE calm() — never instead
          /* THE BODY IS THE HAZE AND THE RIM IS THE LINE, so the body is
             what has to go. Measured against the reference: the interior of a
             cage there means (42, 36, 106) with a p90 of (155, 129, 249) — a
             DARK navy volume with crisp bright things in it — and ours was
             (145, 122, 188) against a p90 of (194, 177, 221), which is a milky
             ball. Six hundred additive rods overlap three deep on most interior
             pixels, so the broad term is multiplied by the overlap and the thin
             one is not; cutting body to a third and rim by a half is what turns
             the sum back into a mesh you see the black through. */
          float a = (body * 0.11 + rim * 0.46) * vA
                  * (0.46 + 0.48 * vD) * vF * u_dens * (0.78 + 0.32 * u_e);
          gl_FragColor = vec4(calm(col, u_bg, u_calm + 0.30), a);
        }`,
    }));
    mEdges.frustumCulled = false;
    mEdges.renderOrder = 7;
    S.add(mEdges);

    /* 2 ── THE HULL IS A TRANSLUCENT SOLID, NOT A BARE WIREFRAME.
       In the reference every cage has visible TINTED FACES: a smoky volume
       filling the hull, dark through the middle, brightest where a facet turns
       edge-on. That is what gives a cluster mass, and it is also why the far
       side of a cage shows THROUGH the near side — the interior chords in the
       image are not extra struts, they are the back of the hull.

       It draws NORMAL-blended, not additive: the one pass whose job is to give
       the hull VOLUME must be able to DARKEN its own interior, and additive
       light cannot darken. It was additive for a while and that is exactly what
       was wrong with it. */
    const face = new TH.IcosahedronGeometry(1, 0);
    const gFaces = sMerge(TH, face, N, {nd: 1}, (i, o) => {
      o.s[0] = o.s[1] = o.s[2] = nodes[i].r;
      o.a.nd = [i];
    });
    face.dispose();
    const mFaces = new TH.Mesh(gFaces, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false, depthTest: true,
      side: TH.DoubleSide, blending: TH.NormalBlending,
      vertexShader: `
        attribute float nd;
        varying vec4 vPal; varying float vT; varying float vD; varying float vF;
        varying float vE;
        ${HAZE_V}
        ${SPIN}
        ${SF_GRAD}
        void main(){
          int ni = int(nd);
          vec4 ndv = u_nd[ni];
          vPal = u_pal[ni];
          vec3 lp = spin(position, ndv.x, u_t);
          vT = clamp(gradT(position / max(ndv.w, 1e-4), u_axis[ni], ndv.y, ndv.z), 0.0, 1.0);
          vec4 mv = modelViewMatrix * vec4(u_np[ni] + lp, 1.0);
          // The surface normal is the vertex direction — every vertex of a
          // subdivided icosahedron sits on its circumsphere, so normalize() of
          // the local offset IS the outward normal. Derived rather than read
          // off the geometry: whether three normalizes a polyhedron's normals
          // has moved between versions, and this cannot be wrong.
          vec3 nv = normalize(mat3(modelViewMatrix) * normalize(lp));
          vE = 1.0 - abs(dot(nv, normalize(-mv.xyz)));
          float dist = -mv.z;
          vD = clamp(1.0 - dist / 26.0, 0.0, 1.0);
          vF = exp(-max(0.0, dist - 16.0) * 0.042);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        ${SF_CALM}
        ${SF_ROLE}
        ${SF_CHORD}
        varying vec4 vPal; varying float vT; varying float vD; varying float vF;
        varying float vE;
        uniform vec3 u_bg; uniform float u_dens, u_calm, u_e;
        void main(){
          vec3 col = pow(max(chord(vPal, vT, 0.05), vec3(0.0)), vec3(2.3));
          col = mix(u_bg, col, vF);          // depth, BEFORE calm()
          // pow 3 and not 2: at 2 the interior still carries enough to fill the
          // hull with flat colour, which is a bubble rather than a cage.
          float a = (0.016 + 0.130 * pow(vE, 3.0)) * (0.45 + 0.55 * vD)
                  * vF * u_dens * (0.85 + 0.3 * u_e);
          gl_FragColor = vec4(calm(col, u_bg, u_calm + 0.26), a);
        }`,
    }));
    mFaces.frustumCulled = false;
    mFaces.renderOrder = 6;      // under the mesh and the beads, over the solids
    S.add(mFaces);

    /* 3 ── the 162 small beads on the hull.
       Only the shell's own nodes now: the twelve frame junctions became real
       glass spheres in the solid pass, which is where they belonged — at one
       alpha the 162 outnumbered the 12 thirteen to one and every cluster was a
       ball of white dots. What is left here is a TEXTURE on the surface, and it
       is deduplicated to the distinct corners because IcosahedronGeometry is a
       triangle soup: 240 positions for 42 corners, and drawing the soup stacks
       five or six additive sprites on each of them. */
    const jp = [], jn = [];
    for (let i = 0; i < N; i++) {
      const n = nodes[i];
      const V = n.lod === 2 ? V_SHELL : V_FRAME;
      for (const v of V) {
        jp.push(v[0] * n.r, v[1] * n.r, v[2] * n.r);
        jn.push(i, n.r);
      }
    }
    const gJoint = new TH.BufferGeometry();
    gJoint.setAttribute('position', new TH.Float32BufferAttribute(jp, 3));
    gJoint.setAttribute('nd', new TH.Float32BufferAttribute(jn, 2));
    const mJoint = new TH.Points(gJoint, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false, depthTest: true,
      blending: TH.AdditiveBlending,
      vertexShader: `
        attribute vec2 nd;
        varying vec4 vPal; varying float vT; varying float vD; varying float vF;
        varying float vR; varying float vJ;
        uniform vec2 u_res;
        ${HAZE_V}
        ${SPIN}
        ${SF_GRAD}
        void main(){
          int ni = int(nd.x);
          vec4 ndv = u_nd[ni];
          vPal = u_pal[ni]; vR = nd.y;
          vT = clamp(gradT(position / max(ndv.w, 1e-4), u_axis[ni], ndv.y, ndv.z), 0.0, 1.0);
          // stable per bead, hashed off its local position — the reference has
          // gold beads sitting on otherwise violet cages, as individual points
          // and not as a whole-cluster tint
          vJ = fract(sin(dot(position, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
          vec3 p = u_np[ni] + spin(position, ndv.x, u_t);
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          float dist = -mv.z;
          vD = clamp(1.0 - dist / 26.0, 0.0, 1.0);
          vF = exp(-max(0.0, dist - 16.0) * 0.042);
          gl_Position = projectionMatrix * mv;
          // size by mass AND size by depth AND defocus — three cues, and they
          // are not the same cue. In the reference the far clusters are not
          // merely small and dim, they are optically BLURRED; a real blur is a
          // readback this shell does not get to have (that is what tore the Qt
          // surface), so a far bead keeps its size and loses its edges instead.
          gl_PointSize = (1.5 + 3.4 * vR) * (0.45 + 0.75 * vD)
                       * (1.0 + 1.1 * (1.0 - vD)) * (u_res.y / 900.0 + 0.6);
        }`,
      fragmentShader: `
        ${SF_CALM}
        ${SF_ROLE}
        ${SF_CHORD}
        varying vec4 vPal; varying float vT; varying float vD; varying float vF;
        varying float vR; varying float vJ;
        uniform vec3 u_bg; uniform float u_dens, u_calm;
        void main(){
          float d = length(gl_PointCoord - 0.5);
          if(d > 0.5) discard;
          // the chord, with its highlight role reaching a tenth of the beads —
          // which is what puts individual gold and white-hot points on a violet
          // cluster instead of tinting the whole thing
          vec3 col = chord(vPal, vT, step(0.90, vJ) * 0.9);
          /* aa widens with distance: the fragment half of the defocus above.
             Crisp edges, not one smoothstep from the middle out — that is a
             blur, and a blur reads as a smudge at every size. */
          float aa = 0.02 + 0.10 * (1.0 - vD);
          float core = 1.0 - smoothstep(0.16 - aa, 0.16 + aa, d);
          float rim  = smoothstep(0.30, 0.42, d) * (1.0 - smoothstep(0.42, 0.42 + aa * 2.0, d));
          float halo = pow(max(0.0, 1.0 - d * 2.0), 2.6);
          col = mix(col, vec3(1.0), core * 0.72 + rim * 0.2);
          col = mix(u_bg, col, vF);
          float a = (core * 0.55 + rim * 0.34 + halo * 0.12)
                  * (0.40 + 0.55 * vD) * vF * u_dens;
          gl_FragColor = vec4(calm(col, u_bg, u_calm + 0.50), a);
        }`,
    }));
    mJoint.frustumCulled = false;
    mJoint.renderOrder = 9;
    S.add(mJoint);

    /* 4 ── the interior population: a cluster is made of clusters.
       Every hull in the reference encloses a haze of smaller points — nodes
       made of nodes, which is literally the shape of this project's memory
       graph: entities inside modules inside repositories.

       Direction comes off a Fibonacci sphere and radius off an independent
       hash: driving both from the same index piles the points at one pole. The
       radius exponent is 0.45, ABOVE the volume-uniform 1/3, so the cloud is
       slightly hollowed rather than core-heavy — the densest reading in the
       image comes from the hull's own vertices, not from a ball in the middle. */
    const mp = [], mn = [];
    for (let i = 0; i < N; i++) {
      const n = nodes[i];
      const cnt = CL.MOTE_MIN + Math.round(CL.MOTE_MAX * Math.pow(n.r / R_MAX, 1.8));
      for (let k = 0; k < cnt; k++) {
        const y = 1 - 2 * (k + 0.5) / cnt;
        const ring = Math.sqrt(Math.max(0, 1 - y * y));
        const th = k * 2.399963;
        const hr = ((k * 7919 + i * 104729) % 233280) / 233280;
        const rad = CL.MOTE_R * 0.9 * n.r * Math.pow(hr, 0.45);
        mp.push(Math.cos(th) * ring * rad, y * rad, Math.sin(th) * ring * rad);
        mn.push(i, hr);
      }
      /* ORBIT GOLD — 28 at 0.47 R, off the model's part list. They ride the
         same buffer as the population and are told apart by their hash alone:
         a separate pass for 28 points per cluster would be a draw call for a
         rounding error. */
      if (n.lod > 0) {
        for (let k = 0; k < CL.ORBIT_N; k++) {
          const y2 = 1 - 2 * (k + 0.5) / CL.ORBIT_N;
          const rg = Math.sqrt(Math.max(0, 1 - y2 * y2));
          const th2 = k * 2.399963 + i;
          const rr = CL.ORBIT_R * n.r;
          mp.push(Math.cos(th2) * rg * rr, y2 * rr, Math.sin(th2) * rg * rr);
          /* 0.90, not 0.985 — and this was a BUG, not a taste. The fragment
             splits the population on FILAMENT_MIX (0.60 magenta, 0.85 gold,
             0.95 white-hot), and 0.985 is past the last stop: all 28 "orbit
             GOLD" beads were being mixed 90% to white. In both references the
             amber beads inside a cage are one of its most recognisable
             features and ours had none. 0.90 lands in the gold band, and it is
             still above the 0.90 size gate that makes an orbiter 2.4x a mote. */
          mn.push(i, 0.90);
        }
      }
    }
    const gMote = new TH.BufferGeometry();
    gMote.setAttribute('position', new TH.Float32BufferAttribute(mp, 3));
    gMote.setAttribute('nd', new TH.Float32BufferAttribute(mn, 2));
    const mMote = new TH.Points(gMote, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false, depthTest: true,
      blending: TH.AdditiveBlending,
      vertexShader: `
        attribute vec2 nd;
        varying vec4 vPal; varying float vT; varying float vD; varying float vF;
        varying float vH;
        uniform vec2 u_res;
        ${HAZE_V}
        ${SPIN}
        ${SF_GRAD}
        void main(){
          int ni = int(nd.x);
          vec4 ndv = u_nd[ni];
          vPal = u_pal[ni]; vH = nd.y;
          vT = clamp(gradT(position / max(ndv.w, 1e-4), u_axis[ni], ndv.y, ndv.z), 0.0, 1.0);
          vec3 p = u_np[ni] + spin(position, ndv.x, u_t);
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          float dist = -mv.z;
          vD = clamp(1.0 - dist / 26.0, 0.0, 1.0);
          vF = exp(-max(0.0, dist - 16.0) * 0.042);
          gl_Position = projectionMatrix * mv;
          // a gold orbiter is 2.4x an interior particle — the model has them at
          // 0.046 R against 0.020 R, and at one size they read as stray sparks
          // rather than as a second population
          gl_PointSize = (1.1 + 2.0 * vD) * (1.0 + 1.4 * step(0.90, nd.y))
                       * (u_res.y / 900.0 + 0.6);
        }`,
      fragmentShader: `
        ${SF_CALM}
        ${SF_ROLE}
        ${SF_CHORD}
        varying vec4 vPal; varying float vT; varying float vD; varying float vF;
        varying float vH;
        uniform vec3 u_bg; uniform float u_dens, u_calm, u_e;
        void main(){
          float d = length(gl_PointCoord - 0.5);
          if(d > 0.5) discard;
          /* THE INTERNAL NETWORK IS FOUR POPULATIONS, in the brief's own split:
             most of it cool, a quarter magenta, a tenth gold, a few white-hot.
             The stops are cluster_spec.FILAMENT_MIX, so the same ratio holds in
             all three renderers. Gold is an ACCENT here, never the dominant
             colour — and it is not white either: white was a guess from a still
             and it is why the interior read as flat fog with sparkles in it
             rather than as a population with a second kind of thing in it. */
          float t = mix(0.05, 0.55, vH / ${F(CL.FILAMENT_MIX[0])});
          vec3 col = chord(vPal, clamp(t, 0.0, 1.0), 0.0);
          col = mix(col, roleCol(2.0), step(${F(CL.FILAMENT_MIX[0])}, vH) * 0.85);
          col = mix(col, u_warn, step(${F(CL.FILAMENT_MIX[1])}, vH) * 0.9);
          col = mix(col, vec3(1.0), step(${F(CL.FILAMENT_MIX[2])}, vH) * 0.9);
          col = mix(u_bg, col, vF);
          //: ...and a gold orbiter is brighter as well as bigger. It is a
          //: glossy metallic bead in the reference, not a spark in the fog.
          float a = (1.0 - smoothstep(0.1, 0.5, d)) * (0.13 + 0.21 * vD)
                  * (1.0 + 1.5 * step(${F(CL.FILAMENT_MIX[1])}, vH))
                  * (0.8 + 0.3 * u_e) * vF * u_dens;
          gl_FragColor = vec4(calm(col, u_bg, u_calm + 0.34), a);
        }`,
    }));
    mMote.frustumCulled = false;
    mMote.renderOrder = 8;
    S.add(mMote);

    /* READ BY tools/ PROBES. Both handles are named, because the previous
       version of inspect_cluster.py reached the live positions through
       `scene.children[0].material.uniforms.u_np` — and the moment a light
       became the first child that threw inside sc.update() every frame, which
       kills the render loop and leaves a blank canvas with nothing in the
       console. A probe that depends on child ORDER is a probe that breaks the
       next time the scene gains an object. */
    S.__nodes = nodes;
    S.__np = u.u_np.value;
    S.update = f => {
      sFeed(u, f);
      physics(Math.min(0.05, f.dt), f.e);
      // a slow orbit, so the cages are seen turning against a moving camera
      /* 9.0 and not 11. THE FIELD'S DENSITY IS THE CAMERA, not the seeding:
         cluster-render-field.png is a PACKED frame where cages overlap and
         every visible one is large, and at 11 this scene showed the whole
         drift box with black margins down both sides — the reference's
         composition is a crop of a constellation, ours was a diagram of one.
         Nothing about the bodies moved (raising the radius floor was tried
         first and only made forty cages of similar size); the frame did.
         This is a background as well as a showcase, which is why the answer is
         a crop and not more or bigger cages: u_calm still mixes the whole
         scene back toward --bg behind the app, and cropping costs nothing
         there while a denser field would cost forty more hulls. */
      cam.position.set(Math.sin(f.t * 0.06) * 2.2 + f.cam * 2.0,
                       Math.cos(f.t * 0.045) * 1.2,
                       8.4 - f.e * 1.2);
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
