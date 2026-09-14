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

     · The canvas declares an alpha channel (alpha:true) and is opaque anyway —
       it clears to --bg at alpha 1. That is the reverse of the obvious call and
       the reason is presentation, not drawing: an OPAQUE canvas is eligible to
       become its own scanout plane, Windows hands a fullscreen window
       independent flip, and a plane updating every third vsync against a page
       plane updating every one shows two moments at once. See boot().
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
/* ...AND A CEILING ON WHAT THAT SCALE MAY COST, because a scale is a
   MULTIPLIER and a multiplier has no idea how big the window is.

   The graph scene asks for 1.5 (it draws hairlines — see _ratio), and 1.5 is
   right at the size it was judged at. On a 2560x1440 window the same number is
   3840x2160 = 8.3 MILLION pixels of blended PBR, drawn again by every mip of
   the bloom pass. That is the whole of "the graph theme tears in the Qt shell":
   the frame does not finish inside the compositor's budget, so QtWebEngine
   swaps a surface mid-composite. Nothing was wrong with the scale; it was
   unbounded.

   3.0M is roughly a 1080p frame at 1.19, or 1440p at 0.89, and leaves a small
   window at the full 1.5 — the sizes the hairlines were tuned at keep them.
   _budget is the STAGE's own field rather than a constant so the degrade
   ladder in _tick can halve it on hardware that still cannot keep up. */
const STAGE_PIXEL_BUDGET = 3.0e6;
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
/* The two halves of "brighter", and they are the stage's own — see _calm().
   Both were the zen mode's lift until the theme was judged in both modes at
   once and the mode lost. In an alpha-composited scene calm decides how far a
   colour comes up off the page and gain decides how much of it survives its
   own alpha, which is why moving one without the other reaches a ceiling and
   still looks dim. */
const STAGE_LIFT = 0.12;
const STAGE_GAIN = 1.12;

/* Per-page character. The canvas is global and never restarts across
   navigation — that is what makes it one stage rather than seven wallpapers —
   but each page tilts it. `c` biases the camera, and that is now the whole of
   it.

   THERE IS NO PER-PAGE EXPOSURE ANY MORE, and the note that used to be here
   was already most of the way to saying why: `d` dimmed the field by up to a
   quarter, the first cut dropped Settings to 0.34 and Help to 0.30, and "that
   is most of why the background looked absent — you are usually ON one of
   those pages when you go looking for it". Raising the floor to 0.72 treated
   the symptom. The verdict that finished it is that the theme must look the
   same whether or not you are looking AT it:

       "theme on vs theme off have different brightness and settings, i like
        the one where i am only viewing the theme, so keep those settings for
        the theme and the theme toggle shouldn't change brightness"

   A page you are on cannot be a reason for the theme to be a different theme.
   The camera bias stays because it changes the COMPOSITION rather than the
   exposure — a different view of the same object, which is what per-page
   character was supposed to mean. */
const STAGE_PAGES = {
  home:     {c: 0.00},
  sessions: {c: 0.35},
  usage:    {c: -0.30},
  memory:   {c: 0.15},
  plan:     {c: 0.55},
  settings: {c: -0.55},
  help:     {c: -0.20},
};
function stagePage(name) { return STAGE_PAGES[name] || {c: 0.1}; }

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
  _E: 0, _Etgt: 0, _shock: 0, _pulse: 0, _cam: 0, _camTgt: 0,
  //: brightness preference, 0 = follow the skin. See setGlow()/_calm().
  /* THERE IS NO ZEN MODE HERE, and that is the point.
     STAGE used to carry a `zen()` that lifted calm by 0.12, lifted the gain by
     1.12, forced the `cinematic` tier over a user who had chosen `lite`, and
     supersampled off devicePixelRatio — so the theme was a brighter, sharper
     theme while you were looking at it than while you were using it:

         "theme on vs theme off have different brightness and settings, i like
          the one where i am only viewing the theme, so keep those settings for
          the theme and the theme toggle shouldn't change brightness"

     Three of the four are the stage's own settings now (STAGE_LIFT,
     STAGE_GAIN, and the graph scene's 1.5 render scale) and the fourth is
     simply gone: `lite` is a COST setting — it drops EffectComposer, and the
     tearing ladder in CLAUDE.md starts there — so no mode may overrule it.
     What is left of zen is layout, which app.js owns: it hides the app and
     collapses the sidebar column, and STAGE.impulse() ripples once because
     something changed. */
  glowPct: 0,
  // _T is scene time; _Tw is the rendered time it was advanced over, so
  // _T/_Tw is the clock multiplier itself — observable without counting
  // frames, which is what a software rasteriser makes meaningless.
  _T: 0, _Tw: 0, _acc: 0, _job: null,
  _th: null, _ren: null, _post: null, _sc: null, _canvas: null,
  /* the degrade ladder — see _tick. _budget is the live pixel ceiling,
     _degraded counts the steps taken (ONE WAY, it never comes back up), _cost
     is the rolling mean of what a rendered frame actually took and _over how
     many consecutive rendered frames have been above budget. */
  _budget: STAGE_PIXEL_BUDGET, _degraded: 0, _cost: 0, _over: 0,
  //: the measured display period and the ring it is the median of — see _tick.
  //: 60Hz is not a fact about anyone's machine, so it is measured.
  _vs: 0, _vsHi: 0, _vr: new Array(31).fill(1 / 60), _vi: 0,
  //: how many of our own frames we skip to keep the COMPOSITOR at 60Hz — a
  //: different resource from the tier and the pixel budget, and the one that
  //: was actually short in fullscreen. See _watch. Reset by resize().
  _slow: 1, _strain: 0,

  /* ── lifecycle ────────────────────────────────────────────────────────── */
  boot() {
    if (this.failed || this.ok) return;
    const TH = window.THREE;
    const cv = document.getElementById('stage');
    if (!TH || !cv) return;
    if (this.tier === 'off' || !MO.on) { this._static(); return; }
    try {
      /* preserveDrawingBuffer: TRUE, and it is the fix for the flicker — the
         one thing in this file that had been reasoned about correctly and
         concluded backwards.

         The fact was already written down, in blur() below: "with
         preserveDrawingBuffer:false the WebGL backbuffer is undefined after it
         has been presented. Qt then recomposites against a surface with
         nothing valid in it, and you get artefacts." That was applied to the
         unfocused window and dismissed everywhere else as "a buffer copy on
         every single frame to repair a state nobody is looking at".

         Somebody is looking at it. The stage draws at 30fps by design and
         QtWebEngine composites at 60 — more often than that while scrolling —
         so on every composite BETWEEN stage frames the canvas is exactly the
         surface that sentence describes. That is the reported symptom, which
         is a strobe rather than a scanline tear: constant, worse on scroll,
         and gone the moment the stage is switched off.

         The copy is per RENDERED frame (30/s), not per composite, and
         STAGE_PIXEL_BUDGET now bounds what it copies — measured at 2.4M px on
         an Intel UHD it does not move the frame interval. Drawing every vsync
         instead would also fix it and costs twice the GPU on exactly the
         hardware that cannot afford it. */
      /* ...and `alpha: TRUE`, which is the fullscreen half of the same bug.
         This one was a deliberate cost decision and the cost it was avoiding
         turns out not to be the one that matters.

         The old note: "a transparent surface has to be blended with the page
         underneath on every composite; an opaque one is a straight blit, and
         the scene clears to --bg so the result is identical." True, and the
         blit is exactly the problem. An OPAQUE canvas is eligible to become
         its own scanout plane, and Windows hands a fullscreen or maximised
         window independent flip — so the canvas gets promoted, and a plane
         updating every third vsync against a page plane updating every one
         puts two different moments on screen at once. Which is the report,
         exactly: clean windowed, starts on fullscreen. Windowed it cannot
         happen at all, because DWM composites everything and DWM is vsynced.

         Declaring an alpha channel makes the canvas something that must be
         BLENDED into the page, so it is not a promotion candidate and it goes
         back through the compositor with everything else. Chromium decides
         this on the context attribute, not on the pixels, and the pixels do
         not change: the clear colour is still --bg at alpha 1, so it is opaque
         to look at and identical on screen.

         The blend is per composite and it is cheap — measured, the page holds
         a clean 16.7ms rAF. Drawing every vsync in fullscreen was the other
         candidate fix and it is NOT cheap; see the note in _tick. */
      const ren = new TH.WebGLRenderer({
        canvas: cv, alpha: true, antialias: false, depth: true, stencil: false,
        powerPreference: 'high-performance', preserveDrawingBuffer: true,
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

         That is now true of ALL of them: the graph scene was the one
         exception — instanced solids under a key/fill/rim and a PMREM
         environment, with ACES rolling off their highlights — and it is drawn
         in additive hairlines again, so there is no lighting model left in
         this file for a working space or a tone curve to be correct about. */
      if (TH.ColorManagement) TH.ColorManagement.enabled = false;
      if (TH.LinearSRGBColorSpace) ren.outputColorSpace = TH.LinearSRGBColorSpace;
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
      const b = new P.UnrealBloomPass(sz, strength, 0.28, 0.55);
      /* ...AND ITS MIPS RUN AT HALF. EffectComposer.setSize multiplies by the
         renderer's pixel ratio and hands that to every pass, so the bloom's
         five mip PAIRS were being allocated and blurred at the scene's
         supersampled resolution — the most expensive thing in the frame, to
         produce a BLUR. Halving the size it is given is a quarter of the area
         at no visible cost: a gaussian does not get sharper with resolution,
         which is the one property that makes this free.
         The radius stays 0.28 and the threshold 0.55. Both are about WHICH
         pixels bloom and neither is a cost lever — widening the radius is how
         a neon scene turns into an undifferentiated spill, which is the
         opposite of what a sharper highlight needs. */
      const bset = b.setSize.bind(b);
      b.setSize = (w, h) => bset(Math.max(2, w >> 1), Math.max(2, h >> 1));
      c.addPass(b);
      c.addPass(new P.OutputPass());
      c.setSize(sz.x, sz.y);
      this._post = c;
    } catch (e) { console.warn('[stage] bloom unavailable', e); this._post = null; }
  },

  /* HOW MANY PIXELS THE SCENE IS DRAWN INTO, and it is the SCENE's number.
     STAGE_SCALE (0.75) with the display ratio ignored is right for a soft
     full-screen field, and it is the opposite of the instruments' clamp-to-2,
     which exists because they draw hairline arcs.

     A scene that IS hairlines says so in its own scale, and the graph scene
     does (1.5): thin glass rods and 42 small beads per cage crawl and
     stair-step at 0.75. This used to be a zen-only supersample off
     devicePixelRatio, which meant the theme was sharper when you were looking
     at it than when you were using it — the same complaint as the brightness
     lift, and the same answer. A mode may not change what the scene is.

     Supersampling and not MSAA on purpose: antialias can only be chosen when
     the context is created, and it does not reach EffectComposer's render
     targets anyway — so it would sharpen the tier that has no bloom and leave
     the one that does exactly as it was.

     ...AND THE SCENE'S NUMBER IS A WISH, NOT THE ANSWER. A scale is a
     multiplier and knows nothing about the window it multiplies; 1.5 was
     judged at one size and silently became 8.3M pixels of blended PBR on a
     1440p panel, which is most of why this scene tore in the Qt shell. The
     cap is on the PRODUCT, so a small window still gets the crisp hairlines
     the scene asked for and a large one gets the same frame budget. */
  _ratio() {
    const want = (this._sc && this._sc.scale) || STAGE_SCALE;
    const px = Math.max(1, window.innerWidth * window.innerHeight);
    return Math.min(want, Math.sqrt(this._budget / px));
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
     being mixed toward the page at all, and a bright skin washes out flat.

     STAGE_LIFT is unconditional, and it used to be the zen exception. Zen is
     the mode where the app is hidden and the canvas is the only thing on
     screen, so it lifted the ceiling by 0.12 and the gain by 1.12 — and the
     result was a theme that looked like one theme while you were looking at it
     and a dimmer one while you were using it. That is not an exception, it is
     two settings:

         "i like the one where i am only viewing the theme, so keep those
          settings for the theme and the theme toggle shouldn't change
          brightness"

     So the lift stays and the mode goes. Zen is now a LAYOUT mode: it hides
     the app and nothing else. */
  _calm() {
    const base = this.calmOf != null ? this.calmOf : 0.3;
    const k = this.glowPct > 0 ? this.glowPct / 100 : 1;
    return Math.min(0.95, base * k + STAGE_LIFT);
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
    return Math.min(2.2, k * STAGE_GAIN);
  },
  page(name) {
    const p = stagePage(name);
    this._pageKey = name; this._camTgt = p.c;
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
     This used to be where the undefined-backbuffer fact was written down, and
     hiding the canvas was called the cheap fix for it because
     `preserveDrawingBuffer: true` "costs a buffer copy on every single frame
     to repair a state nobody is looking at". That reasoning is now in boot(),
     where it belongs, and it came out the other way: somebody is looking at
     it on every composite between stage frames, which is what the flicker was.
     The buffer is preserved, so this is no longer load-bearing for artefacts.

     It stays anyway, for the reason that was always the better one: hiding the
     surface removes it from the composite entirely, which is zero GPU for the
     app while you work in another one — strictly better than a
     paused-but-present canvas. The static CSS wash takes over, so the window
     still looks like itself if you glance at it. */
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
    this._cam += (this._camTgt - this._cam) * k;
    if (this._shock > 0) this._shock = Math.max(0, this._shock - dt / STAGE_SHOCK_S);
    if (this._pulse > 0) this._pulse = Math.max(0, this._pulse - dt / STAGE_PULSE_S);

    /* ── THE FRAME CAP IS A VSYNC DIVISOR, and this is the tearing bug ───────
       Measured in the real Qt shell, on the graph world, after the cost pass
       below had already landed: the page's own rAF was a clean 16.7ms at both
       p50 and p95 — a rock-solid 60Hz with zero long tasks — while the stage's
       own frame interval came out p50 33.7ms and p95 50.1ms. Those two numbers
       are not "slow". They are exactly TWO and THREE vsyncs.

       The old cap was an accumulator against a wall-clock target: render once
       1/fps has elapsed. 1/34 is 29.4ms and a 60Hz display cannot deliver
       29.4ms — the only intervals that exist are 16.7, 33.3, 50.0. So the
       accumulator alternated 2,2,3,2,2,3… forever. That is a beat frequency,
       the canvas swap lands at a different point of the compositor's cycle
       every frame, and on a QtWebEngine GPU hardware surface that is precisely
       what reads as tearing. It is also invisible to every measurement this
       repo had, because the AVERAGE is right — only the distribution is wrong,
       and nothing was looking at one.

       So the target is snapped to a whole number of vsyncs. CEIL rather than
       round: never render more often than the fps asked for, and at 60Hz it
       keeps idle and busy on genuinely different divisors (3 -> 20fps and
       2 -> 30fps) instead of collapsing both to 30. Idle loses four nominal
       fps and gains a cadence that does not beat, which is the whole trade —
       and what carries "the workspace is busy" was never the frame rate, it is
       the scene CLOCK below.

       The vsync period is measured, not assumed: 60Hz is not a fact about
       anyone's machine, and a 120Hz panel or a 30Hz remote session needs a
       different divisor. It is a median-ish floor over the deltas MO hands us,
       clamped to a sane range so one hitched frame cannot latch a slow rate. */
    const fps = STAGE_FPS_IDLE + (STAGE_FPS_BUSY - STAGE_FPS_IDLE) * this._E;
    /* THE MEDIAN OF A RING, and neither half of that is decoration. The first
       cut of this ratcheted toward the minimum (`Math.min(prev, ema)`) so that
       one hitched frame could not latch a slow rate — and it guarded the wrong
       direction: a ratchet that only goes down latches on the SHORT side
       instead, which is what two rAF callbacks landing close together produce.
       Measured in the Qt shell, it reported a 6.5ms vsync on a 60Hz panel and
       the divisor came out 5. An average is no better: a dropped frame is
       double-length and pulls it up. A median is indifferent to both, which is
       exactly the property wanted, and over 31 samples it costs one sort every
       31 frames rather than anything per frame. */
    this._vr[this._vi++ % 31] = dt;
    if (this._vi % 31 === 0) {
      const s = this._vr.slice().sort((a, b) => a - b);
      this._vs = s[15];
      /* ...and the UPPER end of the same sort, which is a different question.
         The median answers "what is the display period" and has to be robust,
         so it ignores the tail by construction. Strain lives entirely IN the
         tail: measured at _slow 2, the page's rAF was a healthy 16.7ms at p50
         and still 50ms at p95, and a median-triggered back-off therefore
         stopped one rung early while the thing being reported — an occasional
         dropped frame, which is what a flicker IS — was still happening. One
         sort, two statistics. */
      this._vsHi = s[27];
    }
    const vs = Math.min(0.05, Math.max(1 / 144, this._vs || 1 / 60));
    /* DRAWING EVERY VSYNC IN FULLSCREEN WAS TRIED HERE AND IT IS WORSE.
       It is the obvious answer to the fullscreen flicker (see `alpha` in
       boot(): the canvas gets its own scanout plane there, and a plane that
       updates every third vsync against a page plane that updates every one
       shows both at once), and it is wrong. Measured in the Qt shell: the
       stage's own interval went 50.0 -> 28.2ms as intended, and the PAGE's rAF
       went from a clean 16.7/16.7 to 16.8/66.6 — the whole app dropped to
       ~36fps, which is far worse than the artefact it was chasing.

       The 0.2ms "drained frame" this was justified on is not real: gl.finish()
       does not force a drain under ANGLE/D3D11, so that number measures
       command submission like everything else. Do not re-derive full-rate
       from it. The mechanism is fixed at the plane instead. */
    /* ...times _slow, which is how often we are ALLOWED to make the compositor
       redraw the screen. See _watch: this is a different resource from the one
       everything above manages, and it is the one that was actually short. */
    const want = Math.max(1, Math.ceil(1 / fps / vs)) * vs * this._slow;
    this._acc += dt;
    // half a vsync of slack: the delta MO reports jitters by a millisecond
    // either way, and without it every other frame is pushed a whole vsync late
    if (this._acc < want - vs * 0.5) return true;
    const fdt = this._acc; this._acc = 0;
    this._watch(fdt, want);

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
                 pulse: this._pulse, dens: this._gain(),
                 cam: this._cam, calm: this._calm()});
      if (this._post) this._post.render(fdt);
      else this._ren.render(sc.scene, sc.camera);
    } catch (e) { this._giveUp('render failed: ' + e.message); return false; }
    // only now is it safe to drop the static wash — a frame has landed
    if (!this._painted) { this._painted = true; this._live(); }
    return true;
  },

  /* ── the degrade ladder, and it is MEASURED rather than guessed ───────────
     Every number in this file was tuned under SwiftShader on a bench, and the
     handoff says so in as many words: "cost has not been measured on real
     hardware, and this pass ADDED to it". A background cannot ask the user
     what their GPU is, so it watches itself.

     WHAT IS MEASURED IS THE ACHIEVED INTERVAL, not the time around render().
     WebGL submission is asynchronous — timing the render call measures how
     long it took to queue the commands, which on a saturated GPU is near zero.
     What a saturated GPU actually does is stall the next buffer swap, and
     that shows up here as `fdt`: the real wall time since the last frame we
     drew. We asked for `want` and got `fdt`, so the ratio is the answer, and
     it is frame-rate independent — same lesson as _T/_Tw, never assert on how
     many frames the machine managed.

     ONE WAY, ALWAYS. A ladder that can climb back up oscillates: it degrades,
     the frame gets cheap, it restores, the frame gets expensive, forever — and
     a background that changes quality twice a second is worse than a slow one.
     Two steps, then it stops trying. */
  _watch(fdt, want) {
    // a parked chain resuming (blur, tab switch, blur() forcing _acc = 1) is
    // not a slow frame, and one such sample would poison the mean for a minute
    if (fdt > 0.5) { this._over = 0; return; }
    this._cost = this._cost ? this._cost * 0.9 + fdt * 0.1 : fdt;

    /* ── EVERY CANVAS UPDATE COSTS A FULL-SCREEN RECOMPOSITE ────────────────
       The resource this manages is the COMPOSITOR's, and it is a different one
       from everything else in this file. Our own drawing is trivial — measured
       on the reporting machine, a 3.75x cut in fill bought 4ms and a
       two-triangle scene ran at the same rate as this one, so the scene is
       about 1.6ms. But the canvas is full-viewport, so every frame we present
       makes the compositor redraw the whole screen underneath the app's
       translucent panels, and at 2560x1440 on an Intel UHD it cannot do that
       24 times a second on top of everything else.

       What that looks like is NOT slowness. Chromium halves the page's frame
       rate when it cannot keep up, so the whole app lurches between 60 and
       30Hz — which is what was reported as flickering in fullscreen, and why
       it appears at fullscreen and nowhere else: windowed, the composited area
       is small enough to afford. Measured, with the stage at its normal rate
       against the same stage let through one frame in three:

           every frame:   page rAF p50 33.3ms / p95 83.3ms   (30fps, lurching)
           one in three:  page rAF p50 16.7ms / p95 33.4ms   (60fps, steady)

       So the signal is the DISPLAY PERIOD ITSELF, which _tick already measures
       as the median of recent rAF deltas. A compositor delivering 60Hz reads
       16.7ms; one that has given up reads 33.3ms. Nothing else here could see
       this: the stage's own interval stayed within 25% of its target the whole
       time, because it was hitting the target it asked for — on a page that
       had been slowed to half speed underneath it.

       ONE WAY UNTIL THE LAYOUT CHANGES, which is what stops it oscillating.
       Back off, and the period recovers to 16.7 — speed up on that and it
       strains again, forever. So _slow only rises, and resize() resets it,
       because entering or leaving fullscreen is exactly when the answer
       changes and exactly when a resize fires.

       A genuine 30Hz panel will back off once and lose a little motion in a
       background. That is the right trade against the alternative, which is
       reading a strained 60Hz panel as if it were fine. */
    if (this._vi > 31 && this._slow < 4) {
      this._strain = Math.max(0, this._strain + (this._vsHi > 0.020 ? 2 : -1));
      if (this._strain > 90) {
        this._strain = 0;
        this._slow *= 2;
        console.warn('[stage] compositor at ' + Math.round(this._vs * 1000) +
                     'ms/frame — drawing 1 in ' + this._slow);
      }
    }
    if (this._degraded >= 2) return;
    /* AN INTEGRATOR, NOT A CONSECUTIVE RUN. The first cut of this counted 90
       frames in a row over budget and reset on any frame that was not, which
       measured against the real Qt shell never fired once — even while the
       scene was visibly missing its target, because a machine that is 20% short
       is late in bursts and on time in between, and a run of ninety never
       happens. Up two, down one: it trips when clearly more than a third of
       frames are late and stays quiet on an occasional hitch, which is the
       distinction that matters and a consecutive counter cannot express. */
    this._over = Math.max(0, this._over + (fdt > want * 1.5 ? 2 : -1));
    if (this._over < 120) return;
    this._over = 0; this._degraded++;
    const ms = Math.round(this._cost * 1000);
    if (this._degraded === 1) {
      // fill first: it is the cheapest thing to give up and the one the user
      // is least likely to notice on a background
      this._budget *= 0.5;
      this.resize();
      console.warn('[stage] ' + ms + 'ms frames — halving the pixel budget');
    } else {
      // then bloom, which is the tearing ladder CLAUDE.md already documents
      this.tier = 'lite';
      this._mkPost();
      console.warn('[stage] ' + ms + 'ms frames — dropping to the lite tier');
    }
  },

  resize() {
    if (!this.ok || !this._ren || !this._sc) return;
    const w = window.innerWidth, h = window.innerHeight;
    /* the compositor back-off is per LAYOUT: how much screen a canvas update
       costs to recomposite is a function of how big the screen area is, and
       that is exactly what has just changed. Entering fullscreen is where it
       is earned and leaving is where it must be given back — resetting here is
       also what lets it be one-way in between, which is what stops it
       oscillating. See _watch. */
    this._slow = 1; this._strain = 0;
    // the ratio is a function of the window now (_ratio caps the product), so
    // it has to be re-read here and not only at build — otherwise a window
    // dragged from a laptop panel to a 4K one keeps the small window's scale
    this._ren.setPixelRatio(this._ratio());
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
    u_ok: {value: c.ok}, u_err: {value: c.err || c.acc2},
    //: white is a role like any other, so a shader need never write a bare
    //: vec3(1) — the ceiling in calm() is the only place a literal belongs.
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

  /* Graph — THE homage, and the cluster is FLAT.

     Every part the reference has, and no 3D rendering of any of it:

     > "keep the complications of the cluster as it was before just remove the
     > 3d part, so keep the nodes on the cluster as a dot which has an outer
     > circle and keep everything inside, just remove from all of this the 3d
     > effect"

     What that removed: three lights, a PMREM environment built from a gradient
     scene, ACES tone mapping, and nine InstancedMesh passes of
     MeshPhysicalMaterial — the frame as a glass sleeve with a coaxial core, a
     junction as a hot core inside an energy volume inside a glass housing, the
     centre as the same object one size up, and a conduit as a coaxial triple
     with a gold collar and a glass hub at each end. 353,566 triangles in 33
     draw calls.

     What it kept, which is everything the cluster is MADE of:

       · the 480-rod hairline shell, at the LOD the cage's own size earns
       · the second 480-rod cage inside it at 0.53 R — a cluster is made of
         clusters, which is literally this project's memory graph
       · the hull's tinted faces, so a cage has a volume rather than being a
         bare wireframe
       · the coarse frame — 30 rods, three times a shell rod's width
       · the 20 spokes, stopping at 0.56 R and never reaching the centre
       · the 162 beads on the hull, the 12 junctions, the lit centre
       · the interior population and its 28 gold orbiters
       · the conduits, as fine lines with packets travelling them

     Four draw calls: one merged ribbon buffer for every rod, one for the
     faces, one merged sprite buffer for every node, one LineSegments for the
     conduits. Every pass is additive and depth-TESTED but never depth-WRITING,
     which is what "no 3D" means here — nothing in this scene is shaded by a
     light, and nothing occludes anything.

     Node positions are deterministic — no Math.random anywhere — so the
     constellation is identical on every reload. A layout that reshuffles reads
     as noise. */
  graph(TH, c) {
    const cam = new TH.PerspectiveCamera(55, 1, 0.1, 60);
    //: 1.5, and it is the scene that asks. This is a field of glass rods a few
    //: pixels wide and 42 beads per cage; at 1.0 they crawl and stair-step,
    //: which is what the zen-only supersample was for before a mode stopped
    //: being allowed to change the picture.
    const S = sScene(TH, cam, .5, 1.5);
    const u = sU(TH, c);
    //: every measurement of the cluster and the conduit, generated from
    //: claude_sessions/cluster_spec.py. Referenced directly and not defensively:
    //: if it is missing the bundle is broken, and the scene build failing lands
    //: on the static background, which is the right answer to a broken bundle.
    const CL = CLUSTER;

    /* THE ROLES, DEEPENED — measured, and it is the answer to "the theme's
       accents are pale by design and the reference's are not".

       A perpendicular cut across a frame tube in `cluster-render-single.png`
       reads (0, 55, 135) in the wall and (0, 128, 233) in the energy: RED IS
       ZERO, in both. Ours is #7dcfff, which is (125, 207, 255) — the same hue
       and the same HSL saturation, and a third of the way to white. That is
       the whole gap, and it is a LIGHTNESS gap rather than a saturation one:
       #7dcfff is already s = 1.0 (its max channel is 255), so no saturation
       push can move it. What makes a pale tint a saturated hue is dropping L
       at constant H and S — #7dcfff at L 0.46 is (0, 118, 235), which is the
       measurement above to within a couple of levels.

       That is also why this file kept reaching for pow(): pow darkens, and
       darkening was the half of it that worked. Doing it here instead means
       every pass gets it — the lit solids, the additive hairlines, the faces,
       the motes and the conduit — from one place, and the pow() curves stay
       what they are for, which is composition.

       Scene-local on purpose, and it is NOT a palette edit. u_acc and u_acc2
       are the app's link and focus colours and they clear a 4.5:1 contrast
       floor as TEXT (tests/test_themes.py); a palette deep enough for this
       field would fail that. u_bg, u_panel and u_white are left alone: the
       first two are the ground this scene is mixed back toward and the third
       is a highlight gate, not a hue. */
    const DEEP_L = 0.58, DEEP_S = 1.12;
    const _hsl = {h: 0, s: 0, l: 0};
    for (const k of ['u_acc', 'u_acc2', 'u_err', 'u_warn', 'u_ok']) {
      u[k].value.getHSL(_hsl);
      u[k].value.setHSL(_hsl.h, Math.min(1, _hsl.s * DEEP_S), _hsl.l * DEEP_L);
    }

    // ── node field ──
    const N = 40;
    const R_MAX = 1.60;
    //: the near face of the drift wedge (see BOUND_Z below). The hero starts
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
    /* ...AND THE BOX IS A FRUSTUM, WHICH IS WHAT FILLS THE FRAME.
       The one thing left on the work queue that the eye reads first: the
       reference field is edge to edge and ours had black gutters down both
       sides and along the bottom. Measured rather than judged — the seeding
       box was a RECTANGLE 20.0 wide and 10.4 tall at every depth, and the
       frame a perspective camera sees is a wedge. At the near slice (9.4 units
       out) the visible half-height is 4.89 and the box filled it exactly; at
       the far slice (22.6 out) the visible half-height is 11.8 and the box
       still only reached 4.94, so the back HALF of the field sat in the middle
       fifth of the frame with nothing around it. No amount of colour or bloom
       reaches that, and neither does the lever the queue named first: more
       bodies packs the middle tighter and leaves the corners exactly as empty.

       So x and y are placed as a FRACTION OF THE FRAME at each body's own
       depth. The near slice is unchanged (which is why the hero still reads);
       the far slice spreads 2.4x and lands in the corners. It also costs
       nothing the drift has to absorb — spreading the back apart LOWERS the
       density the collision term sees, where narrowing the box (the queue's
       other lever) would have raised it into the cascade the drift speeds were
       tuned against.

       DESIGN_AR is fixed rather than read from the camera: the seeding happens
       once at build and the window resizes. 1.92 is the ratio the rectangular
       box already had (20.0 / 10.4), so a square window crops the sides
       exactly as it did before. */
    const CAM_Z = 8.4, TAN_HALF_FOV = 0.5206, DESIGN_AR = 1.92;
    const SEED_FILL = 1.02, DRIFT_FILL = 1.18;
    //: half-height of the frame at a body's depth, in POS space — u_np pushes
    //: every cluster 3.0 further back than the number the physics holds
    const frameH = z => (CAM_Z - (z - 3.0)) * TAN_HALF_FOV;
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
      /* Floor 0.34, top 1.60, exponent 3.4 — and the FLOOR is the number that
         has moved three times, always for the same reason and always by too
         little. The tail's shape is right (three or four dominant hulls among
         dozens is what the reference field measures) and the top is right; the
         problem was always the bottom. At 0.10 and then 0.16, thirteen of the
         forty cages came out under 0.22 — below the LOD ladder's first break,
         which means NO frame and NO junctions at all, so they drew as bare
         specks joined by conduit and a third of the frame was a wire diagram.
         In cluster-render-field.png every cage, down to the smallest in the
         crop, has its frame and its twelve lit junctions.

         The floor is also the only lever here that costs nothing the drift has
         to absorb. Moving bodies closer together is what the drift cannot take
         (the lattice already packs 40 densely and the old speeds turned a
         drift into a permanent collision cascade), and the frustum seeding
         above LOWERED the density at depth, which is what left room for this.
         The multiplier comes down to 1.26 so the largest hull does not grow
         with the smallest: the top of the range is unchanged at 1.60, and only
         about one more cluster crosses the ladder's upper break into the
         480-rod shell. */
      const r = 0.34 + Math.pow(h, 3.4) * 1.26;
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
      /* the depth first, because x and y are a fraction of the frame AT that
         depth — see the frustum note above the lattice constants. */
      const nz = ((gz + 0.5 + j3) / GZ * 2.0 - 1.0) * 6.6 - 4.6;
      const nh = frameH(nz) * SEED_FILL;
      nodes.push({
        x: ((gx + 0.5 + j1) / GX * 2.0 - 1.0) * nh * DESIGN_AR,
        y: ((gy + 0.5 + j2) / GY * 2.0 - 1.0) * nh,
        /* THE BOX IS DEEP, and that is where the background network comes
           from. The brief asks for distant clusters — smaller, dimmer, fading
           into darkness rather than a flat starfield — and at a span of 3.4
           there was no BACK of the field: every cage sat within a couple of
           units of the camera plane, so the frame had a foreground and empty
           black behind it. 6.6 deep and pushed back 4.6 puts a third of them
           past 18 units, where vFar and the LOD ladder already make them
           small, soft and mixed toward the ground with nothing new to draw. */
        z: nz,
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
    /* off the exact centre, not out of frame — and the two ratios are of the
       frame, not of the old rectangle. Pulling the hero forward SHRINKS the
       frame around it (the wedge again), so a hero seeded in the corner of the
       far slice would start a third of the way outside the near one and spend
       the first seconds of every session being shoved back in by the wall. */
    const heroK = frameH(BOUND_Z_NEAR) / frameH(nodes[hero].z);
    nodes[hero].x *= 0.45 * heroK;
    nodes[hero].y *= 0.35 * heroK;
    nodes[hero].z = BOUND_Z_NEAR;               // the near face of the wedge

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

    //: how far a body may drift in z. x and y are not constants any more —
    //: they are DRIFT_FILL of the frame at the body's own depth, or a cage
    //: seeded into the corner of the far slice would be shoved back into the
    //: rectangle the frustum seeding just replaced.
    const BOUND_Z = 11.5;
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
        //: the wedge at this body's depth, read once per body. One frame of
        //: lag on z is not worth a second pass over the axes.
        const h = frameH(POS[i * 3 + 2]) * DRIFT_FILL;
        const WALL = [h * DESIGN_AR, h, BOUND_Z];
        for (let k = 0; k < 3; k++) {
          const a = i * 3 + k;
          POS[a] += VEL[a] * dt * spi;
          // Reflect at the wall, and clamp back inside so a body can never
          // escape and drift off screen for the rest of the session. The limit
          // is inset by the radius, or a large solid half-leaves the frame while
          // its centre is still legally inside.
          const lim = Math.max(0.5, WALL[k] - nodes[i].r);
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


    /* GLSL has no implicit int-to-float, so a spec value that happens to be
       a whole number must still be written with a decimal point: `${CL.X}` for
       an X of 1 emits `1`, and `float y = 1;` does not compile. */
    const F = v => (Number(v) || 0).toFixed(4);

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
    /* `pop` is which population the rod belongs to — 0 the shell, 1 the inner
       web, 2 the coarse frame, 3 a spoke. It exists because the WEB has to
       turn on its own clock (see the vertex shader): every rod used to be spun
       by one call, so the cage at 0.53 R was rigidly locked to the one at
       1.0 R and the two read as a single object with a denser middle. */
    const rod = (n, i, A, B, half, alpha, pop) => {
      const base = erod * 4;
      for (const [t, side] of [[0, -1], [0, 1], [1, -1], [1, 1]]) {
        const me = t ? B : A, other = t ? A : B;
        ep.push(me[0], me[1], me[2]);
        eo.push(other[0], other[1], other[2]);
        et.push(t); ew.push(side); ea.push(alpha);
        en.push(i, half, pop);
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
                  [q[3] * n.r, q[4] * n.r, q[5] * n.r],
                  CL.SHELL_ROD_HALF * n.r, dens, 0);
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
          //: 0.75, up from 0.55 — "brighten a bit the geometric figure inside
          //: the cluster just a bit". It is the one population that reads
          //: THROUGH the shell rather than on it, so it loses to two layers of
          //: additive hairline before it reaches the eye.
          rod(n, i, [q[0] * n.r * w, q[1] * n.r * w, q[2] * n.r * w],
                    [q[3] * n.r * w, q[4] * n.r * w, q[5] * n.r * w],
                    CL.WEB_ROD_HALF * n.r, 0.75, 1);
        }
      }
      /* THE COARSE FRAME — the most recognisable feature of the reference, and
         it is in this buffer now rather than being a lit glass sleeve with a
         coaxial core inside it. It is the same `rod()` as the shell: a
         camera-facing ribbon at the spec's own width, additive, no depth
         write. What made it read as a frame was never the lighting model — it
         is that it is three times the width of a shell rod and carries a
         junction at each end, and both of those survive being flat.

         Alpha 1.0 against the shell's ~0.3 and the web's 0.55: thirty rods
         against four hundred and eighty cannot share a number (the same
         argument ROD_ALPHA_BY_EDGES already makes), and this is the population
         the eye is supposed to read first. */
      if (n.lod > 0) {
        for (const q of SHELL[0]) {
          rod(n, i, [q[0] * n.r, q[1] * n.r, q[2] * n.r],
                    [q[3] * n.r, q[4] * n.r, q[5] * n.r],
                    CL.FRAME_HALF * n.r, 1.0, 2);
        }
        /* ...and the twenty spokes, which stop at 0.56 R and never reach the
           centre. Twenty rods meeting at one point sum, additively, into a
           white star brighter than anything the scene means — that is what
           SPOKE_IN is for, and it matters MORE here than it did under the
           lights, because every one of these passes is additive. */
        for (const d of SPOKES) {
          rod(n, i, [d[0] * n.r * CL.SPOKE_IN, d[1] * n.r * CL.SPOKE_IN,
                     d[2] * n.r * CL.SPOKE_IN],
                    [d[0] * n.r * CL.SPOKE_OUT, d[1] * n.r * CL.SPOKE_OUT,
                     d[2] * n.r * CL.SPOKE_OUT], CL.SPOKE_HALF * n.r, 0.42, 3);
        }
      }
    }
    const gEdges = new TH.BufferGeometry();
    gEdges.setAttribute('position', new TH.Float32BufferAttribute(ep, 3));
    gEdges.setAttribute('eo', new TH.Float32BufferAttribute(eo, 3));
    gEdges.setAttribute('et', new TH.Float32BufferAttribute(et, 1));
    gEdges.setAttribute('ew', new TH.Float32BufferAttribute(ew, 1));
    gEdges.setAttribute('ea', new TH.Float32BufferAttribute(ea, 1));
    gEdges.setAttribute('nd', new TH.Float32BufferAttribute(en, 3));
    gEdges.setIndex(eidx);
    const mEdges = new TH.Mesh(gEdges, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false, depthTest: true,
      side: TH.DoubleSide, blending: TH.AdditiveBlending,
      vertexShader: `
        attribute vec3 eo; attribute float et; attribute float ew;
        attribute float ea; attribute vec3 nd;
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
          /* THE INNER WEB TURNS ON ITS OWN CLOCK, and that is the whole
             reason nd.z exists. Every rod used to be spun by one call, so
             the cage at 0.53 R was rigidly locked to the cage at 1.0 R and the
             two read as one object with a denser middle — you could not see
             that there was a second cage in there at all.

             OPPOSITE, which is -1 and not the -0.62 this first shipped as.
             Reversed-and-slower was chosen on the grounds that slower is
             calmer; opposite means the mirror of the outer cage's motion, and
             it is also the fastest the pair can be made to read without
             either one of them turning faster — the RELATIVE rate between the
             two lattices is what the eye picks up, and at -1 that is twice the
             cluster's own. A co-rotation at a different rate is only legible
             while you watch one rod, where two lattices sliding THROUGH each
             other is legible from the shape of the whole thing. The +1.7
             offset stops them starting aligned, which is the one moment the
             effect is invisible. Only the web (pop 1) takes it; the shell, the
             frame and the spokes are the same object and must not drift
             apart. */
          float own = step(0.5, nd.z) * step(nd.z, 1.5);
          float tw = mix(u_t, -u_t + 1.7, own);
          vec3 pa = org + spin(position, ndv.x, tw);
          vec3 pb = org + spin(eo, ndv.x, tw);
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
          col = pow(max(col, vec3(0.0)), vec3(1.5));
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
          vec3 col = pow(max(chord(vPal, vT, 0.05), vec3(0.0)), vec3(1.5));
          col = mix(u_bg, col, vF);          // depth, BEFORE calm()
          // pow 3 and not 2: at 2 the interior still carries enough to fill the
          // hull with flat colour, which is a bubble rather than a cage.
          float a = (0.016 + 0.130 * pow(vE, 3.0)) * (0.45 + 0.55 * vD)
                  * vF * u_dens * (0.85 + 0.3 * u_e);
          gl_FragColor = vec4(calm(col, u_bg, u_calm + 0.26), a);
        }`,
    }));
    mFaces.frustumCulled = false;
    mFaces.renderOrder = 6;      // under the rods, the beads and the conduits
    S.add(mFaces);

    /* 3 ── EVERY NODE ON THE CLUSTER, AS A DOT WITH AN OUTER CIRCLE.
       One buffer, three populations, told apart by `kd`:

         kd 0  the 162 small beads on the hull — a TEXTURE on the surface,
               deduplicated to the distinct corners because
               IcosahedronGeometry is a triangle soup (240 positions for 42
               corners, and drawing the soup stacks five or six additive
               sprites on each of them).
         kd 1  the 12 frame junctions. These were three concentric
               MeshPhysicalMaterial spheres in the solid pass — a hot core
               inside an energy volume inside a glass housing — and the
               instruction is to keep the node and drop the 3D: a dot with an
               outer circle is what that object looks like drawn flat, and the
               fragment shader below already had the core/rim/halo terms to do
               it with.
         kd 2  the lit centre, one per cluster. Same object one size up, which
               is what the model's parts list says it is.

       Sized in WORLD units for kd 1 and 2 (see the vertex shader): a junction
       is a fixed fraction of its own hull in the reference, so it has to shrink
       with distance like the rods do, or a far cluster is a ring of blobs. The
       shell beads keep the screen-space size they had — they are a texture,
       and a texture that scales to a quarter of a pixel is gone. */
    const jp = [], jn = [], jk = [];
    for (let i = 0; i < N; i++) {
      const n = nodes[i];
      const V = n.lod === 2 ? V_SHELL : V_FRAME;
      for (const v of V) {
        jp.push(v[0] * n.r, v[1] * n.r, v[2] * n.r);
        jn.push(i, n.r); jk.push(0, 0);
      }
      if (n.lod > 0) {
        for (const v of V_FRAME) {
          jp.push(v[0] * n.r, v[1] * n.r, v[2] * n.r);
          jn.push(i, n.r); jk.push(1, CL.FRAME_BEAD_R * n.r);
        }
        jp.push(0, 0, 0);
        jn.push(i, n.r); jk.push(2, CL.CORE_SHELL_R * n.r);
      }
    }
    const gJoint = new TH.BufferGeometry();
    gJoint.setAttribute('position', new TH.Float32BufferAttribute(jp, 3));
    gJoint.setAttribute('nd', new TH.Float32BufferAttribute(jn, 2));
    //: .x is which population, .y is its world radius (0 for a shell bead,
    //: which is sized in screen space)
    gJoint.setAttribute('kd', new TH.Float32BufferAttribute(jk, 2));
    const mJoint = new TH.Points(gJoint, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false, depthTest: true,
      blending: TH.AdditiveBlending,
      vertexShader: `
        attribute vec2 nd; attribute vec2 kd;
        varying vec4 vPal; varying float vT; varying float vD; varying float vF;
        varying float vR; varying float vJ; varying float vK;
        uniform vec2 u_res;
        ${HAZE_V}
        ${SPIN}
        ${SF_GRAD}
        void main(){
          int ni = int(nd.x);
          vec4 ndv = u_nd[ni];
          vPal = u_pal[ni]; vR = nd.y; vK = kd.x;
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
          /* A SHELL BEAD IS SIZED IN SCREEN SPACE AND A JUNCTION IS NOT,
             and that is the difference between a texture and a part. The bead
             gets the same three cues it always had — mass, depth, and a
             defocus that keeps its size and loses its edges, because a real
             blur is a readback this shell does not get to have (it is what
             tore the Qt surface). A junction and the centre are a fixed
             fraction of their own hull in the reference, so they are projected
             like geometry: worldR * (viewport height * P[1][1] / 2) / distance,
             which is exactly how many pixels a sphere of that radius covers.
             Clamped at the top, or the hero's centre is a dinner plate. */
          float scr = (1.5 + 3.4 * vR) * (0.45 + 0.75 * vD)
                    * (1.0 + 1.1 * (1.0 - vD)) * (u_res.y / 900.0 + 0.6);
          float wrl = kd.y * u_res.y * projectionMatrix[1][1] * 0.5
                    / max(dist, 0.25);
          gl_PointSize = kd.x > 0.5 ? clamp(wrl * 2.0, 2.0, 96.0) : scr;
        }`,
      fragmentShader: `
        ${SF_CALM}
        ${SF_ROLE}
        ${SF_CHORD}
        varying vec4 vPal; varying float vT; varying float vD; varying float vF;
        varying float vR; varying float vJ; varying float vK;
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
          /* A DOT WITH AN OUTER CIRCLE, and the three populations differ only
             in where the two radii sit. A shell bead is mostly dot: it is a
             point of light on a surface. A junction and the centre are the
             object the solid pass drew as three concentric spheres — a hot
             white middle, a coloured volume around it, and a bright ring at
             the edge where the housing turned away — so the dot keeps the
             white, the gap between the radii keeps the chord, and the ring IS
             the silhouette. Drawn flat, that reads as a node rather than as a
             sphere, which is the whole instruction.

             THE FOUR-TERM VERSION OF THIS WAS TRIED AND REJECTED. A second
             reference still was read for a spiked core, a filled bubble, a
             hairline shell and a second hairline outside it — every one of
             them present in that image, and the judgement on the result was
             "the cluster was better before this last reference modifications
             to the cluster nodes and core". So the node is two radii again.
             The rejected version is in the session notes rather than here,
             because what a shader needs to say is what it draws. */
          float isN = step(0.5, vK);
          float rc = mix(0.16, 0.30, isN);          // the dot
          float rr = mix(0.42, 0.46, isN);          // the outer circle
          float core = 1.0 - smoothstep(rc - aa, rc + aa, d);
          float ring = smoothstep(rr - 0.13, rr, d)
                     * (1.0 - smoothstep(rr, rr + aa * 2.0, d));
          float halo = pow(max(0.0, 1.0 - d * 2.0), 2.6);
          //: the centre is the one thing in a cage that is WHITE at its middle
          //: — and it is not a sun: in both references the middle of a cluster
          //: is dark, so the white stops at the dot and the volume around it is
          //: the chord, mixed no further out than the ring.
          float hot = core * mix(0.72, 0.52 + 0.34 * step(1.5, vK), isN);
          col = mix(col, vec3(1.0), hot + ring * 0.24);
          col = mix(u_bg, col, vF);
          float a = (core * mix(0.55, 0.62, isN) + ring * mix(0.34, 0.72, isN)
                   + halo * mix(0.12, 0.22, isN))
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

    /* 5 ── THE CONDUITS, AS FINE LINES.
       "for the connection lines you can go back to drawing fine lines instead
       of all this mess" — so this is one LineSegments, not the coaxial triple
       of housing, glass sleeve and filament plus a gold collar and a glass hub
       at each end that the solid pass drew.

       WHICH cages are joined: the four nearest neighbours BY DISTANCE, taken
       once at rest and then held. The pairs used to be index offsets — i+1,
       i+2, i+3 and an i+8 chord — and the indices run along the seeding
       lattice, so after the physics has moved anything "i+8" is an arbitrary
       partner on the far side of the box. Recomputing them every frame is the
       other wrong answer: the drift is supposed to stretch the structure, not
       rewire it. */
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
        const key = i < j ? i + ':' + j : j + ':' + i;
        if (seenPair.has(key)) continue;
        seenPair.add(key);
        PAIRS.push([i, j]);
      }
    }
    /* `position` is a placeholder — BOTH endpoints are placed by u_np in the
       vertex shader, so a conduit follows its cages as they drift. Every
       attribute here is required: a declared-but-absent attribute reads as 0,
       which pins every segment to node 0 and gives it zero length, so the
       lines vanish without a single error anywhere. */
    const cp = [], cat = [], ci = [], cj = [], cs = [];
    PAIRS.forEach(([i, j], seg) => {
      cp.push(0, 0, 0, 0, 0, 0);
      cat.push(0, 1);                // where along the conduit this end is
      ci.push(i, j);                 // this end's cage
      cj.push(j, i);                 // the other end's
      // one seed per SEGMENT (identical on both endpoints, so it survives
      // interpolation) — it de-synchronises the packets. Without it every
      // conduit pulses in lockstep and the field reads as a strobe.
      const sd = ((seg * 9301 + 49297) % 233280) / 233280;
      cs.push(sd, sd);
    });
    const gLink = new TH.BufferGeometry();
    gLink.setAttribute('position', new TH.Float32BufferAttribute(cp, 3));
    gLink.setAttribute('cat', new TH.Float32BufferAttribute(cat, 1));
    gLink.setAttribute('ci', new TH.Float32BufferAttribute(ci, 1));
    gLink.setAttribute('cj', new TH.Float32BufferAttribute(cj, 1));
    gLink.setAttribute('csd', new TH.Float32BufferAttribute(cs, 1));
    const mLink = new TH.LineSegments(gLink, new TH.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false, depthTest: true,
      blending: TH.AdditiveBlending,
      vertexShader: `
        attribute float cat; attribute float ci; attribute float cj;
        attribute float csd;
        varying vec4 vPal; varying float vT; varying float vD; varying float vF;
        varying float vS;
        ${HAZE_V}
        void main(){
          int a = int(ci), b = int(cj);
          vS = csd; vT = cat; vPal = u_pal[a];
          /* IT STOPS ON THE HULL, not at the centre of one. CONDUIT_REACH is
             how far into a hull the reference's tube goes; run it to the centre
             instead and every line crosses its own cage, which is what turns a
             lattice into a scribble. CONDUIT_CLAMP is the floor for two hulls
             close enough that the two insets would cross and invert the
             segment. */
          vec3 pa = u_np[a], pb = u_np[b];
          vec3 dv = pb - pa;
          float L = max(length(dv), 1e-4);
          float inset = min(u_nd[a].w * ${F(CL.CONDUIT_REACH)},
                            L * ${F(CL.CONDUIT_CLAMP)});
          vec4 mv = modelViewMatrix * vec4(pa + dv / L * inset, 1.0);
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
        varying float vS;
        uniform vec3 u_bg; uniform float u_t, u_e, u_pulse, u_dens, u_calm;
        // a packet: a bright head with a short tail behind it, like the
        // particles connections.py runs along its own edges
        float packet(float at, float head){
          float d = at - head;
          float dot_ = pow(max(0.0, 1.0 - abs(d) * 26.0), 2.0);
          float tail = d < 0.0 ? pow(max(0.0, 1.0 + d * 7.0), 3.0) * 0.35 : 0.0;
          return dot_ + tail;
        }
        void main(){
          // DATA TRAVELLING. Always running — this is the graph showing that
          // the conduits carry something — but faster and denser when the
          // workspace is busy, so it still reports rather than decorates.
          float sp = 0.16 + 0.42 * u_e;
          float data = packet(vT, fract(u_t * sp + vS))
                     + packet(vT, fract(u_t * sp * 0.72 + vS + 0.53)) * 0.7;
          // …plus the one-shot surge when you navigate
          float surge = pow(1.0 - abs(fract(u_t * 0.2) - vT), 26.0) * u_pulse;
          /* THE CONDUIT INHERITS THE COLOUR OF WHAT IT CONNECTS, which is the
             brief's own rule. vPal is the chord of the cage at THIS end and
             the fragment interpolates to the other's, so a cyan cluster joined
             to a magenta one is joined by something cyan at one end and
             magenta at the other. */
          vec3 col = chord(vPal, mix(0.12, 0.84, vT), 0.0);
          col = mix(col, vec3(1.0), clamp(data, 0.0, 1.0) * 0.55);
          col = mix(u_bg, col, vF);
          float a = (0.20 + 0.18 * vD + 0.70 * data + 0.55 * surge)
                  * vF * u_dens;
          gl_FragColor = vec4(calm(col, u_bg, u_calm + 0.34), a);
        }`,
    }));
    mLink.frustumCulled = false;
    mLink.renderOrder = 5;
    S.add(mLink);

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
/* COALESCED, because resize() reallocates the canvas backing store and all
   three composer render targets. Dragging a Qt window edge fires this on every
   mouse move, and reallocating a 3-megapixel target sixty times a second is
   the one thing guaranteed to tear the surface it is trying to fit.

   Through MO.frame and NOT requestAnimationFrame: there is exactly one rAF
   chain in this app and a coalescer is not a good enough reason to be the
   second one (tests/test_gui_flicker.py enforces it, and it caught this).
   Returning false retires the job after one pass. It also falls out right for
   a hidden window — MO refuses to reschedule while hidden, so the resize is
   applied when the window comes back rather than into a surface nobody is
   compositing. */
let _rsz = 0;
window.addEventListener('resize', () => {
  if (_rsz) return;
  _rsz = 1;
  MO.frame(() => { _rsz = 0; STAGE.resize(); return false; });
});

window.STAGE = STAGE;
