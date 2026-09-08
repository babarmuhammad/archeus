# Handoff — getting the cluster to 1:1 with the references

Rewritten 2026-09-09 (second pass of that day). The standing instruction is
unchanged: **do not stop until the cluster and the connections are a 1:1 copy
of the references**, plus **all three renderers must represent the SAME
reference**, not three approximations of it.

## Read these first, in this order

1. `claude_sessions/cluster_spec.py` — **the single source of truth.** Every
   measurement, and the reasoning for each. It generates
   `claude_sessions/web/cluster-spec.js` and `www/lib/cluster-spec.ts` via
   `tools/gen_cluster_spec.py`; `connections.py` imports it directly. Change a
   number here and regenerate — never edit a generated file.
2. `notes/cluster-spec.md` — the prose version, and the transcription of the
   two `.glb` part lists. Note the correction below: its "the thick violet
   tubes in the stills are the SPOKES" reading was wrong, and cost a round.
3. `notes/reference/` (**gitignored**, ~11 MB, must be on disk):
   `cluster.glb`, `connection.glb`, `cluster-render-single.png`,
   `cluster-render-field.png`, `connection-render.png`, `field-photo.jpeg`.
   If they are missing, ask for them before changing a number.
4. `claude_sessions/web/stage.js`, the `graph(TH, c, ren)` scene. Still the
   reference implementation; the other two are ported FROM it.
5. `notes/constellation-gap.md` — the history of what each earlier number cost
   to learn. Its settled-parameters table is history, not current values.

## The tools

    py tools/inspect_cluster.py out.png            # one cluster, filling the frame
    py tools/inspect_cluster.py out.png --link     # one conduit, side on
    py tools/inspect_cluster.py out.png --node 7   # a specific cluster

It boots the real scene and overrides only the camera. **Judge at this size.**
`--link` now skips a partner whose hull overlaps the subject's: the plain
nearest neighbour in a packed field is usually a cage the camera would end up
inside.

It reads `sc.__np` and `sc.__nodes`, both named handles on the scene object.
If a probe ever goes blank, check that first — reaching through
`scene.children[0]` threw once per frame the moment a light became the first
child, and a dead `update()` is a black canvas with an empty console.

For the whole field and the 2D graph there is still no committed tool; both are
five lines of Playwright (boot the GUI, `ST.world='graph'`, `setZen(true)`,
screenshot; or `connections.render_html` to a file and open it). For the site,
`npx next build && npx next start` and drive it with Playwright — and **kill the
old server before restarting it**, or it serves chunk hashes the rebuild
deleted and the scene is simply absent with one 500 in the console.

## What this pass changed, and why each one was structural

Measured, not judged by eye: at cage scale the reference's MEDIAN pixel is
(23, 27, 113) — near-black in red and green with the blue up — against a p95 of
(251, 244, 254). Ours was (115, 117, 176) against (216, 216, 237): a milky
lavender fog with no true black and no true white. Most of what follows is that
one number.

### 1. The spoke and the frame were the same tubes, drawn twice

`notes/cluster-spec.md` read the thick violet tubes in the still as the model's
twenty `Hub spoke`s. Then `FRAME_*` was added for the *same* tubes, read a
second time as the icosahedral frame the .glb does not contain. Both shipped:
twenty rods as thick as the frame crossing every interior, which is why the
cage read as a ball of struts. In `cluster-render-single.png` **nothing radial
crosses the interior at that weight** — count them, every tube runs between two
junctions. `SPOKE_HALF` is 0.011 R stopping at 0.56 R now: the faint radial fan
the render does show around the centre.

### 2. The centre is not a sun

0.16 R at emissive 1.2 was a blown white ball filling a third of the frame. In
BOTH references the middle of a cage is **dark**. What the model's part list
calls the core is the same OBJECT as a junction, one size up — hot white inside
a violet energy shell inside glass — so the centre now has the junction's four
radii scaled 1.4x (`CORE_R` / `CORE_ENERGY_R` / `CORE_SHELL_R` / `SEED_R`).

### 3. A junction's white core was sitting on top of its energy shell

The two inner shells were the CONDUIT hub's ratios with the hot core multiplied
by 1.7 — 0.053 R against the energy shell's 0.061 R. No pink could ever show,
and every junction was a white blob in a grey bubble. They have their own spec
keys now (`FRAME_BEAD_HOT` 0.034, `FRAME_BEAD_ENERGY` 0.076, `FRAME_BEAD_R`
0.150), measured off the render where the coloured core is about half the glass
sphere and the white part about a quarter.

### 4. The second chord role is HALF THE GEOMETRY, and it was magenta

`chord()` walks primary into secondary over `smoothstep(0.40, 0.76)` and
`gradT` lands most of a cage in that band, so the secondary is not an accent.
Violet's was `ROLE_ERR` and every tube on a violet cage came out hot magenta —
the field was pink. The cool accent is the secondary now and magenta drops to
third; the highlight is `ROLE_WHITE` almost everywhere, because a highlight is
a gate of a few pixels and in the references those pixels are white. Gold
survives as a whole family and as the interior motes.

### 5. A rim is a BAND, and a tube is its mirror image

`fresE` is a mode, not a flag. 1 is the old rim ramp; **2** is
`0.16 + 1.90·pow(1 - fres, 7)`, a narrow specular line down the part of a
cylinder that faces you with a dark silhouette — which is what the reference's
tubes have and the opposite of a rim glow; **3** is a hard
`smoothstep(0.55, 0.96, fres)` ring for glass. The glass alpha is the same band
with a low floor: the floor is what you read the core through, the band is the
ring. Exponent 7 and not 3 because a cylinder's normal turns as the SINE of the
angle across it — at 3 the term is still at 65% half way to the silhouette.

### 6. All 28 "orbit GOLD" beads were being drawn WHITE

The interior population splits on `FILAMENT_MIX` (0.60 magenta, 0.85 gold, 0.95
white-hot) and the orbiters were tagged 0.985 — past the last stop. A plain
bug, invisible because "there is not much gold" reads as a tuning problem.

### 7. The conduit was not grey; it was uncurved, and then it was a reflection

`F_SHADE` writes `pow(ch, 2.5)` into `diffuseColor` and `pow(ch, 2.05)` into
`totalEmissiveRadiance`, and the conduit's `over` block **assigns over both**.
So it was the one lit surface in the scene running a 1.6 albedo and a raw
emissive — a full stop paler than the cages around it under the same key. A
pale blue past the bloom threshold spreads as WHITE, which is why three earlier
rounds of dimming and brightening that layer only ever moved it between grey
and a white beam. Then three reflections that no over-block can reach: metal
0.55 + clearcoat 0.9 under a 1.3 environment (a rough 0.16 surface mirrors the
PMREM map), **iridescence 0.4** across six stacked translucent faces, and a
0.65-emissive gold collar that stacked into a cream haze wherever several
conduits met one small hull.

**The general rule this pass earned:** an `over` block that ASSIGNS to
`diffuseColor.rgb` or `totalEmissiveRadiance` silently drops every correction
`F_SHADE` made — and a lit material has three more channels (indirect specular,
iridescence, clearcoat) that no colour written there touches at all.

### 8. The field has a back now

The seeding box was 3.4 deep, so there was no BACKGROUND: a foreground and
black. It is 6.6 deep pushed back 4.6, the haze is 16/0.042 rather than
15/0.075 (at the old rate a cage at 22 units was a dark lump, and in the
reference field the far cages are about half the near ones and still obviously
coloured), and the camera sits at 8.4 rather than 11 — the reference field is a
CROP of a constellation and ours was a diagram of one with black margins down
both sides. Cropping is the right lever for a surface that is also the app
background: `u_calm` still holds the whole scene down behind the app, and a
crop costs nothing there where forty more hulls would.

### 9. The site's hero colour was a lottery, and it lost

`seedOf(i)` is a fair draw and six draws are not a fair sample: three of the six
stations landed on `blend`, the deliberately magenta-leaning violet, including
station 01. Stations are stratified now — `(i + 0.5) / n` through the weighted
table reproduces the weights exactly for any n — while the seven sections keep
their stride, because stratifying those would put three violets in a row at the
top of the page. The gradient AXIS still comes off `seedOf(i)`, so two violet
stations are not the same object rotated.

Also ported to `www`: the per-part **gradient bias**, which the site never had.
Without it every part of a cage reads the chord at one place, so a junction's
energy shell was the same hue as the tube it sits on — flat balls where the GUI
has magenta cores. There was no room for a fifth per-instance float, so `aI.y`
carries the station in its integer part and the bias in its fraction; every
array indexed by station takes `Math.floor` of it. And the site's emissives run
hotter than the GUI's by roughly what the composer would have added, because
`Canvas.tsx` has no bloom pass and never gets one.

## What is NOT 1:1 yet — the work queue

1. **The field is still not as packed as the reference field render.** The crop
   and the depth helped; `cluster-render-field.png` is denser still, with cages
   overlapping in the plane rather than only in depth. The remaining levers are
   the seeding box (narrower in x, which risks the collision cascade the drift
   speeds were tuned against) or more bodies (N is baked into the uniform array
   sizes — 40 is 140 vec4s and there is not much headroom).
2. **Background clusters are dim, not blurred.** The reference has real bokeh;
   a separable blur is a readback and this codebase does not get one
   (`tests/test_gui_flicker.py`, the Qt tearing). The affordable substitute is
   still half-built in the bead shader's defocus term.
3. **Cost has not been measured on real hardware.** Everything here was judged
   under SwiftShader. `lite` still drops bloom; nothing has been checked on the
   Qt shell. If it tears, the ladder in `CLAUDE.md` is `stage: lite` first,
   then `--disable-gpu-compositing`.
4. **The theme's accents are pale by design and the reference's are not.** Ours
   clear a contrast floor as TEXT (#7dcfff, #9d7bff); the reference's tube blue
   is a saturated electric blue. The albedo curve and the saturation push carry
   most of the gap, and the last of it may not be reachable without a
   graph-world-specific palette — which is allowed (`WORLDS` own their palette,
   and the graph world's is already `hidden`) but was not done here.
5. **The conduit's core still carries the endpoint chord**, so a conduit into a
   gold cage is warm at that end. That is the brief's "a connection inherits the
   palettes of the two clusters" and the reference's blue-end-to-end conduit at
   the same time; the glass is forced blue and only the axis and the threads
   inherit. Left deliberately.

## Gates

- `py -m pytest tests/test_stage.py tests/test_shader_strings.py
  tests/test_cluster_parity.py tests/test_connections.py -q`
- `py tools/gen_cluster_spec.py --check` — the two generated copies
- `py -m pytest tests/ -q` — 1958 passed, 1 skipped at the end of this pass
- `py tools/smoke_gui.py` — FAILURES: none
- `cd www && npx tsc --noEmit -p tsconfig.json && npx next build`
- **A backtick inside a shader comment kills the whole GUI bundle.** It happened
  again in this pass, in a comment explaining the glass alpha. `node --check
  claude_sessions/web/stage.js` catches it in a second and is worth running
  after every shader edit; `tests/test_shader_strings.py` is the gate.
- **An injected prelude must end with a newline**, and **every number
  substituted into GLSL must be a float literal** (`F()` does this).
- **`test_cluster_parity` is what makes "all three draw the same object" true.**
  It failed the moment the GUI's junction stopped reading `HUB_HOT` and did not
  pass again until `scene.ts` and `connections.py` had been ported. Do not
  relax its READS table to make a change land in one renderer.
- **The Bash tool's heredoc eats backslashes.** A patch script containing a
  `\n` inside a string is silently corrupted; write it with the `Write` tool
  and run it by path. Cost one confusing failed assertion here.
- Every literal in `test_stage.py` is pinned deliberately — when a number here
  moves, update the assertion AND its docstring, do not delete the test.

## Where this pass stopped

Everything above is landed, tested and rendering; the full suite, the smoke
tool, the spec check, `tsc` and `next build` are all green. The working tree is
uncommitted and was already dirty when the pass started. Iteration renders are
in `.qa/` (gitignored) if the next reader wants the before/after.
