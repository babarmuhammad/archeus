# Handoff — getting the cluster to 1:1 with the references

Rewritten 2026-09-09 by the session that picked this up from the previous one.
The standing instruction is unchanged: **do not stop until the cluster and the
connections are a 1:1 copy of the references**, plus the one the user added
mid-session: **all three renderers must represent the SAME reference**, not
three approximations of it.

## Read these first, in this order

1. `claude_sessions/cluster_spec.py` — **the single source of truth.** Every
   measurement, and the reasoning for each. It generates
   `claude_sessions/web/cluster-spec.js` and `www/lib/cluster-spec.ts` via
   `tools/gen_cluster_spec.py`; `connections.py` imports it directly. Change a
   number here and regenerate — never edit a generated file.
2. `notes/cluster-spec.md` — the prose version, and the transcription of the
   two `.glb` part lists.
3. `notes/reference/` (**gitignored**, ~11 MB, must be on disk):
   `cluster.glb`, `connection.glb`, `cluster-render-single.png`,
   `cluster-render-field.png`, `connection-render.png`, `field-photo.jpeg`.
   If they are missing, ask for them before changing a number.
4. `claude_sessions/web/stage.js`, the `graph(TH, c, ren)` scene. Still the
   reference implementation; the other two are ported FROM it.
5. `notes/constellation-gap.md` — the history of what each earlier number cost
   to learn. Parts of its settled-parameters table are superseded by the
   "what changed" section below; the reasoning is still worth reading.

## The tools

    py tools/inspect_cluster.py out.png            # one cluster, filling the frame
    py tools/inspect_cluster.py out.png --link     # one conduit, side on
    py tools/inspect_cluster.py out.png --node 7   # a specific cluster

It boots the real scene and overrides only the camera. **Judge at this size.**
Six rounds of "still not high quality" were once spent tuning rod walls at
forty units, where none of it is visible.

It reads `sc.__np` and `sc.__nodes`, both named handles on the scene object. It
used to reach the live positions through `scene.children[0].material.uniforms.
u_np` — the moment a light became the first child, that threw inside
`sc.update()` every frame, which kills the render loop and leaves a **blank
canvas with nothing in the console**. If a probe ever goes blank, check that
first.

For the whole field and the 2D graph there is no committed tool; both are five
lines of Playwright (boot the GUI, `ST.world='graph'`, `setZen(true)`,
screenshot; or `connections.render_html` to a file and open it).

## What this session changed

The previous queue said the remaining work was colour plus four tuning items.
It was not: two things were structural, and everything else followed.

### 1. Every pass was `depthWrite:false` and additive

An additive scene with no depth cannot have a silhouette. Nothing occluded
anything, so forty overlapping translucent things summed into one smear and the
coarse frame — the most recognisable feature of the reference — was invisible
*inside its own cluster*. No tuning inside that model could have fixed it.

The frame, the junctions, the spokes, the centre and the whole conduit are now
**real geometry with a real lighting model**: six `InstancedMesh` over
`MeshPhysicalMaterial`, depth-written, with the haze drawing behind them. This
overrides two rules `CLAUDE.md` used to state flatly; both are amended there
rather than quietly broken.

### 2. A cluster was one hue BY CONSTRUCTION

`hue5(n.tone)` took a number that was constant across a cluster. Every cluster
was one colour because the code could not express anything else.

Every cluster now wears a **chord** of four roles
(`cluster_spec.PALETTE_FAMILIES`), and every pass reads
`chord(pal, gradT(...), hot)` — a colour that varies across the geometry by
angular position, radius and 3D value noise, with a per-cluster gradient axis
and seed. `hue5()` is gone from all three renderers.

### The rest, in the order it was found

- **`u_err` is bound** as the magenta role, and `roleCol()` pulls it a third of
  the way toward `u_acc2`: `err` is a salmon in most palettes because its real
  job is to read as a failure against text, and used raw every cluster was coral.
- **ACES tone mapping**, on the lit materials only (`toneMapped: true`; every
  raw ShaderMaterial keeps `false` and never gets the chunk). This is the real
  answer to "two pale colours added together are white", which four passes in
  this file had each been approximating with a hand-written `pow()`.
- **The shell rod is 0.013 R, not the model's 0.0555.** 480 rods at the model's
  thickness cover more than the whole surface of the hull — the arithmetic is in
  `cluster_spec.py` — and that is exactly the featureless blue sphere the scene
  shipped as.
- **The junctions are 0.135 R spheres**, measured off the render at Ø 130 px
  against a 950 px hull. They were point sprites at 2.1x a shell bead, i.e.
  dots, which is why the frame vanished.
- **The chord is weighted**, not three even thirds: `smoothstep(0.40, 0.76)`
  then `smoothstep(0.74, 1.0)`. An even split put as much magenta on a violet
  cluster as violet, and the field came out pink.
- **The conduit carries its internal filaments.** Gold `Internal_Filament` and
  cyan `Internal_CrossLink` as helices — free, because a helix on a cylinder is
  a straight line in (angle, length) and the fragment already has both — plus
  `Energy_Particle` beads riding the gold. They are the one part of a conduit
  that is NOT the two clusters' chord, exactly as the collar is gold.
- **The LOD ladder came down to (0.22, 0.70).** It was calibrated when a cluster
  was a wire cage; with the frame as lit solids the recognisable part survives to
  a much smaller size, and at the old first break half the field was bare specks
  joined by conduit.
- **The site and the 2D graph were ported.** `www` takes the chord and a solid
  frame/junction/core pass from the same generated spec (and ACES, on the same
  terms — its "never a bloom pass" rule is untouched). `connections.py` stays
  canvas 2D because its HTML is written to disk and opened over `file://`, where
  `/vendor/` is unreachable, so it takes the SPEC rather than the shaders: the
  same proportions, the same layer stack, a chord that ROTATES AROUND the node's
  own `TYPE_COLORS` hue rather than replacing it, and a lit centre.

## What is NOT 1:1 yet — the work queue

1. **The field is sparser than the reference field render.** Ours shows the
   whole drift box; `cluster-render-field.png` is a close-up of a packed frame
   where clusters overlap and every visible one is large. The floor and the LOD
   breaks were raised this session and it helped a little. The real lever is the
   camera (`cam.position.z = 11 - f.e * 1.2`) or a smaller seeding box — and
   both are a **background** decision, not a cluster one: this canvas sits
   behind the whole app and the previous session tuned that distance for that
   job. Decide it deliberately rather than while chasing the render.
2. **Background clusters are sharp, not blurred.** The reference has real
   bokeh. A separable blur is a readback and this codebase does not get one
   (`tests/test_gui_flicker.py`, the Qt tearing) — the affordable substitute is
   already half-built in the bead shader's defocus term.
3. **Cost has not been measured on real hardware.** Six instanced meshes with a
   lighting model is more than this file's stated budget, and everything here
   was judged under SwiftShader. `lite` still drops bloom; nothing has been
   checked on the Qt shell. If it tears, the ladder in `CLAUDE.md` is
   `stage: lite` first, then `--disable-gpu-compositing`.
4. **The site's journey has not been looked at with eyes.** It typechecks and
   `next build` passes; nobody has scrolled it since the port.
5. **The conduit's glass reads a little grey** next to the reference's bright
   blue. The housing's Fresnel alpha and the glass layer's emissive are the two
   numbers to move.

## Gates

- `py -m pytest tests/test_stage.py tests/test_shader_strings.py
  tests/test_cluster_parity.py tests/test_connections.py -q`
- `py tools/gen_cluster_spec.py --check` — the two generated copies
- `py tools/smoke_gui.py` — its FIRST check is "every top-level module reached
  the page", which is the one that catches the bug below
- `cd www && npx tsc --noEmit -p tsconfig.json && npx next build`
- **A backtick inside a shader comment kills the whole GUI bundle.** It happened
  again in this session, in a comment explaining the magenta role.
  `tests/test_shader_strings.py` caught it. Write identifiers bare in GLSL. That
  test reads a GLSL template as everything between the line that opens one and
  the line that closes it, so the shader-injection code deliberately assembles
  **named string constants** rather than nesting templates — a nested template
  is indistinguishable from the bug to any textual reader.
- **An injected prelude must end with a newline.** three's own shader opens with
  `#define STANDARD`; a preprocessor directive has to begin a line, and gluing
  it to the end of a prelude is an "invalid character" error reported a hundred
  lines from anything this file wrote.
- **Every number substituted into GLSL must be a float literal.** `${o.alpha}`
  for an alpha of 1 emits `1`, GLSL has no implicit int-to-float, and the
  expression it lands in fails to compile. `F()` in the scene does this.
- `smoke_gui.py` walks the settings sub-pages with a fixed 900 ms wait and
  flakes under load (several Chromium instances at once, which is normal while
  iterating with `inspect_cluster.py`). A clean re-run on an idle machine is the
  check. Two agent-page checks were already failing when this session started
  and are unrelated to any of this.
- Every literal in `test_stage.py` is pinned deliberately — when a number here
  moves, update the assertion AND its docstring, do not delete the test.

## Where this session stopped

Everything above is landed, tested and rendering. The full suite is green
(1822 passed). The working tree is uncommitted and was already dirty when this
session started. When it is committed, the commits that touch the mark or the
banner carry Federico Coscia's credit (github.com/cosfederico), which already
stands in `docs/credits.md`.
