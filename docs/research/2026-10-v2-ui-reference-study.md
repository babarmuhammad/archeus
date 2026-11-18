# V2 UI Reference Study, 2026-10 — external references and technology evidence

Internal research document (excluded from the published manual: `mkdocs.yml` `exclude_docs:
/research/`). It keeps the **evidence** for the V2 UI research. The decisions, the V1 assessment,
the V2 visual language, the interaction model and the roadmap are in
[../design/ARCHEUS_V2_UI_RESEARCH.md](../design/ARCHEUS_V2_UI_RESEARCH.md), which must be readable
without this file. Where that document cites `E-n`, the entry is here.

Date 2026-10-04. Branch `archeus-v1-rearchitecture` at `cb11480` (R13 passed after its
correction pass). Nothing in the product was changed to produce this. No dependency was added.

**Method.** Four read-only research passes in parallel:

1. the supplied references (huwprosser.com, libraries.dev) read from their live HTML, CSS and JS
   bundles, the GitHub API, raw source and the npm registry;
2. Anime.js, Motion, the platform animation features, three.js and eleven graph libraries, from
   official docs, package source, MDN browser-compat-data 8.1.4 (2026-10-01), and bundles
   **measured** in a scratch project (`esbuild --bundle --minify --format=esm`, then `gzip -9`,
   React external);
3. about thirty real products and open-source projects, from primary docs, changelogs, repos
   and source;
4. research literature on 3D vs 2D graph comprehension and large-graph rendering, via Crossref,
   OpenAlex and Semantic Scholar.

No login was used and nothing was posted. One search result (ampcode.com) carried text addressed
to language models; it was treated as data and ignored.

**Tags.** **[O]** observed in a primary source, in source code, or measured. **[S]** a secondary
write-up. **[I]** inference. Archeus facts are cited by file or document and are **[A]**.

---

## 1. The supplied references

### E-1 huwprosser.com

**Who.** Huw Prosser, "ML Engineer. Tinkerer.", London. His public work is voice and agents: Fury
SDK (2026, "the agent wrapper I wish existed"), Jarvis MLX (local ASR → LLM → TTS), Carter Labs
(AI characters, 2022), and a long-running real-life JARVIS documented on TikTok [O]. The
architecture-level findings about his code are already recorded in
[2026-10-external-research.md](2026-10-external-research.md) §4 and govern V2-A, not this study.

**What the site actually is** [O, from the bundle and CSS]:

- **Svelte 5**, Vite, one 78 KB JS bundle and one 9.6 KB stylesheet. Client-rendered SPA with a
  hand-rolled router.
- **No WebGL, no three.js, no shaders, no GSAP, no animation library.** The only
  `requestAnimationFrame` is Svelte's scheduler.
- **Zero `transition`, `animation` or `@keyframes` in the CSS.** Hover is an instant inversion
  (background to text colour, text to background).
- **Monochrome.** `#111` on `#f5f5f5`; a `prefers-color-scheme: dark` block flips to `#f0f0f0` on
  `#0b0b0b`. No theme toggle.
- **One typeface for everything:** JetBrains Mono. `font-variant-numeric: tabular-nums
  lining-nums`.
- **Hierarchy by weight, not size:** titles 1.4rem, project titles 0.95rem; small uppercase
  labels at 0.68–0.72rem with 0.12–0.18em tracking for dates and tabs.
- **Every structure is a 1 px border in the text colour.** No radius, no shadow, no gradient.
- **Projects are literal HTML tables:** a 6-column row with the title spanning five columns and a
  right-aligned meta cell (year, "Open source").
- Vertical rhythm from `*+*{margin-top:var(--line-height)}`; tables snapped to whole characters
  with `calc(round(down,100%,1ch))` [I: the "Monospace Web" pattern].
- ARIA tabs for Blog / Projects; an `aria-live="polite"` newsletter status.

**Correction to the brief's premise.** The brief asked to study the site's "use of depth, motion,
transitions". The site has **none**. Its identity is made entirely of restraint, typography, a
character grid and copy. That is the finding, and it is a useful one (§E-1 lessons, design doc
§4.1).

**Lessons [I].**
- Distinctiveness without motion: a document that looks like an instrument because every value
  sits in a fixed, right-aligned, tabular column.
- Hierarchy by weight at near-constant size reads dense without shouting.
- One border weight, one radius (zero), one ink: the structure is "felt, not seen".
- Personality from copy — which Archeus deliberately does **not** take (ADR-0027 §5: no
  greeting, no personality text).

### E-2 libraries.dev

Seven React components by Jakub Antalik ("High-crafted UI libraries for AI agents"), each its own
npm package, **all MIT**, **zero runtime `dependencies`**, peer React ≥ 18 (img-fx also peers
three ≥ 0.149). None uses Motion, GSAP or Tailwind; styles are injected CSS strings [O]. The site's
own size claims disagree ("about 83 KB gzipped" for five, "under 110 KB" for seven) [O]. The
home-page previews are looping muted MP4s, not live components [O].

| Package (version) | Rendering | States / API | Reduced motion and a11y | Archeus-relevant constraint |
|---|---|---|---|---|
| **thinking-orbs** 0.3.2 | **plain Canvas 2D**: dots on a Fibonacci sphere, rotated, projected, z-sorted; depth by dot radius and ink only | 9 states: `working` (orbits), `searching` (globe scan), `solving` (rubik), `listening` (wave), `connecting` (web with packets on edges), `weaving` (braid), `composing` (ribbon), `breathing` (ring), `shaping` (morph). The demo relabels `weaving→"planning"`, `breathing→"thinking"`, `connecting→"solving"`. Sizes **64 / 32 / 20, each a separately tuned design, "not a scale factor"** (32 is interpolated and untuned). `theme auto|dark|light`, `paused`, `speed`, `color` (keeps the depth ramp), `gravity` (warps a raster of the cursor) | `prefers-reduced-motion` draws **one static frame**. `role="img"` with a per-state label; **no `role="status"`, no live region**, so a state change is never announced | **each instance runs its own rAF loop**; the animation is **perpetual while visible** (pauses only offscreen or tab-hidden) |
| **border-beam** 1.4.1 | conic-gradient `::after` masked to the border, `::before` glow, a bloom child; **`@property` keyframes** and **`filter: blur()`** (~12 rules), `will-change` | sizes `sm|md|line|pulse-inner|pulse-outside`; colour variants; `active` with fade in/out | built-in reduced motion **only for pulse types**; rotate types "respect prefers-reduced-motion when implemented by the consumer" | animates a paint property under a blur filter |
| **liquid-gooey** 0.2.2 | **SVG filter** silhouette (`feGaussianBlur` + alpha contrast, `feDisplacementMap`) behind live DOM; springs compiled to CSS `linear()` | `<Liquid>` + `<Liquid.Item effect="morph|move|melt|bend">` | reduced motion snaps transitions; content stays real DOM | blur filter layer |
| **voice-glow** 0.2.1 (`VoiceBeam`) | Web Audio `AnalyserNode` (RMS + 3 bands, attack/release); one shared rAF writing CSS vars; band on canvas; warp via SVG `feDisplacementMap` + per-frame `clip-path` | `stream` or `level`, `useMicrophone()` from a user gesture; `processing` turns the glow into a ping-pong beam | reduce zeroes processing, breathing, flow and distortion, **keeps the level response** | filter warp; a "processing" loop |
| **bot-avatars** 0.2.2 | Canvas 2D lit height field | 18 shapes with faces; `default | working | sleeping` | still pose under reduce; `role="img"` | avatars |
| **metal-fx** 2.0.11 | **WebGL2** (vendors Paper Shaders' `liquidMetal`, Apache-2.0); one shared context | `MetalFx`, `MetalText`, `MetalBadge`; presets chromatic/silver/gold | reduce gates **only** the cursor light; no check stopping the shader was found [O by grep, an absence] | WebGL shader as decoration |
| **img-fx** 0.5.1 | **three.js** `WebGLRenderer` + `ShaderMaterial`, 10 fps cap | image-generation loader mosaic | **no reduced-motion handling found** [O by grep] | three.js peer |

**Lessons [I].**
- The orbs' **state vocabulary** is close to Archeus's live vocabulary, and their best idea is
  **per-size tuned figures**, not one figure scaled.
- Their failure modes are exactly Archeus's rejected list: perpetual loops, per-instance rAF, no
  announcement, blur and blend effects, WebGL as ornament.

Sources: <https://huwprosser.com/> (HTML, `/assets/index-*.js`, `/assets/index-*.css`);
<https://libraries.dev/> and `/orbs`, `/beam.html`, `/gooey.html`, `/voice.html`, `/bots.html`,
`/metal.html`, `/image.html`; <https://github.com/Jakubantalik/Libraries.dev> (raw
`packages/*/package.json`, READMEs, `src/**`); `registry.npmjs.org/<pkg>/latest`.

---

## 2. Animation technology

### E-3 Anime.js

| Fact | Detail |
|---|---|
| Version | **4.5.0** (2026-06-22) is npm `latest`; `5.0.0-beta.2` on the `beta` tag with no GitHub release or notes [O] |
| Licence | MIT [O] |
| Modules | `animate`, `createTimeline`, `createTimer`, `createAnimatable`, `stagger`, `spring`, `createDraggable`, `onScroll`, `createScope` (with `mediaQueries`), `createLayout` (4.3), `svg` (`morphTo`, `createDrawable`, `createMotionPath`), `splitText`, `waapi`, `engine`, and since 4.5 a three.js adapter [O] |
| `createSpring` | deprecated in favour of `spring()`; logs a warning [O] |
| Engine | `engine.useDefaultMainLoop` (default true), `pauseOnDocumentHidden` (default true), `update()`, `pause()`, `resume()`, `speed`, `fps`, `precision`; driving it from your own rAF is supported [O] |
| Reduced motion | **none built in** — no `reduce` string in the 4.5.0 source; the documented pattern is a scope with `mediaQueries: { reduceMotion: '(prefers-reduced-motion)' }` and setting `duration: 0` per animation [O] |
| React | `createScope({ root })` in `useEffect`, `revert()` on cleanup; no hooks package [O] |
| 4.4.0 | **breaking**: fixed transform order; `matrix`/`matrix3d` no longer animatable [O] |

**Measured sizes (gzip)** [O]: `animate` 13.3 KB · `animate+createTimeline+stagger` 16.2 KB ·
`waapi` 5.1 KB · `spring` 1.9 KB · `createScope` 2.0 KB · `svg` 2.4 KB · `onScroll` 17.8 KB ·
`createDraggable` 20.9 KB · `createLayout` 22.4 KB · whole library **44.0 KB**.

**Archeus's own history with it [A].** The legacy GUI vendored anime.js **v4.5.0**
(`claude_sessions/web/vendor/anime.esm.min.js`, 118 KB min) as its choreography engine, with
`engine.useDefaultMainLoop = false` so it could not become a second rAF chain (CLAUDE.md,
"Motion is transitional"). The V1 client deliberately ships **no** animation library
(`clients/app/package.json`: runtime deps are `react`, `react-dom`, `qrcode-generator`).

### E-4 Motion (motion.dev)

14.0.0 (2026-10-02), MIT [O]. Measured gzip: `motion/mini` `animate` 3.8 KB; hybrid `animate`
22.1 KB; `motion/react-m` 8.4 KB; `m` + `LazyMotion` + `domAnimation` 29.9 KB; `motion/react`
44.5 KB [O]. **The only option with reduced motion by default:** `<MotionConfig
reducedMotion="user">` disables transform and layout animation and keeps opacity [O]. Vanilla
`animate()` outside React is not gated [I].

### E-5 Platform animation features (MDN BCD 8.1.4; Qt WebEngine 6.11 = Chromium 140)

| Feature | Chrome | Firefox | Safari | Baseline | Qt shell |
|---|---|---|---|---|---|
| WAAPI `element.animate`, `.finished`, `composite` | 84 | 63–80 | 13.1–16 | widely available | yes |
| `linear()` easing (springs as keyframes) | 113 | 112 | 17.2 | **widely available since 2026-06-11** | yes |
| `@starting-style` | 117 | 129 | 17.5 | newly available | yes |
| `transition-behavior: allow-discrete` | 117 | 129 | 17.4 | newly available | yes |
| View Transitions, same-document | 111 | **144** | 18 | **newly available since 2025-10-14** | yes |
| View Transitions, cross-document | 126 | no | 18.2 | no | yes |
| Scroll-driven animations | 115 | Nightly only | 26 | **no** | yes |
| `interpolate-size` / `calc-size()` | 129 | no | no | no | yes |

All [O]. None of them honours reduced motion by itself; each needs an
`@media (prefers-reduced-motion: reduce)` rule [I]. WAAPI and CSS animations of `transform` and
`opacity` run on the compositor; a JS-ticked library animates on the main thread except in its
WAAPI mode [I].

---

## 3. 3D and graph technology

### E-6 three.js

- **r186** (npm 0.186.1, 2026-09-24), MIT [O].
- **WebGPURenderer is still experimental** per the r186 manual; it falls back to a WebGL 2
  backend; it does not support `ShaderMaterial`, `onBeforeCompile` or `EffectComposer` [O].
- WebGPU availability: Chrome/Edge 144 desktop, Chrome Android 121, Safari 26, Firefox 141
  (Windows only, partial). Not Baseline. **No Qt WebEngine documentation on WebGPU was found;
  assume WebGL 2 in the Qt shell** [O / I].
- **Measured gzip:** minimal WebGL scene **133 KB**; with InstancedMesh, Raycaster and
  LineSegments 135 KB; whole `three` 191 KB; minimal `three/webgpu` **219 KB** [O].
- `InstancedMesh` and `BatchedMesh` cut draw calls; `Raycaster` "might be slow" on many
  triangles; GPU picking needs a 1×1 readback [O].
- `LineBasicMaterial.linewidth` is ignored (always 1 px); thick lines need `Line2` [O].
- Labels: `CSS2DRenderer` repositions one DOM element per label per frame [O]; troika SDF text
  ~45 KB gzip [O].
- Accessibility: a canvas is opaque to assistive technology; `@react-three/a11y` 3.0.0 last
  published 2022-05 [O]; the research toolkit **Data Navigator** (MIT; Elavsky, Nadolskis &
  Moritz, IEEE TVCG 2023, doi:10.1109/TVCG.2023.3327393) builds keyboard and screen-reader
  structures over a raster [O].

**Archeus's own history with it [A].** The legacy GUI ran a three.js background stage
(`claude_sessions/web/stage.js`, 141 KB, plus vendored `three.module.min.js` 365 KB min and
postprocessing passes). Its record, from CLAUDE.md Gotchas and `notes/qt-flicker.md`:

- the stage's first cut "was judged overstimulating", and both users switched to the one skin
  with no background;
- a lit cluster (353,566 triangles, 33 blended draw calls) collapsed the page's frame delivery in
  fullscreen in the Qt shell: rAF p95 **249.9 ms**, 138 frames in 8 s; the flat version (24,494
  triangles) held 60 Hz;
- a real Qt/ANGLE compositing bug exists separately (Windows + Qt 6), and `--use-angle=gl`
  breaks WebGL outright on Intel UHD;
- `backdrop-filter`, `filter:blur` and `mix-blend-mode` tear the Qt GPU surface;
- headless probes of the Qt window measured a parked page for two sessions.

V1 carried none of it (ADR-0016) and named a post-V1 phase **V1.x-3D** for "the lineage of the
flat graph scene" (ADR-0030; rulebook §26 R20).

### E-7 Graph libraries

| Library (version) | Renderer | Scale claim / evidence | Keyboard / AT | gzip | Licence |
|---|---|---|---|---|---|
| **sigma 3.0.3** + graphology 0.26 | WebGL nodes/edges, Canvas 2D labels | "thousands of nodes and edges"; v4 in beta | **none** | **38 KB** | MIT |
| @cosmos.gl/graph 3.4.2 | WebGL2, GPU layout | "hundreds of thousands of points"; needs `OES_texture_float` (fails on some Android) | minimal | 193 KB | MIT (the `@cosmograph/*` packages are **CC-BY-NC-4.0**) |
| force-graph 1.52 / react-force-graph-2d | Canvas 2D | `autoPauseRedraw` once settled | none | 61 KB | MIT |
| 3d-force-graph 1.80 | three.js | — | none | 417 KB | MIT |
| reagraph 4.32 | WebGL via three + R3F + drei (bundled) | edge bundling, clustering | context menu only | **480 KB** | Apache-2.0 |
| cytoscape 3.34.3 | Canvas 2D; WebGL preview since 3.31 | ~1,200 nodes / 16,000 edges: ~20 fps canvas vs > 100 fps WebGL (project blog) | none | 143 KB | MIT |
| @antv/g6 5.1.1 | Canvas by default | WebGPU/WASM layout claims | shortcut keys, no ARIA | 440 KB | MIT |
| ELK.js 0.12.0 | layout only (worker) | layered DAGs | n/a | 433 KB | **EPL-2.0 OR GPL-3.0** |
| d3-force 3.0.0 | layout only | Barnes–Hut | n/a | **5.3 KB** | ISC |
| @dagrejs/dagre 3.1.1 | layout only | layered | n/a | 17 KB | MIT |
| d3-dag 1.2.2 | layout only | 184 nodes in 5.1 ms ("fast") | n/a | 42 KB | MIT |

All [O]. **No mainstream graph library ships keyboard or screen-reader navigation** [I from the
scans]; every one needs the parallel DOM that Archeus's graph mirror already is.

### E-8 3D vs 2D graph comprehension (research)

- **Munzner**, *Visualization Analysis and Design* (2014), ch. 6 "Rules of Thumb": "No
  Unjustified 3D" [O chapter; wording from memory, I].
- **Ware & Franck 1996** (ACM TOG, doi:10.1145/234972.234975): head-coupled stereo let people
  understand graphs 3× larger; stereo alone 1.6×, head-coupling alone 2.2× — **motion mattered
  more than stereo** [O].
- **Ware & Mitchell 2008** (ACM TAP, doi:10.1145/1279640.1279642): stereo **plus** motion on a
  high-resolution display reached an order of magnitude over 2D for path tracing [O]. Needs
  stereo and motion; a mono canvas on a laptop or phone has neither [I].
- **Kwon et al. 2016** (IEEE TVCG, doi:10.1109/TVCG.2016.2520921): immersive HMD faster than 2D;
  correctness not significantly different overall [O].
- **Kotlarek et al. 2020** (PacificVis, doi:10.1109/pacificvis48177.2020.4722): immersive better
  for structure in larger networks; **2D better for spatial-memory tasks** [O].
- **Cockburn & McKenzie 2002** (CHI, doi:10.1145/503376.503413): performance **worsened** as
  freedom to use depth increased; 3D felt "more cluttered" [O].
- **Yoghourdjian et al. 2021** (IEEE TVCG, doi:10.1109/tvcg.2020.3030459): significant
  difficulty finding shortest paths in dense node-link diagrams **above 50 nodes**, and in sparse
  ones above **100**; hairballs need aggregation or filtering [O].
- **Ghoniem, Fekete & Castagliola 2004/05** (doi:10.1109/infvis.2004.1): above ~20 vertices,
  matrices beat node-link on most tasks except path finding [O].
- Greffard et al. 2011 (doi:10.1007/978-3-642-25878-7_21): abstract not retrieved; not relied on.

### E-9 Rendering thresholds and large-graph techniques

- **Horak, Kister & Dachselt 2018** (IEEE VIS poster): all technologies lost frame rate above
  ~400 nodes (~8,000 graphical elements); SVG ≈ Canvas; WebGL degraded least; **text was WebGL's
  bottleneck** → WebGL shapes + Canvas text, LOD, worker tiles [O].
- Cytoscape's WebGL preview numbers (E-7) [O].
- Zhao et al. 2025 (VCIBA, doi:10.1186/s42492-025-00193-y): library benchmarks 100–200k nodes;
  abstract only [O].
- Semantic zoom: Hornbæk et al. 2002 (doi:10.1145/586081.586086) — 80 % preferred an overview,
  yet good semantic zoom levels sometimes made it unnecessary, and switching overview/detail
  costs time [O].
- Focus+context: Furnas 1986 (doi:10.1145/22339.22342); Sarkar & Brown 1992
  (doi:10.1145/142750.142763); survey Cockburn, Karlson & Bederson 2009
  (doi:10.1145/1456650.1456652) [O].
- Edge bundling: Holten 2006 (hierarchical, doi:10.1109/TVCG.2006.147); Holten & van Wijk 2009
  (force-directed); survey Lhuillier, Hurter & Telea 2017 (doi:10.1111/cgf.13213) [O].

**Practical rule [I].** Canvas 2D holds ~1–2k nodes and a few thousand edges with batched paths,
viewport culling, render on demand, capped DPR and hidden labels while moving — which is exactly
the V1 renderer's design (`graph/render.ts`: static layer, LOD above 250 nodes, DPR ≤ 2, parking
loop) [A]. WebGL 2D becomes worth it past ~5–10k edges, continuous layout, or fullscreen at high
DPR on an integrated GPU.

---

## 4. Product references

Each entry: what it does well → what Archeus can learn → what not to copy. Detailed sourcing is
per entry; everything is [O] from the listed primary source unless marked.

### 4.1 AI agent interfaces

**E-10 Claude Code desktop: Projects Overview** (code.claude.com/docs/en/claude-projects,
/desktop).
- *Does well:* groups threads **by what you owe them** — *Ready for review*, *Waiting on you*
  (reply, approval or failed), *Working*, *Landing* (PR approved or queued to merge), *Idle*,
  *Resolved* (by you, by Claude after your last step, or automatically after a week idle).
  Notifications are narrow by default (posts, errors, needs input; "finished a turn" is opt-in).
  Stop replaces Send while a thread works. Scope spill-over becomes a **task chip** that starts a
  new session. Some confirmations hold "in every permission mode, including Auto and Bypass".
  Messages from another session arrive as a labelled card with a link back.
- *Learn:* obligation grouping; a *landing* step between accepted and done; out-of-scope findings
  as a "propose a mission" action; some policy floors that no autonomy level removes (Archeus
  already has locked floors, ADR-0007).
- *Not:* coordination preferences are soft instructions, "not enforced settings". Archeus policy
  stays enforced.

**E-11 OpenAI Codex app.** The Scheduled view "acts as your inbox"; runs with nothing to report
are archived automatically [O]; a task sidebar (plan, sources, artifacts, summary) for returning
after a break [S]. *Learn:* silence when there is nothing to say; a per-mission "while you were
away" summary separate from the conversation. *Not:* scheduled runs inherit sandbox settings
silently — show the effective policy when a schedule is made.

**E-12 Cursor 3 Agents Window and Plan Mode.** One sidebar for agents started from desktop,
mobile, web, Slack, GitHub, Linear; cloud agents attach demos and screenshots; Plan Mode writes an
editable markdown plan and **Build** is the approval. *Learn:* origin badge on every mission;
review needs evidence, not only a diff; plan editing then one approve verb (Archeus already has
B4 plan edit). *Not:* two parallel surfaces (IDE and Agents Window) the user switches between.

**E-13 GitHub Copilot coding agent.** Agents panel on every page; session log with tool use and
token use; "Stop session" ends the run "and preserves any commits already pushed"; **steering is
queued** — applied "after it finishes its current tool call"; commits link to the session log.
*Learn:* say what Stop keeps (Archeus's stop copy already does); say where a steer lands; link
each produced artifact to the moment that produced it. *Not:* steering cost not shown before
sending.

**E-14 Linear for Agents (Agent Interaction API).** Six session states (`pending`, `active`,
`error`, `awaitingInput`, `complete`, `stale`) **derived from the agent's last activity**; five
activity types (`thought`, `action`, `elicitation`, `response`, `error`); **ephemeral
activities** replaced by the next one, giving a "currently doing X" line without log spam; plan
steps `pending|inProgress|completed|canceled`; an agent must acknowledge within **10 s** or is
marked unresponsive. *Learn:* the ephemeral current-action line (= Archeus A-17, owned by P21); a
**liveness rule** that turns a silent execution into an explicit state instead of an endless
"running". *Not:* plan updates replace the whole array, losing history — Archeus versions plans.

**E-15 Devin.** Interactive planning: waits for approval when unsure, otherwise **proceeds after
30 s** unless told to wait; plan items cite code; a Progress tab lists commands, edits and
browser actions. *Learn:* plan items cite evidence; the approval card says *why* it asks.
*Not:* **a timer that turns silence into consent** — Archeus approvals expire into nothing, never
into action.

**E-16 Warp agent notifications.** Classes Complete / Request / Error; a toast, a **Mailbox**
(All / Unread / Errors), per-tab icons. Users report (issues #10242, #9142, #9868) that badges
are not prominent enough to see what needs attention across many agents. *Learn:* a needs-you
state needs **position and area**, not only a small icon. *Not:* status carried by a 10 px icon
alone.

**E-17 Zed agent panel.** "Follow the agent" (editor follows each file touched), per-hunk accept
or reject, Restore Checkpoint per user message, notify when waiting. *Learn:* follow as an
**opt-in** mode; checkpoint per human turn. *Not:* follow by default.

**E-18 Vibe Kanban, Conductor, Amp.** Kanban To Do → In Progress → Review → Done where dragging a
card starts an agent (Vibe Kanban); per-task workspace then merge and **archive** (Conductor: "The
actual value is the review interface"). Vibe Kanban's company shut down 2026-04-10; the local core
survives, cloud services were removed; open issues ask for remote/headless notifications [O]. Amp
subagents cannot take mid-task guidance [O]. *Learn:* local-first survives; archive is a real end
state; notifications for a local server reached remotely is the hard problem (Archeus P20).
*Not:* **drag as command** (a drop spends quota) and a kanban as home.

### 4.2 Orchestration and workflow

**E-19 Temporal Web UI.** Three views of one history — *Compact* (order only; concurrent groups
stack; repeats collapse with a count), *Timeline* (clock durations), *Full History*. "Red means
failure, **dashed** red means retrying, dashed purple is pending, green means completion";
pending lines animate, completed are static. *Learn:* **line style says "not final yet"** and
reads without colour; compact order-only history as the default. *Not:* full history as default.

**E-20 Airflow Grid view.** Runs as columns, tasks as rows; replaced the Tree view because trees
"can only branch forward". *Learn:* a run matrix for recurring automations (a flaky step shows as
a stripe). *Not:* ~10 state hues.

**E-21 Dagster asset health.** One health per asset (Unknown / Healthy / Warning / Degraded),
"the most elevated status" of its inputs; **a failure with an automatic retry pending is Warning,
not Degraded**. *Learn:* one rolled-up health per resource with its reasons; **self-healing looks
different from needs-a-human**. *Not:* global lineage as landing page.

**E-22 Inngest traces.** Timeline left, step detail right; **each span splits its time into
queue delay, processing, your code and flow-control waits**; LLM steps show model, tokens,
latency. *Learn:* split an execution's time into working / waiting for capacity / waiting on you.
*Not:* deep span nesting by default.

**E-23 GitHub Actions run graph.** Jobs as nodes with status icons, live. *Learn:* draw a plan as
a DAG only when it has real dependencies; otherwise a list.

### 4.3 Observability

**E-24 Honeycomb.** Trace waterfall with collapse by depth and "Highlight errors". The Service
Map post: early versions were "a tangle of spaghetti"; the fix made the map **a jumping-off point
for queries**, with label zoom thresholds tuned on real customer graphs. *Learn:* a graph earns
its place as a query launcher; tune on real project graphs, not fixtures. *Not:* a map you look at
"once … and then never again".

**E-25 Sentry.** One status at a time (New / Ongoing / Escalating / **Regressed** / Archived /
Resolved); archive **until a condition** ("until escalating" by default). *Learn:* snooze with a
wake condition; a regressed state for done work that broke later. *Not:* volume forecasting.

**E-26 Vercel Geist StatusDot.** Written rules: the dot animates only while BUILDING or QUEUED and
is static at a terminal state, with no separate spinner; "Don't flash the color through every
transitional state on a polling tick"; pair the dot with relative time because "the dot alone
doesn't convey duration"; the dot is reserved for one lifecycle and other statuses use a badge.
*Learn:* one indicator per vocabulary; re-render only on a real change; always show elapsed time.
*Not:* the loop itself — see the design doc §5.3 for why Archeus keeps evidence-driven motion.

### 4.4 Command centres

**E-27 Linear.** Triage keys `1` accept, `2` decline, `3` duplicate, `H` snooze (returns at a time
**or on new activity**); Priority Inbox (2026-09-03); the March 2026 refresh: "Don't compete for
attention you haven't earned", "Structure should be felt not seen", dimmer navigation, fewer and
smaller icons. *Learn:* single-key verdicts; snooze that wakes on activity; navigation recedes
once you arrive. *Not:* two queues with different semantics.

**E-28 Raycast.** Enter = first action, Cmd+Enter = second, Cmd+K = all actions grouped with each
row's shortcut shown, so users graduate to direct keys. *Learn:* primary / secondary / everything,
with shortcuts printed. *Not:* launcher-as-root on a phone.

**E-29 Superhuman [S], Things 3.** Cmd+K teaches shortcuts; Things' drag-to-place on a phone.
*Learn:* the palette is a teaching surface. *Not:* gesture as the only path.

### 4.5 Graph and spatial

**E-30 Obsidian graph view.** Forum criticism (thread 71316): "never found it helpful",
"chaotic patterns have no meaning, time changes are uncontrollable and cannot be remembered".
Defenders use the **local graph**, filters and saved queries. *Learn:* ego graph by default,
stable layout, saved views. *Not:* a global force-directed hairball.

**E-31 Nx, Backstage.** Nx `--focus` and `--affected`; its docs call the full graph
"unmanageable even for smaller repositories". Backstage puts a **direct-relations card** on every
entity page with depth (1 or infinite) and kind filters. *Learn:* relations mostly as a small
card on detail pages; "affected" as the most useful overlay (Archeus built "What does this
affect?"). *Not:* infinite depth by default.

**E-32 Heptabase, tldraw.** Heptabase keeps a card library and spatial whiteboards in sync;
tldraw's agent kit gives the agent structured shape data, not just pixels. *Learn:* if a spatial
view is ever arranged by hand, the list stays the truth. *Not:* an infinite canvas as navigation.

### 4.6 Mission control

**E-33 NASA Open MCT** (Apache-2.0, v4.3.1 2026-08-31). Time Conductor with fixed vs real-time
modes; Fault Management rows show severity, name, **value when tripped vs current value**,
trigger time; **Acknowledge** and **Shelve** are separate; v4.3.1 raises the operator-status
indicator's priority. *Learn:* attention rows say "then vs now"; acknowledge ≠ resolve; label a
snapshot like a fixed-time conductor. *Not:* user-composable layouts.

**E-34 Dark cockpit, Crew Dragon, ATC research.** Dark cockpit: correctly configured systems show
no lights; any light is abnormal. Crew Dragon: critical commands on physical buttons that work if
the display fails [S, press]. FAA/NASA research: alarms noticed faster with a notification window
and red background than with red text alone (rosap.ntl.bts.gov/view/dot/71713). *Learn:* Archeus's
"dark and still until it acts" is the dark-cockpit rule; an e-stop outside the main UI (the tray)
is right; a needs-you state changes an **area**. *Not:* sci-fi HUD styling.

### 4.7 Mobile triage

**E-35 Claude Code Remote Control and Dispatch.** Two push toggles ("actions required", "Claude
decides"); machine online dot; trusted-device enrolment; Dispatch approvals expire after 30 min.
*Learn:* push on one deterministic class plus opt-ins; short-lived phone approvals. *Not:* pushing
when the model "decides".

**E-36 GitHub Mobile, Linear Mobile.** Inbox filters, "Done" as the core verb, swipe to done or
save; Linear's customisable bottom bar and Priority inbox. *Learn:* the phone triages, approves,
steers and reads. *Not:* authoring a plan on a phone.

### 4.8 Identity and TUI

**E-37 lazygit, k9s, btop, Textual, Charm Crush.** lazygit numbers its panes, `?` shows keys for
the current context, undo/redo via reflog with stated limits; k9s `:` commands (`:pulses`
dashboard, `:xray` relation tree) and a `default` colour that keeps the terminal's background;
btop: "all buttons with a highlighted key are clickable"; Textual has a `ctrl+p` palette and
`textual serve`; Crush is the closest agent-TUI peer (bubbletea/lipgloss). *Learn:* the
highlighted letter is both hint and hotkey; respect the terminal palette; a relation tree inside a
TUI. *Not:* cluster-wide density on a home view.

### 4.9 Motion and attention principles

- **Calm technology** (Weiser & Brown 1995; Amber Case): move "from the periphery of our
  attention, to the center, and back"; "smallest possible amount of attention"; "work even when
  it fails".
- **Apple HIG Motion:** "Don't add motion for the sake of adding motion"; motion never the only
  carrier; "avoid adding motion to UI interactions that occur frequently"; "let people cancel
  motion".
- **Material 3 Expressive:** springs; *standard* scheme with "minimal bounce … for utilitarian
  products"; **effects springs (colour, opacity) never overshoot**.
- **IBM Carbon:** *productive* motion for task moments, *expressive* "for significant moments …
  or when the movement itself conveys a meaning"; durations 70 / 110 / 150 / 240 / 400 / 700 ms;
  "ideally unnoticed".
- **Fluent 2:** functional, short, no distracting motion outside the focused element.

---

## 5. Evidence gaps

- huwprosser.com's blog posts are client-rendered; their text was read from the bundle's JSON.
- libraries.dev's Accessibility page is JS-rendered and was not read separately; the orbs' a11y
  facts come from source.
- metal-fx and img-fx "no reduced-motion handling" are absences found by grep and may miss a
  file not fetched.
- Greffard 2011 and Zhao 2025 were not read in full and are not relied on.
- WebGPU inside Qt WebEngine is undocumented; treated as unavailable.
- Not covered: Factory, Sculptor, Datadog, Grafana, Kumu, Neo4j Bloom, Excalidraw, FigJam, Miro,
  Logseq, Sourcegraph, Gource, Arc/Dia, Height, Notion Mail, Slack mobile, Ghostty. This is "not
  looked at", not "lacks anything".
- The libraries.dev npm download figure for thinking-orbs (2.39 M/month) is implausible for an
  organic count and is not relied on.
- No V2 claim here was measured on Archeus's own hardware; the owed V1 measurements (60 fps at
  1,000 nodes on integrated graphics, a physical phone) remain owed (R13 §6).

---

## 6. Visual-impact addendum (2026-10-04)

This section holds the evidence for
[../design/ARCHEUS_V2_VISUAL_DIRECTION.md](../design/ARCHEUS_V2_VISUAL_DIRECTION.md), the addendum
on visual impact.

**Method.** Four more read-only passes ran in parallel:

1. depth, materials and motion systems;
2. "awe" in technical products;
3. living interfaces, ambient displays and fatigue;
4. visual-effect technology.

Sizes are **measured** unless marked BP: unpkg files, or `esbuild --minify --format=esm` with
React external, then `gzip -9`. BP means the bundlephobia API. The `opencli` search adapters were
unavailable because the browser bridge was not connected, so the passes used native search, Jina
Reader, the GitHub API, the HN Algolia API and `pdftotext` on downloaded papers. No login was
used, nothing was posted, and no fetched page carried instructions.

**One correction made during the pass.** A summarising fetch reported that Bartram et al. 2003
found blinking the *most* distracting motion. The paper's own text says the opposite (E-49).
Every Bartram figure below comes from the extracted PDF.

### 6.1 Archeus's own record

**E-38 The legacy GUI already built the spectacular version, and its users judged it [A].**
Sources: `CLAUDE.md` gotchas (the stage, worlds, skins, the cluster, flicker), DR §6–7, rulebook
§2.6.

| What was built | Judgement (the user's words where recorded) | What survived |
|---|---|---|
| A full-viewport WebGL stage, one three.js scene per skin, bloom on by default | "overstimulating, confonde"; both users switched to the one skin with no background | A luminance ceiling (`u_calm` ≤ ~0.45), idle at 12 fps × 0.12 time, bloom opt-in, `lite` as the default. V1 then dropped the mechanism and kept the principle "one surface behind, driven by state" (ADR-0016) |
| 26 generative canvases (rain, embers, petals, dust) in ~30 places | Deleted for "smearing motion through the content" | Nothing |
| Background motion at 16 % opacity behind opaque cards | Invisible, so useless | Motion moved to the foreground, each element bound to its own data feed |
| Loud mixable skins (Sakura, Mecha, Glass, Neon city) | "da buttare" | The lesson that "Terminal won because its transformation is in the chrome and its background is quiet. **Drama belongs in the interface, not the wallpaper.**" |
| A lit 3D PBR cluster (353,566 triangles, 33 draw calls, ACES, PMREM) | "i don't like this theme … everything else is worse"; "keep the complications of the cluster … just remove the 3d part" | The same parts drawn flat and additive: 24,494 triangles in 19 draw calls |
| Zen mode raising brightness and gain | "theme on vs theme off have different brightness … i like the one where i am only viewing the theme" | The rule that a display mode may not change the stage |
| Particle bursts on launch | Kept only as one-shot effects of ≤ ~1.6 s: "petals falling forever is the ambient wallpaper … petals bursting once when a session launches is feedback" | V1 dropped bursts along with skins |
| The lit cluster in the Qt shell at full screen | rAF p95 **249.9 ms**, 138 frames in 8 s: the whole app lurched between 60 and ~17 Hz | The flat scene: p95 16.8 ms, 480 frames |

**What this record shows [I].** The same product, with the same users, made four separate attempts
at visual spectacle. All four failed for the same reason: the intensity was tied to nothing the
user needed. Two things survived every time:

- **light that reported real state**;
- **drama placed in the chrome rather than behind it**.

No external reference in this study bears on the question as directly as this record.

### 6.2 Depth, materials and motion systems

**E-39 visionOS HIG [O].**
- **Materials:**
  - Window glass is a system material that "limits the range of background color information"
    so contrast holds.
  - Thickness carries meaning: thin for interactive or selected elements, regular for sections,
    thick for a distinct dark element on top.
  - Vibrancy has three text levels and "pulls light and color forward".
- **Depth:**
  - Depth comes from "color temperature, reflections, and shadow".
  - Apple recommends "small amounts of depth throughout your interface — even in standard
    windows".
  - A sheet makes the window behind it "recede along the z-axis".
  - No depth on text or small symbols; each change of depth costs the eye a refocus.
  - Ornaments sit "slightly in front", on a parallel plane.
- **Hover:** three delay classes (none, short, long). Custom hover effects are for "special
  moments"; too many "dilute the impact".
- **Motion:**
  - nothing in the peripheral field;
  - fade before relocating anything;
  - keep a stationary frame of reference;
  - **avoid sustained oscillation near 0.2 Hz**.

Source: developer.apple.com/design/human-interface-guidelines/ — the pages materials,
spatial-layout, ornaments, eyes and motion.

**E-40 Liquid Glass (WWDC25) and the critique of it [O/S].**
- **Apple's stated principles:**
  - Controls form "a distinct functional layer that sits above apps", with shapes concentric to
    the window corners.
  - The glass "bends, shapes, and concentrates light". Elements "materialize" by modulating that
    bending rather than by fading.
  - Shadow opacity adapts to what lies beneath; the glass "illuminates from within" on touch.
  - Never glass on glass; content stays in the content layer; use it "sparingly".
- **Accessibility settings:** Reduce Transparency makes the glass frostier. Increase Contrast
  makes it black or white with a border. Reduce Motion removes the elastic behaviour.
- **Sources:** WWDC25 session 219; HIG Materials; Apple Newsroom, June 2025.
- **iOS 26.1 added a Clear/Tinted switch:** "Tinted increases opacity and adds more contrast"
  (9to5mac, 2025-10-20).
- **NN/g, "Liquid Glass Is Cracked" (2025-10-10):**
  - low contrast, including "text on top of text";
  - "motion without meaning";
  - smaller, more crowded targets;
  - controls that appear and vanish;
  - verdict: "prioritizing spectacle over usability".
- **Portable without blur:** a distinct control layer, concentric radii, a shadow that adapts, an
  inner light on press.
- **Not portable:** lensing and refraction. Both need backdrop sampling, which is the GPU readback
  the Qt shell cannot afford.

**E-41 Fluent 2 / Windows 11 [O].**
- **Mica:** opaque, for long-lived window backdrops; it "only samples the desktop wallpaper
  once".
- **Acrylic:** "used only for transient, light-dismiss surfaces"; it is "GPU-intensive", and
  Battery Saver turns it off.
- **Smoke:** a black dim under modals.
- **Layering:**
  - A base layer plus a content layer filled with a low-opacity solid.
  - Elevation values run from 128 (window, dialog) down to 1 (layer), each with a 1 px stroke.
  - Sharp shadows read as near and large soft ones as far. Windows "uses strokes instead of key
    shadows".
  - In the dark theme the shadow tokens double their opacity: ambient .24, key .28.
- **Motion:**
  - durations from 50 to 500 ms; WinUI controls use 83, 167 and 250 ms;
  - `decelerateMax` is `(0.1,0.9,0.2,1)`;
  - top-level navigation is "a quick fade".

Sources: learn.microsoft.com (the mica, acrylic, layering, and timing-and-easing pages);
fluent2.microsoft.design (material, elevation, motion); microsoft/fluentui `packages/tokens`.

**E-42 Material dark elevation, M3 Expressive springs, Carbon's two modes [O].**
- **Material 2, dark theme:**
  - "Higher elevation, lighter surface": a white overlay from 0 to 16 % across 0–24 dp.
  - Use dark grey rather than black, because shadows read on grey.
- **Material 3:** separates surfaces by tonal difference by default; levels +4 and +5 are for
  hover and drag.
- **M3 Expressive (2025):**
  - *Spatial* springs may overshoot; *effects* springs (colour, opacity) never do. Each comes in
    fast, default and slow.
  - The *standard* scheme has "minimal bounce … for utilitarian products"; the *expressive*
    scheme is for "hero moments".
  - Published web approximations: standard spatial `cubic-bezier(.27,1.06,.18,1)` at
    350/500/750 ms; effects at 150/200/300 ms.
- **Container transform:** the container persists while its size, position and shape animate;
  the content is pinned to its top edge and cross-faded.
- **Carbon:**
  - *Productive* motion is "efficient… subtle"; *expressive* motion is for "occasional, important
    moments".
  - Durations from 70 to 700 ms.
  - "If [motion] is frequently noticed by average users… consider removing" it.

Sources: m3.material.io (motion, elevation); m2.material.io (dark theme, motion system);
carbondesignsystem.com/elements/motion.

**E-43 Live Activities / Dynamic Island [O].** Source: HIG Live Activities, updated 2025-12.
- **Presentations:** minimal, compact and expanded. The expanded one must "maintain the relative
  placement of elements".
- **Animation:** capped at **2 s**. Elements that move animate to their new positions; the rest
  fade.
- **Restraint:**
  - "Update … only when new content is available. If the underlying content or status remains
    the same, maintain the same display."
  - "Alert people only for essential updates."
  - End immediately when the task ends; at most 8 h live, and at most 4 h on the Lock Screen
    afterwards.
  - The minimal presentation shows live data, not a logo.

### 6.3 Living state, ambient display, fatigue and trust

**E-44 AI state indicators [O/S].**
- **Gemini Live:** a waveform pill that grows "when users speak louder or for longer" — driven by
  real signal (androidauthority; 9to5google, 2026-01).
- **Siri on iOS 18:** an edge glow that "adapts in response to the sound of your voice". Its
  entry edge encodes how Siri was invoked (9to5mac 2024-11, headline: "looks different, works
  the same").
- **ChatGPT voice orb:**
  - whether it follows audio amplitude is unverified;
  - in Nov 2025 voice moved inline and the full-screen orb stopped being the main surface
    (TechCrunch 2025-11-25);
  - a community thread asks to customise the orb for "the long-term experience".
- **Claude Code spinner verbs:** 187 verbs, picked at random.
  - Issue #33057: they "don't reflect what Claude is actually doing … you look at the spinner
    expecting to understand the current state, but get a meaningless word".
  - Issue #21893 asks for plain "Busy".
- **Shimmer text** (Cursor, v0, shadcn) is a canned loop. Jim Nielsen (2026): shimmer "implies a
  kind of 'thinking' but is being repurposed to indicate any kind of asynchronous task".
- **Perplexity Pro Search:** "users were more willing to wait for results if the product would
  display the intermediate progress" (LangChain case study).

**E-45 OS status grammars [O].**
- **Windows taskbar progress** (`ITaskbarList3::SetProgressState`):
  - green for normal, yellow for paused, red for error; indeterminate "cycles";
  - when several sources report, the button shows **ERROR > PAUSED > NORMAL > INDETERMINATE**.
- **`FlashWindowEx`:** flashes `uCount` times, or until the window comes to the foreground.
- **macOS:**
  - `NSInformationalRequest` makes the dock icon bounce **once, for one second**;
    `NSCriticalRequest` bounces until the app is activated;
  - the privacy indicators are static dots, one at a time.
- **Nothing Glyph Progress:** LEDs show real progress (Uber, Maps), and a timer drains.

**E-46 Ableton Live clip launch [O].** A clip button blinks while the clip is *queued*, waiting for
the next quantisation boundary. The Live Object Model states it directly:
`is_triggered: 1 = Clip Launch button is blinking`. Here motion means "committed, waiting for a
known boundary" — the nearest analogue to "approved, about to run".

**E-47 Figma multiplayer and htop [O].**
- **Figma:** designers at first "hated the idea" of live cursors and feared "hovering art
  directors". Live state can read as surveillance.
- **htop:** the only motion is the data changing, at a user-set interval of 0.1–10 s.

**E-48 Calm technology and ambient displays [O].**
- **Live Wire (Weiser & Brown 1995):** Jeremijenko's string twitches a motor for every Ethernet
  packet: "a very busy network causes a madly whirling string … a quiet network causes only a
  small twitch every few seconds". The motion is proportional to real signal; that is the whole
  design.
- **Ambient Orb (2002):** one data stream mapped to colour.
- **Mankoff et al., CHI 2003 — heuristics for ambient displays:**
  - sufficient information design;
  - consistent and intuitive mapping;
  - **visibility of state** ("transition from one state to another should be easily
    perceptible");
  - aesthetic and pleasing design;
  - useful and relevant information;
  - easy transition to more in-depth information;
  - **peripherality** ("unobtrusive and remain so unless it requires the user's attention");
  - error prevention;
  - flexibility.

  Three to five evaluators found 40–60 % of the known issues.

**E-49 Bartram, Ware & Calvert 2003, "Moticons" (IJHCS 58(5)) [O].**
- **Detection:** missed peripheral colour cues rose from 6 % to 25 %; missed motion cues stayed
  under 2 % in both near and far fields. Motion was detected in about 1 s, colour in 2.3 s or
  more.
- **Slow blink:** still detected 89 % of the time within 10 s.
- **Distraction:**
  - The *type* of motion dominated (F(7,84)=86.89, p<.0001).
  - From least to most distracting: **blink, linear, zoom, travelling**.
  - Travelling motion was "by far the most distracting"; zoom came next, for its "sudden
    perceptual onset".
- **The authors' recommendation:** "slow linear motion would appear to be a good compromise".
- **Persistence:** ratings rose somewhat when cues persisted longer, but not significantly.
- **Cited in the paper:** in Maglio & Campbell 2000, continuous scrolling banners were
  "substantially more distracting with no increased benefit in awareness".

**E-50 Repetition and habituation [O].**
- **NN/g:**
  - "The more frequent the animation, the more subtle and shorter"; most should run 100–500 ms.
  - Testers routinely say "this [animation] was nice the first time, but now it's getting
    annoying".
  - Overused peripheral motion produces banner blindness, replicated from 1997 to 2018.
- **Alarm fatigue:**
  - Joint Commission SEA 50 (2013): "**85 to 99 percent** of alarm signals do not require
    clinical intervention".
  - 98 alarm-related events in 2009–2012, of which 80 were deaths.
  - ECRI ranked alarm hazards first four years running, to 2015.
- **Anderson, Vance, Kirwan et al. (fMRI):**
  - Visual-cortex response shows a "dramatic drop" **after the second exposure** to the same
    warning.
  - **Polymorphic warnings**, whose appearance changes, were "substantially more resistant to
    habituation" over a 5-day study.
- **Gap:** no controlled study was found of products that reduce animation intensity with use.
  The shipped precedents are severity-scaled persistence (E-45) and Live Activities' "alert only
  for essential updates" (E-43).

**E-51 The cost and accessibility of continuous motion [O].**
- **VS Code #22900 (2017):**
  - **13 % CPU** while idle and focused, caused by the blinking cursor.
  - "A native animation updates at 60hz in Chromium", even for a two-state blink.
  - A solid cursor brought it to about 0.
- **Chromium throttling** applies to hidden pages, not to a visible unfocused window. This
  matches the repo's own Qt finding.
- **Apple energy guides:** use lower frame rates, halt animation in the background, and expect
  idle timers to wake the CPU.
- **WCAG:**
  - **2.2.2 Pause, Stop, Hide (A):** moving content that starts automatically, lasts **more than
    5 s** and sits beside other content needs a pause, stop or hide control. A long-running
    "working" loop beside usable content is in scope.
  - **2.3.3 (AAA):** motion triggered by interaction must be possible to switch off. Vestibular
    reactions include "nausea, migraine headaches, and potentially needing bed rest".
  - **2.3.1 (A):** no more than three flashes per second; red is the most dangerous.
- **Prevalence:** vestibular dysfunction affects **35.4 %** of US adults aged 40 and over
  (Agrawal 2009, NHANES).
- **`prefers-reduced-transparency`** is not Baseline (MDN).

**E-52 Emotion, trust and how people perceive progress [O].**
- **Emotional design:**
  - Norman (2004): visceral, behavioural, reflective.
  - Walter: functional → reliable → usable → pleasurable. Delight counts only once the lower
    layers hold.
- **Lee & See 2004 (Human Factors 46(1)):** trust should be
  - *calibrated* to capability;
  - able to follow changes in capability (*resolution*);
  - specific rather than global.

  Trust is built by conveying **purpose, process and performance**.
- **Chen et al., SAT model:** three levels of agent transparency — actions and plans, reasoning,
  projected outcomes. More transparency improved performance and calibrated trust: operators
  accepted correct plans and rejected wrong ones (DTIC ADA600351).
- **Myers 1985:** 86 % of 48 students liked percent-done bars and "didn't mind so much if it was
  inaccurate".
- **Harrison 2007 and 2010:** a bar's pace profile changes how long the wait feels;
  backwards-moving ribbing felt **~11 % faster**.
- **Viget skeleton study (n=136):** perceived wait was 2.82 s with a skeleton (the worst), 2.41 s
  with a spinner, 2.29 s with a blank screen. The authors' hypothesis: novelty draws attention to
  the wait.

### 6.4 Visual-effect technology

**E-53 Animation libraries (measured unless BP) [O].**

| Library | Version (date) | gzip | Reduced motion | Notes |
|---|---|---|---|---|
| GSAP core | 3.15.0 (2026-04-13) | **28.3 KB**; + ScrollTrigger 18.0; + Flip 9.7 (gsap with Flip 36.3) | Only through `gsap.matchMedia()`; nothing by default | Free, including the formerly paid plugins, since 2025-04-30 — except in no-code tools that compete with Webflow. Its own rAF ticker; values written on the main thread |
| Motion | 14.0.0 (**2026-10-02**) | `motion/mini` animate **3.4**; LazyMotion + m 7.4 (29.3 with domAnimation); full `motion` component **41.3** | Built in | Motion One is merged in (last standalone `@motionone/dom` 2024-06). New `AnimateView` wraps React 19.3 `ViewTransition` |
| lottie-web | 5.13.0 | full **76.0**; light (SVG) **46.4** | None built in | `title`/`description` become SVG title/desc, nothing more |
| dotlottie-web | 0.80.0 | 33.0 JS (BP) + **WASM 496 KB gz** | None documented | **Fetches its WASM from a CDN by default** (`setWasmUrl` for offline use) |
| Rive | 2.44.0 (2026-09-30) | 51.6–60.0 JS (BP) + **WASM 368–926 KB gz** | An example only | **Fetches its WASM from unpkg by default.** State-machine inputs are deprecated in favour of Data Binding (view models bound to numbers, enums, text) |

**E-54 Figma Motion [O].** Announced at Config on 2026-06-24.
- A Motion mode with a timeline, keyframes, a bezier or spring ease per keyframe, and presets.
- Exports MP4, WebM, animated SVG and GIF.
- **Exports code as CSS, JSON or React**, also through the Figma MCP server. No Lottie export is
  named.
- Plan or beta status: unverified.

Sources: figma.com/motion; figma.com/blog/config-2026-recap.

**E-55 WebGPU and the Qt shell [O].**
- WebGPU ships in Chrome 113+ (Windows), Safari 26 and Firefox 141 on Windows. It is **not
  Baseline** (web-features 3.40.1).
- **Qt WebEngine 6.11 compiles Dawn out** (`use_dawn=false` and `skia_use_dawn=false` in
  `src/core/CMakeLists.txt`), so no flag can enable WebGPU in the shell.
- It also sets `enable_swiftshader=false`, so there is no software WebGL fallback.
- Base Chromium is 140.0.7339.264.
- So a GPU renderer in the shell means WebGL 2.

**E-56 Platform features in Chromium 140 (Qt 6.11) [O].** Source: MDN BCD 8.1.4 and web-features
3.40.1.
- **Supported:**
  - scroll-driven animations (not Baseline: behind a flag in Firefox);
  - same-document View Transitions and `view-transition-class` (Baseline low, 2025-10-14);
  - cross-document `@view-transition` (not in Firefox);
  - `@property`, `oklch()`, `color-mix()`, relative colour, `light-dark()`;
  - `interpolate-size` / `calc-size()` (Chromium only);
  - `forced-colors`, `prefers-contrast`;
  - `font-variation-settings`, `font-optical-sizing`;
  - `prefers-reduced-transparency` (Chromium only; whether Qt maps it to the Windows setting is
    unverified).
- **Not in 140:** element-scoped View Transitions (arrive in 147).
- **Partial before 151:** anchor positioning.

**E-57 System variable fonts [O, measured from the font files].**
- **Windows 11:**
  - **Segoe UI Variable** (`SegUIVar.ttf`): wght 300–700, **opsz 5–36** (default 10.5), 15 named
    instances;
  - Cascadia Code and Cascadia Mono: wght 200–700;
  - Bahnschrift: wght 300–700, wdth 75–100.
- Microsoft says opsz applies automatically, and that HTML must name the font explicitly
  (learn.microsoft.com, Windows typography).
- **SF Pro:** wght, wdth and opsz; it blends from Text to Display between 17 and 28 pt.
- **Unverified:** whether `system-ui` gets opsz in Safari, and whether Android's system Roboto is
  variable.

**E-58 GPU graph renderers and compositing cost [O].**
- **`@cosmos.gl/graph` 3.4.2:** WebGL 2, layout computed on the GPU, 156.8 KB BP. Avoid the old
  `@cosmograph/cosmos` name, which is licensed CC-BY-NC.
- **`@antv/g6` 5.1.1:** 399.8 KB BP.
- **`force-graph` 1.52.0:** Canvas 2D, 57.4 KB.
- **`sigma` 3.0.3:** WebGL, 26.0 KB BP (38 KB measured with graphology, E-7).
- **Compositing (web.dev):**
  - Only transform and opacity are compositor-only.
  - "Anything that involves a blur (like a shadow…) takes longer to paint", so animating
    `box-shadow` repaints every frame. Animate the opacity of a pre-rendered shadow layer
    instead.
- **Blur:** a third-party Skia analysis puts most of its cost in a fixed per-operation
  render-target switch that scales with area. This has not been checked against Chromium source.

### 6.5 Awe in technical products

**E-59 Stripe globe [O/S]** (stripe.com/blog/globe).
- **What it draws:**
  - three layers: a translucent ocean sphere, tens of thousands of dots in a sunflower spiral,
    and arcs between pulsing discs;
  - the arcs show real coverage (where Stripe accepts payments → where businesses use it), not
    live transactions.
- **Stated goal:** "inspire a sense of awe, invite people to explore, and conceal details for
  discovery".
- **Engineering:**
  - a hard 60 fps rule, otherwise a static image;
  - geometry only for countries where Stripe is live (60k → ~20k dots);
  - animation pauses during scroll;
  - `antialias` off, which fixed integrated GPUs driving 5K screens.
- **Later:** a "small, but momentous appearance" in the Dashboard; its form there is not
  described.
- **Users:** HN reported "extremely janky… when scrolling, on an upper-midrange laptop"
  (item 24352138).

**E-60 GitHub homepage globe [O]** (github.blog, "How we built the GitHub globe" and "Making
GitHub's new homepage fast and performant").
- **Data:** real pull requests opened in one place and merged in another, from the event stream.
  The team noticed the arcs "could quite as easily just be design animations", so they added
  **proof of life**: hover shows the PR, repo, time and language, and every arc is clickable.
- **Rendering:**
  - one InstancedMesh of ~12k land circles;
  - arcs animated with `setDrawRange`;
  - a landing is a dot plus a ring that scales up and fades.
- **Budget:**
  - antialias off;
  - **four quality tiers, dropped when the scene misses 55.5 fps over the last 50 frames**
    (pixel ratio 2 → 1.5, fewer arcs, fewer dots);
  - an inline SVG globe paints first, then cross-fades to the canvas;
  - IntersectionObserver starts and stops it;
  - transform and opacity only.
- **Users:** HN reported 40–55 % CPU without hardware acceleration (item 25584720). A browser
  engineer pointed to `failIfMajorPerformanceCaveat` for refusing software rendering.

**E-61 Linear [O].**
- **2024 redesign:**
  - goals: "reduce visual noise, maintain visual alignment, and increase the hierarchy and
    density";
  - themes generated in LCH from three variables (base, accent, contrast); the contrast variable
    yields high-contrast themes;
  - "limiting how much chrome (blue…) was used";
  - alignment work "you'll feel after a few minutes of using the app".
- **2026 refresh, "A calmer interface for a product in motion":**
  - "Don't compete for attention you haven't earned"; "Structure should be felt not seen";
  - a sidebar dimmed "a few notches", fewer and smaller icons, warmer and less saturated greys;
  - "If most people don't immediately notice what changed, that's probably a good sign."
- **Sources:** linear.app/now, "How we redesigned the Linear UI" and "Behind the latest design
  refresh".

**E-62 Awwwards Sites of the Year [O/S].**
- **Winners:** 2025 Lando Norris and Messenger (abeto); 2024 Igloo Inc, Don't Board Me, Opal
  Tadpole; 2023 Lusion v3, Noomo, Mana Yerba Mate.
- **Igloo Inc case study:**
  - a scroll-driven camera journey;
  - an intro rendered in real time;
  - VDB volume data driving particles synced to sound;
  - the UI drawn in WebGL so that glitch and scramble effects avoid DOM recalculation;
  - shaders compiled in the background;
  - low-end devices targeted.
- **Lusion:** cloth simulation baked into 16-bit data (983 KB desktop, 246 KB mobile), with
  reactive cursor and scroll animation.
- **Recurring techniques:**
  - scroll-driven camera stories;
  - full-screen shader or particle fields;
  - cinematic transitions (aberration, displacement);
  - kinetic or scrambled type;
  - fluid or light injected by the cursor;
  - simulation baked offline;
  - audio-synced motion.
- **What they share:** all are spectacle for a single visit, and none is driven by the visitor's
  own data.

**E-63 Flighty (Apple Design Award 2023) [O].**
- "We want Flighty to work so well that it feels almost boringly obvious." Its analogy is airport
  boards: "one line per flight… 50 years of figuring out what's important".
- "There's something comforting about information always being there."
- "We really have to shine when things go awry":
  - delay notifications lead with the *reason* (the inbound aircraft tracked 25 h ahead, ATC
    ground stops with their probability of extension);
  - before takeoff the Island shrinks to minimal progress, because "we won't see them again until
    they land";
  - the landing message is warm ("Mom landed… 22m early").
- The wonder lives in **Passport**, a rarely visited retrospective of the user's own flights
  drawn as artwork.
- Sources: developer.apple.com/news (id 970ncww4); flighty.com.

**E-64 Data-driven beauty [O].**
- **Wattenberger's repo visualization (GitHub Next):**
  - packed circles, colour by file type, size by file size;
  - a "fingerprint" learned by repetition and regenerated on every push, building "a baseline to
    detect… large changes";
  - import links shown only on hover, because there are "too many connections".
- **Gource:** repository history replayed as a growing tree. It is an artefact you watch, not an
  always-on view.

**E-65 Delight in daily-use apps, and how it survived [O].**
- **Arc** (Letter to Arc members, 2025):
  - a "novelty tax: too many new things to learn, for too little reward";
  - Spaces used by 5.52 % of daily users, Live Folders by 4.17 %, Calendar Preview on hover by
    0.4 %;
  - the "saxophone vs piano" critique.
- **Things 3:** the draggable Magic Plus makes a playful gesture do real work, because where you
  drop it decides where the item is created.
- **Raycast confetti:** shown only when asked for (a deeplink), and doubles as a "success" test
  signal. Its acknowledged flaw: it "does steal focus".
- **(Not Boring) Habits** (Apple Design Award 2022):
  - an explosive 3D checkbox with sound and haptics behind a long press — "we had to make it much
    more intentional";
  - the standard controls stay "fairly off-the-shelf… simple and predictable".

**E-66 Concentrated hero moments [O].**
- **Next.js Conf:** one prism-and-beam hero; raymarched reflections limited to the prism and
  "turned … off entirely for mobile devices"; drei `<PerformanceMonitor>` adapts quality to
  measured fps.
- **Vercel Ship 2025:**
  - ferrofluid dropped because it triggered trypophobia;
  - oil-slick looks were "too far, too shiny, and too loud", and they pulled back to "darker,
    sleeker… grounded";
  - one hero through a "portal" plane, with plain components everywhere else.
- **Apple product pages:** pre-rendered frame sequences scrubbed by scroll position. This comes
  from a reverse-engineering write-up, not an Apple source.

### 6.6 Gaps in this addendum

- **Not found:**
  - a primary source for whether the ChatGPT voice orb follows audio amplitude;
  - a primary source for the Claude app's animated mark;
  - Stripe Press's engineering;
  - Material's container-transform durations;
  - Android battery guidance.
- **No controlled study of adaptive or decaying animation intensity exists in what was
  searched.** The proposal's fatigue rules (design doc §6.4) rest on habituation research, NN/g,
  and severity-scaled precedents.
- **Unverified:**
  - whether Qt maps `prefers-reduced-transparency` to the Windows setting;
  - whether `font-optical-sizing` reaches Segoe UI Variable through a local `font-family` inside
    Qt.

  Both need a five-minute check in the shell.
- **Not checked against the Chromium source:** the Grida blur-cost figures.

---

## 7. JARVIS, reel, film-UI and voice benchmark (2026-10-04)

This section holds the evidence for `ARCHEUS_V2_VISUAL_DIRECTION.md` §20–§29 and
`ARCHEUS_V2_UI_ARCHITECTURE.md` §U–§V.

**Method.** Three read-only passes ran in parallel:

1. **Thirteen JARVIS-style repositories,** shallow-cloned into the session scratchpad and read in
   source (`scratchpad/r/<owner>_<repo>`). Counts come from regex greps, with known false
   positives removed, so treat them as approximate.
2. **The five Instagram reels** the user supplied.
   - No login was used, and no Instagram cookie command was run.
   - Captions and handles come from the public captioned-embed page through Jina Reader.
   - One cover still per reel came from the page's `og:image`; reel 1's caption was confirmed
     through public oEmbed.
   - **No reel video was watched**, so motion is described only where the caption describes it.
   - Two stills (reels 3 and 5) were also viewed directly by the author of the design document,
     and they match the descriptions below.
3. **Film-UI (FUI) craft and voice-state conventions,** from the designers' own interviews and
   official guidelines.

No fetched content carried instructions.

### 7.1 JARVIS-style repositories

**E-67 Thirteen repositories, read in source [O].** Stars and sizes are from the GitHub API on
2026-10-04. "Inf." counts `infinite` CSS animations. "Fake" means a fabricated value shown as
live. "Audio" means visuals driven by real audio. "RM" means reduced-motion handling.

| Repo (★) | Stack | Focal object | Palette / type | Inf. | Fake | Audio | RM | Responsive | Notable |
|---|---|---|---|---|---|---|---|---|---|
| thisisreyy/jarvis (0) | React 18, R3F, framer-motion | PBR metal arc reactor; emission colour per state, lerps to amber under load | `#06070a`, ice `#84b6d6`, muted ok/warn/alert; Inter Tight, IBM Plex Mono; CSS rejects "outer neon halo" | 1 | yes: `audioLevel = Math.random()` every 100 ms (`App.tsx:54`); "1.21 GW", "34.2 °C" (`TelemetryRail.tsx`) | no | CSS only; the 3D ignores it | no | Labels its demo mode "Demo"; WebGL fallback |
| Dix01/JARVIS (15) | FastAPI, React, Electron | SVG "reference dial", 7 rings spinning `linear infinite` (`Orb.tsx`) | cyan `#22d3ee` → violet when thinking; Orbitron, Rajdhani | 16 (+~25 `animate-*`) | fake boot log; perpetual rAF just to show fps | mic AnalyserNode (`lib/voice.ts`) | yes (the orb is CSS) | no | 58 `blur(`, 31 backdrop-blur, 62 box-shadow; real psutil telemetry |
| hasibjaan/jarvis (0) | PySide6 | A circle whose edge "ripples with the audio level… a circle that breathes, not a blob" (`ui/orb.py`) | `#04070E`, cyan, violet speaking; Orbitron | 0 | no | mic RMS, and the reply waveform | — | desktop | **Measured: fullscreen HUD ~24 ms/frame, "intermittently stalls audio playback"; orb 3.8 ms** → shrank to the orb (README); 30 fps, stops when hidden |
| nikdonthala/jarvis-prototype (0) | React 19, R3F | 800-particle plasma orb | neon cyan, magenta, pink, green on `#040a14`; Orbitron, Share Tech Mono | 6 | battery "simulate[s] drain" with `Math.random` | mic | no | no | Draggable widgets |
| kvdoe/jarvis-ui (0) | React 19, three | Wireframe "HolographicCore", 220 particles | OKLCH cyan; 3-layer glow; Courier New | 10 | hex stream "0xA4F2", "SYNC OK"; "STARK INDUSTRIES" | no | detects it; the rAF ignores it | no | **PRODUCT.md bans "generic glowing orb" and requires reduced motion; the code ships both violations**; thinking = rotation ×3.5 |
| PRUTU29/jarvis (0) | Flask, three via CDN | Reactor; 1,500 particles + "matrix rain" | neon cyan, magenta, lime on `#050510`; Orbitron | 4 | no (real psutil) | no | no | 3 breakpoints | 12 backdrop-filters; **`CORS(*)` beside `/api/terminal/run` and file search** |
| Nikhil0learning/Jarvis (0) | PyQt6 | HudCanvas | `#00060a`, cyan, orange; Courier New | 2 | random "breathing shimmer" over the real level | real PCM | no | desktop | 60 fps QTimer, no stop when hidden |
| shauryamalhotra957-wq/jarvis (0) | vanilla JS, three | Earth globe "satellite targeting", 4–5k textures (2.5 MB) | cyan `#4df3ff` on `#020a12` | 10 | "reactor pulse" is synthesized sine sums | an analyser class exists but is used only in tests | **yes, the only repo that stops its 3D** | 12 `@media` | perpetual rAF writing a CSS variable; 43 aria attributes; design doc ignored by the code |
| eadmin2/jarvis_ai (179) | single-file HUD | Canvas 2D reactor, **6 states including a distinct `tool` state** | cyan, teal, amber; Orbitron | 2 | random hex/coords line | mic PCM | no | 1 | **The agent pushes panels on screen through `hud_display` tools**; cinematic boot with audio; `shadowBlur` up to 40×DPR every frame |
| Gmasterzhangxinyang/jarvis-amber-protocol-hud (64) | three r128 + MediaPipe via CDN | Camera feed + gestures | **amber/red**; Segoe UI | 2 per file | CPU/NET bars `Math.random` | no | no | no | Weather real (Open-Meteo) |
| xxjun9527/jarvis-holographic (44) | R3F + postprocessing bloom | Holographic Earth | `#00f0ff`; Orbitron | 5 | "Power Cells" random walk | mic | no | no | 14 rAF loops, 38 `Math.random` |
| jincocodev/openclaw-jarvis-ui (38) | three, GSAP, VAD-web | 3,000-particle orb (1,000 on mobile) | hue-rotatable, red default | 11 | idle waveform is sine + noise | **TTS output analyser** | — | yes + PWA | **Pauses when hidden; user power-save caps at 15 fps** |
| bertrandmbanwi/Jarvis (37) | Next 15, three | GLSL orb, 2,400 particles; **typed 15-parameter state table, states blend** | cyan on `#000408`; Inter, JetBrains Mono | 11 | no; a real cost dashboard | **server-sent TTS amplitude envelope** | lowers DPR but does not reduce motion | yes | Pauses when hidden; DPR ≤ 2 |

**E-68 Cross-repo counts, out of 13 [O, approximate].**

| What | Count | Repos |
|---|---|---|
| A central orb or reactor as the focal object | **12** | all except xxjun (Earth) |
| Cyan on near-black | 11 | |
| Orbitron and/or Rajdhani | 8 | |
| A perpetual render loop while visible | **13** | all |
| Pause when hidden | 3 | hasibjaan, openclaw, bertrand |
| A user power-save mode | 1 | openclaw |
| At least one infinite CSS animation | 12 | |
| At least one fabricated value shown as live | **8** | |
| Real system telemetry | 7 | |
| Visuals driven by real audio | 8 | |
| Detect reduced motion | 5 | |
| Actually stop their 3D under reduced motion | **1** | shaurya |
| Responsive (of the 11 web UIs) | 5 | |
| A fake boot or "kernel" sequence | 5 | |
| Real bloom post-processing | 1 | xxjun (the rest stack `box-shadow` and `drop-shadow`) |

**What the best of them do [O]:**

- **A typed state → visual parameter table** (bertrand), including a separate **tool** state
  (eadmin2).
- **Audio coupling from measured signal** (hasibjaan, openclaw, bertrand).
- **Physical material over neon** (thisisreyy).
- **The agent driving what is on screen** (eadmin2).
- **Honest cost measurement:** hasibjaan shrank its UI after hearing the frame cost in its own
  audio.

### 7.2 The five supplied reels

**E-69 Instagram reels [partly observed: caption, creator, one cover still each; no video
watched].** Each entry is marked by how it was seen.

1. **`DY_YCRYgEwi` — @jonathonmj** (with @kycoai), 61k likes.
   - [from caption] "My kind of evening… #claudecode #jarvis #aiagents". The project is probably
     **Z.E.R.O**, which reel 5 names [inferred].
   - [observed] A wall TV in a blue-LED room.
   - [observed] A full-screen radial network graph, coloured by cluster with white endpoints
     around a blue core.
   - [observed] Translucent label/value panels top-left and right, a status-dot list on the
     right edge, a pill bar at the top, a clock, and an overlay reading "$11,500".
2. **`DY4o8dluXdK` — @lukebuildsai,** 379k likes, 121k comments.
   - [from caption] 'Comment "Jarvis" and I'll send you the platform' — a lead-capture funnel.
   - [observed] A man at a three-monitor desk in a warm amber room. The wall screen shows a
     classic monochrome blue film HUD: a ring with ticks around a particle texture, a pie chart,
     dense text columns, and "$30k MRR" overlays.
   - [observed] The subtitle reads "Hey Jarvis, wake up!".
3. **`Dd9g4biMnS4` — @shipnotesai** ("UI animations & free code"), 1.1k likes.
   - [from caption] "Every word your assistant says flies out of 12,000 particles and lands as a
     live caption. You can read it with the sound off. Listening, thinking, speaking. One
     JavaScript file, no libraries".
   - [observed, viewed directly] Near-black, with lots of empty space and one mauve/pink accent.
     A bold white headline, "Your Jarvis needs a face.".
   - [observed] Three monospace state pills, LISTENING / THINKING / SPEAKING; SPEAKING is lit.
   - [observed] A particle sphere sheds particles that form the caption "You have three
     meetings", partly formed.
   - Repo: in the bio, not retrieved.
4. **`Dct1a3Yud5K` — @reznikov_engineering,** 510 likes.
   - [from caption] "The 'face' is here".
   - [observed] A curved monitor in an LED-lit desk setup. On screen: a cyan point-cloud human
     head in profile with a warm orange glow inside, dissolving into particles at the back. The
     rest of the screen is black.
5. **`DZcSLefuxRU` — @jonathonmj with @agentcoreai,** 29k likes.
   - [from caption] "The difference between an LLM and Z.E.R.O".
   - [observed, viewed directly] A 3D "brain" network of coloured clusters, each labelled
     "<REGION> · <n> neurons · firing 0.xx" (MOTOR CORTEX, PREFRONTAL, HIPPOCAMPUS, BRAINSTEM).
   - [observed] A semi-transparent grid of about 32 snake_case tool tiles laid *over* the graph
     (web_search, read_file…).
   - [observed] A red "LIVE" badge with a counter, a right-edge index of modules, and an overlay
     title "TOOLS".

**Patterns across the reels [inferred]:**

- Four of five centre a presence object: a sphere, a ring, a head or a brain. Reel 1 has its
  graph in that slot.
- State is shown with named pills or LIVE badges.
- Dark ground, with saturated light assigned to meaning.
- Three of five are staged in LED-lit rooms. The room supplies part of the "wow".
- Reach comes partly from distribution mechanics: reel 2's 121k comments are a "comment to get
  it" funnel.

### 7.3 Film-UI craft

**E-70 Jayse Hansen** (lead on the Avengers Mark VII HUD) [O]:

- "The HUD was a character… each shot had a specific message to deliver."
- Stereo removed the depth-of-field cheats, so "all the text is related to the scene, and all the
  graphics had a purpose". Depth is used to separate things.
- **Patterns, not readouts:** "an immense amount of data… you can't read each individual thing.
  And you're not meant to — he's looking at the patterns." Tony "knows where each piece of data
  lives". "It can remain complex — yet convey what you need simply."
- Grounded first in real flight instruments. A fighter pilot told him real HUDs "are always
  overloaded" and that pilots are taught to ignore most of them.
- Sources: provideocoalition.com ("Marvel's The Avengers: taking the HUD to new heights");
  pushing-pixels.org/?p=7447.

**E-71 Territory Studio and Perception [O]:**

- **The Martian (Territory):** "real on almost every single piece of data". NASA warned that
  operators are trained to spot anomalies, so visual parameters must stay stable. "NASA's screens
  never flash 'DANGER'". NASA/JPL's Dave Lavery: "the most mission-critical thing on screen is a
  spreadsheet of events" (pushing-pixels.org/?p=11034). Territory describes the screens as "pared
  down and pure, each one glows with quiet authority".
- **On JARVIS:** an AI "which really is just a voice, was represented with a cloud of data", for
  dramatic reasons.
- **Perception:** "the UI itself is the personality" (Engadget 2015-12-14). Black Panther's sand
  table hints at "a much richer, a much deeper world… off screen" (School of Motion).

**E-72 Noessel and Shedroff, Make It So; scifiinterfaces.com [O]:**

- **"Tony Stark is being lied to by his own creation" (2015-09-15):** the first flight's HUD has
  29+ elements.
  - 87 % reposition without being asked; 6 last under 2 s; 6 "risk dangerous mid-flight startle
    reactions"; every one overlaps another through transparency.
  - Verdict: "a placebo interface meant to keep Tony thinking he's in control".
  - The need behind it: "we want to be at the adult table… we really want to *feel* like we
    are."
- **Agentive technology:** the design work is in the "maintenance and customization touchpoints"
  — pausing, exceptions, adjusting the rules.
- **Two lessons from the book:** "Small interfaces advertise small-value experiences"; "Avoid
  reminding people of the simulation".
- **Transparent screens:** designers "*must* build up a skeptical immunity" to sci-fi, because it
  answers to "story, worldbuilding, and often, spectacle".

**E-73 Mark Coleran** (coined "FUI") [O]:

- These screens are "not interfaces. What they are are *plot visualizations*." The worst trope is
  "spinning 3D globes and 'flying' to information".
- "In a movie, you see an interface for at most a couple of seconds. In real life, every design
  decision has a consequence… day in and day out… you can't say I put this here because it looks
  cool."
- Source: pushing-pixels.org/coleran interviews.

### 7.4 Voice-state conventions

**E-74 Voice assistants [O]:**

- **Alexa light ring** (official identity guide):
  - listening: directional blue; thinking: alternating blue; responding: directional blue;
  - mic muted: solid red; notification: pulsing yellow;
  - error: *fast*-pulsing purple; Do Not Disturb: *slow*-pulsing purple — one hue, two meanings,
    told apart by tempo.
- **Google dots:** they "indicate when Google is working for you", with defined expressions for
  listening, thinking, replying, incomprehension and confirmation. "Their motion is rooted in
  consistent paths and timing… a standard set of snappy easing curves" (design.google, "Evolving
  the Google identity").
- **Siri:** an edge glow while active, plus type-to-Siri.

**E-75 OpenAI Realtime and ChatGPT voice [O]** (developers.openai.com, realtime-vad and
realtime-conversations; help.openai.com voice FAQ):

- **Barge-in:** "immediately stop playback". Send `conversation.item.truncate` with `audio_end_ms`
  so the model knows where it was cut off; the unplayed transcript is removed.
- **Push-to-talk:** `turn_detection: null`, gate audio on key-hold, commit on release. OpenAI: PTT
  "gives the users control… avoids VAD failures, and it feels snappy because we're not waiting
  for a VAD timeout."
- **ChatGPT voice:** captions (`cc`) and a saved transcript. Users ask for hold-to-talk because
  full-duplex voice interrupts them.

**E-76 Push-to-talk conventions [O/S]:**

- **Zello:** the PTT outline is orange when idle, red while transmitting, green while receiving.
  Hold-to-talk is the default (support.zello.com).
- **Discord:** a green ring around whoever is speaking (patch notes, 2025-07). Its support article
  was blocked (403).

**E-77 Mic meters and voice accessibility [O]:**

- **AnalyserNode** passes audio through unchanged and exposes time- or frequency-domain data
  (MDN).
- **Chrome's reference AudioWorklet volume meter:** RMS per block, `volume = max(rms, prev*0.8)` —
  instant rise, exponential fall — posted at most about every 16 ms
  (GoogleChromeLabs/web-audio-samples).
- **W3C NAUR (2022 Draft Note):** speech output comes with "a synchronized text transcript"
  (REQ 7); users can choose input and output modes (REQ 3, 4, 8).

**Gaps:**

- No reel video was watched. The motion claims are the captions' own.
- The bio links (reel 3's code and demo) were not retrievable without a login.
- Discord's PTT article was blocked.
- The dBFS mapping practice is unverified.
- The repo counts are greps, not audits.
