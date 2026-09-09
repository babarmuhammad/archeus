# Handoff — getting the cluster to 1:1 with the references

Rewritten 2026-09-09 (third pass of that day; the "what this pass changed"
section below is the second pass, and **"The glass pass"** further down is the
third). The standing instruction is unchanged: **do not stop until the cluster
and the connections are a 1:1 copy of the references**, plus **all three
renderers must represent the SAME reference**, not three approximations of it.

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

## The glass pass — what the third pass changed, and why each was structural

The instruction that opened it was blunt and it was right:

> "The structural tubes inside each Cluster3D and the tubes used for
> Connection3D must be visibly TRANSPARENT like the reference renders. Do NOT
> make them opaque solid-colored cylinders. … Use actual material
> transparency/volume/depth rather than achieving the effect only with bloom.
> The underlying geometry must remain clearly visible through the translucent
> tube."

Four things came out of it, and three of them were bugs rather than taste.
Everything below is measured against `notes/reference/`, and the numbers are in
`claude_sessions/cluster_spec.py` and `tests/test_stage.py`.

### 1. A frame tube is a glass SLEEVE with a coaxial core, not a rod

The pass was ONE `FrontSide`, depth-writing, `metal 0.78`, `clearcoat 0.9`,
`iridescence 0.35` cylinder at `FRAME_HALF`. Every one of those is a reflector,
so the tube's colour came off the PMREM map rather than off the chord — the
same diagnosis this file already carries for the conduit's housing ("THE GREY
WAS A REFLECTION"), which is why three earlier rounds of tuning its emissive
never moved it. And it was **opaque**, so a cage was a scribble of solid rods
with nothing visible behind or inside them.

The measurement that settles the shape is a perpendicular scan across a tube in
`cluster-render-single.png` (x = 70, y = 475..515, a 40 px tube):

    14 px   (0,  55, 135)    the far glass wall — RED IS ZERO
    15 px   (0, 128, 233)    the energy inside it, same hue, three stops up
     8 px   (218, 253, 254)  one narrow specular rail, near white, OFF-AXIS
     4 px   (0,  50, 110)    the near wall again, falling to the silhouette

So: a translucent sleeve at `FRAME_HALF` you read the lattice through, and a
brighter coaxial core at `FRAME_CORE_HALF` (0.024 R). **The core is the part
that writes depth** — that is what keeps the lesson the whole scene was rebuilt
around: a tube still occludes what is behind it, through a cylinder half its
width, so a cluster keeps its silhouette while the sleeve stays see-through.
`fresE: 2` moved from the wall to the core, which is where it always belonged:
exponent 9 on `pow(1 - fres)` is a filament inside a tube, and run on the wall
it was a broad pale band with bright edges — the mirror image of the rim the
wall wants (`fresE: 3`). Spokes get no sleeve: a hairline at 0.011 R would have
a quarter-pixel wall at every size this scene draws.

### 2. The pale palette was a LIGHTNESS problem, and the pow() curves were double-counting it

The scan above says red is zero in both the wall and the energy. `#7dcfff` is
(125, 207, 255) — the same hue, and **already `s = 1.0`** because its max
channel is 255, so no saturation push could ever move it. What turns a pale
tint into a saturated hue is dropping L: `#7dcfff` at L 0.46 is (0, 118, 235),
the measurement to within two levels. That is `DEEP_L = 0.58, DEEP_S = 1.12`
applied once to the five hue roles at scene build, where every pass gets it —
the lit solids, the additive hairlines, the faces, the motes and the conduit.

It is **not** a palette edit: `u_acc`/`u_acc2` are the app's link and focus
colours and clear a 4.5:1 contrast floor as text. `u_bg` and `u_white` are left
alone — the first is the ground the scene is mixed toward, the second a
highlight gate rather than a hue.

Then the correction had to be **removed from where it used to live**. The
saturation push at 1.90 and the `pow(ch, 2.5)` / `pow(ch, 2.05)` curves existed
*because* the albedo going in was pale; with a deepened albedo they applied
twice and crushed the middle channel. Measured on the field: p95 green went
148 → 66 and mean luminance 43 → 25 against a reference at 72. They are 1.25,
1.5 and 1.35 now, and the conduit's `over` block carries its own copy of both
(it ASSIGNS over `F_SHADE`) so those moved with them. `bloom` went the other
way for the same reason — `.34` was set when the lit surface was near-white and
a pass keyed at 0.55 sees far less of a deepened one, so it is `.58`.

**The general rule: a correction applied at the source must be REMOVED from
every place that was approximating it.** Two of the three numbers in this
paragraph had been set to compensate for the thing that is now fixed.

### 3. A junction's white core was never rasterised at all

Both inner shells were in the opaque core mesh, so an opaque energy shell at
0.076 R completely enclosed an opaque hot core at 0.034 R. The previous pass
resized them — the right half of the fix — but resizing cannot reach this while
the outer of the two is solid: in both references you read the white *through*
the coloured volume, so the coloured volume is **glass**. It has its own pass
now, between the opaque core and the housing, with a flat alpha rather than a
Fresnel band (the band is what makes a *housing* read as glass; here it would
put the colour on the rim and leave the middle empty, which is the opposite of
a volume).

That exposed the second half: the gradient bias is **added** to `gradT` and then
**clamped**, so a bias of 0.52 put most of a cluster's twelve junctions at
exactly 1.0 — the top of the chord, which is the third role, magenta on a
violet cage. Every junction in the field was the same flat hot pink ball. It
read as "pale pink" while the palette was pale and as a bug the moment the roles
were deepened; the clamp was the cause both times. 0.20 now, and 0.28 for the
cluster's own centre.

### 4. The seeding box is a FRUSTUM, which is what filled the frame

Queue item 1, and the eye reads it first. The box was a rectangle 20.0 wide and
10.4 tall at every depth and the frame a perspective camera sees is a wedge: at
the near slice (9.4 units out) the visible half-height is 4.89 and the box
filled it exactly, while at the far slice (22.6 out) the visible half-height is
11.8 and the box still only reached 4.94. The back HALF of the field sat in the
middle fifth of the frame. **Neither lever this queue named could have fixed
that** — more bodies packs the middle tighter and leaves the corners exactly as
empty, and narrowing the box raises the density into the collision cascade the
drift speeds were tuned against.

x and y are a fraction of the frame at each body's own depth now (`frameH(z)`,
`SEED_FILL` 1.02 for the seeding, `DRIFT_FILL` 1.18 for the wall). The near
slice is unchanged, so the hero still reads; the far slice spreads 2.4x and
lands in the corners. Two things ride on it: the **drift wall** is the same
wedge or a corner-seeded cage is shoved straight back into the rectangle, and
the **hero** is rescaled by `frameH(near)/frameH(its own z)` because pulling it
forward shrinks the frame around it. Measured: the lit fraction of the frame
went 0.86 → 0.98 against a reference at 0.95.

...and then the **radius floor**, which has now moved three times (0.10, 0.16,
0.34) always for the same reason and always by too little. Below 0.22 a cluster
is under the LOD ladder's first break and draws **no frame and no junctions at
all**; at 0.16 thirteen of the forty landed there, so a third of the frame was a
wire diagram of specks joined by conduit. In `cluster-render-field.png` every
cage in the crop has its frame and its twelve lit junctions. The floor is
asserted against `LOD_BREAKS[0]` rather than as a literal, and the multiplier
came down to 1.26 so the top of the range stays at 1.60 and only about one more
cluster crosses into the 480-rod shell.

### Where it landed, in numbers

The field probe is five lines of Playwright (boot the GUI, `ST.world='graph'`,
`setZen(true)`, screenshot) at the reference render's own aspect. Against
`cluster-render-field.png`:

| | median | p95 | mean luminance | mean saturation |
|---|---|---|---|---|
| reference | (8, 31, 76) | (248, 246, 253) | 71.7 | 0.775 |
| before | (11, 13, 21) | (158, 148, 203) | 42.7 | 0.462 |
| after | (11, 14, 24) | (121, 120, 202) | 39.3 | 0.559 |

The **shape** of the median is right for the first time — red lowest, blue
highest, which is what a saturated blue-violet field on black measures as, where
before it was a neutral grey. Saturation closed two thirds of its gap. Luminance
did not, and the next section says what is left.

## The cost pass — and the flicker was never a cost problem

Opened by a report, not by a measurement: *"fix the screen tearing and lag from
this theme"*, in the Qt shell only, with a plain Chromium tab on the same DOM
smooth. Queue item 4 below had predicted the cost half of it and the ladder in
`CLAUDE.md` (`stage: lite`, then `--disable-gpu-compositing`) turned out not to
cover it — the default tier already IS `lite`.

`tools/probe_qt.py` is new and is the reason any of this is fact rather than
theory. Everything else that measures this scene drives headless Chromium under
SwiftShader, which is right for behaviour and worthless for cost; this drives
the real window through `run_desktop(on_ready=...)` and Qt's own
`runJavaScript`, because Playwright cannot attach to QtWebEngine's CDP
(`Browser.setDownloadBehavior` is unimplemented). Measured on the reporter's
machine: **Intel UHD Graphics, ANGLE/D3D11**.

### 1. The flicker: the drawing buffer was not preserved

The finding that settles it is the user's, not a probe's: **`stage: off` is
clean**, and what they see is a strobe rather than a scanline tear — constant,
worse while scrolling.

The fact was already in this codebase, in `STAGE.blur()`: with
`preserveDrawingBuffer:false` the backbuffer is undefined once presented, so Qt
recomposites against a surface with nothing valid in it. It was applied to the
unfocused window and dismissed everywhere else as *"a buffer copy on every
single frame to repair a state nobody is looking at"*.

Somebody is looking at it. **The stage draws at 30fps by design and the
compositor runs at 60**, so every composite between two stage frames is exactly
that surface. `preserveDrawingBuffer: true`, and measured in the Qt shell at
3.0M px it does not move the frame interval at all.

### 1b. The fullscreen half: an opaque canvas is a scanout-plane candidate

Reported after the above landed: **clean windowed, starts the moment the window
goes fullscreen.** That is a Windows compositing boundary and nothing about the
scene. A windowed app is composited by DWM, DWM is always vsynced, and the
canvas is simply re-composited on the frames it did not redraw — it cannot
tear. A fullscreen or maximised window gets independent flip / multiplane
overlay, where an **opaque** canvas is eligible to become its own scanout
plane, and a plane updating every third vsync against a page plane updating
every one puts two moments on screen at once.

`alpha: true` makes the canvas something that must be BLENDED into the page, so
it stops being a promotion candidate. Chromium decides on the context
attribute, not the pixels, and the pixels do not change (clear colour is --bg
at alpha 1 and every pass preserves a destination alpha of 1). The old value
was a deliberate cost decision — *"a transparent surface has to be blended on
every composite; an opaque one is a straight blit"* — and the blit was the
problem. After: fullscreen and windowed measure identically, p50 50.0ms against
a 50.1ms target with the page's rAF a clean 16.7ms in both.

**It improved the report without closing it**, so the mechanism is right and
something else is still promoting or mis-presenting. What is left is invisible
to in-page instrumentation — verified exhaustively: no blur events, no canvas
hiding, no resize churn, no scene rebuilds, page rAF a solid 60Hz. The next
rung is `QTWEBENGINE_CHROMIUM_FLAGS=--disable-direct-composition`, which targets
the overlay mechanism directly and is far less drastic than the
`--disable-gpu-compositing` this repo already documents; measured, it costs
nothing and keeps ANGLE/D3D11.

**DO NOT re-derive "just draw every vsync in fullscreen".** It is the obvious
answer, it was tried, and it is worse: the stage's interval went 50.0 -> 28.2ms
as intended and the PAGE's rAF went from a clean 16.7/16.7 to 16.8/66.6 — the
whole app dropped to ~36fps. The 0.2ms "drained frame" that justified it is not
real either; `gl.finish()` does not force a drain under ANGLE/D3D11, so it
measures command submission like everything else. Both are recorded in
`tests/test_stage.py` so the next reader does not spend the round again.

Related, measured while looking: **the pixel budget is load-bearing.** Pinning
the ratio to 1.0 in fullscreen gives a 3.69M-px buffer and takes the whole page
to 30fps. 3.0M is close to this machine's edge.

### 2. The judder: the frame cap was not a vsync divisor

Measured before the fix: the page's own rAF was a clean 16.7ms at **both** p50
and p95 — solid 60Hz, zero long tasks — while the stage's interval was p50
33.7ms / p95 50.1ms. Those are two and three vsyncs. The cap was an accumulator
against a wall-clock target, and 1/34 = 29.4ms is not a thing a 60Hz display can
produce, so it alternated 2,2,3,2,2,3 forever.

Invisible to everything here, because the AVERAGE was correct — only the
distribution was wrong and nothing was looking at one. The target is snapped to
a whole number of vsyncs now (ceil, so idle and busy stay on different divisors),
off a **median** of measured rAF deltas: the first cut ratcheted toward the
minimum and latched a 6.5ms vsync on a 60Hz panel. After: p50 33.4ms against a
33.4ms target, p95 42ms.

### 3. Cost: 757,776 -> 353,552 triangles, and the LOD ladder now reaches the solids

The radius floor is 0.34 and `LOD_BREAKS[0]` is 0.22, so `n.lod > 0` — the only
gate the solid pass had — was true for all forty clusters, and twenty-eight of
them are at lod 1, where a glass sleeve is about **1.5 px** wide and a
three-shell junction about **5 px**. The sleeve and the junction energy volume
are `lod === 2` only now; the opaque frame core (which writes the depth that
gives a cluster its silhouette) and the junction housing (which IS the
silhouette) stay at every lod. Detail 2 is kept for the one sphere whose edge
you read and dropped to detail 1 for the four you do not.

Read the triangle count right: **three draws a transparent DoubleSide material
in two passes**, back then front, and `info.render` counts both. Six of the
scene's thirteen meshes are glass, so the blended share went 522,576 -> 105,448
— a 5x cut on the half that costs most per triangle.

`STAGE_PIXEL_BUDGET` (3.0M drawing-buffer pixels) caps the scene's 1.5 render
scale, which was a multiplier with nothing bounding it: on a 1440p window it was
8.3M pixels of blended PBR plus every bloom mip over the same area. Honest
finding from the sweep, though: **fill was not the bottleneck** — 3.75x fewer
pixels bought 4ms. A 2-triangle scene measured 33.5ms on the same machine, so
the whole cluster field costs about 1.6ms and the cost work was worth doing on
its own merits, not as the fix.

`STAGE._watch` is a one-way degrade ladder (halve the budget, then drop to
`lite`) for hardware nobody here has. Its first cut needed 90 consecutive
over-budget frames and, measured, never fired once — a machine short by a fifth
is late in bursts. It is an integrator now, up two down one.

### 4. Brighter, sharper: exposure, not calm and not a wider bloom

Queue item 1 said the field was bright in character and not in amount, and named
the two honest levers as bloom radius and more lit surface. There was a third
nobody had looked at: **ACES tone mapping exposure**, which rolls off hard (an
input of 1.0 leaves at ~0.8) and reaches only `toneMapped` materials — the lit
solids and nothing else. 1.0 -> 1.25, in both GL renderers. The cluster hot core
went 0.95 -> 1.30 and the conduit core 1.15 -> 1.45; the sleeve, the volume and
the housing did not move, because "brighter, sharper" is one instruction and the
way to sharpen a highlight is to raise what is meant to be a light.

The 2D canvas has no headroom above white — its hot core was already at 0.92, so
the whole lever there is the last 8% plus compositing it `lighter`.

### 5. Energy flowing inside the cluster tubes

The conduit had travelling packets and the cluster frame did not. `vLen` is the
tube's own axis (the cylinder template is a unit one along Y before
`instanceMatrix`), which no existing varying could stand in for — `vT`/`vGT`
walk the chord by position and do not run end to end on any rod. The offset is
hashed off the instance's translation, or all thirty tubes on a cage pulse
together and it reads as a strobe. Both GL renderers, gated by
`test_both_gl_renderers_run_energy_along_a_tube_the_same_way`.

### What the probe still says is NOT ours

Four long tasks totalling ~430ms per 12 seconds, **identical with the stage
switched off**. That is the app's own polling, not the theme, and it is the next
thing anyone chasing "the GUI feels heavy" should measure.

## What is NOT 1:1 yet — the work queue

1. **The field is bright enough in character and not in amount.** Every white
   in the reference is a blown highlight (its p95 is (248, 246, 253)) and ours
   tops out around 120 outside the junction cores. The remaining honest levers
   are the bloom **radius** (0.28, and it is global — raising it for this scene
   alone means a per-scene radius, which `_mkPost` does not have) and genuinely
   more lit surface. Do NOT reach for `calm`: every lit pass adds its own
   `o.calm` (0.30-0.50) to `u_calm` and `calm()` clamps the sum at 1.0, so this
   scene already has no ceiling — measured, moving the graph skin's value from
   0.50 to 0.62 changed the field's mean luminance from 25.3 to 25.4. (That was
   measured in zen. It is now true everywhere: `STAGE_LIFT` and `STAGE_GAIN`
   are unconditional and the graph scene's render scale is its own, because a
   display mode may not change the theme — see the mode bullet in `CLAUDE.md`.
   The corollary for anyone measuring this scene: screenshotting `#stage`
   without hiding the app chrome samples the app painted over a `z-index:-2`
   element, which reads as a 40% brightness difference that is not there.)
2. **The field is still not as PACKED as the reference render.** The frustum and
   the floor helped a great deal; `cluster-render-field.png` still has cages
   overlapping in the plane rather than mostly meeting at conduits. The lever
   left is more bodies, and N is baked into the uniform array sizes (40 is 140
   vec4s, and there is not much headroom).
3. **Background clusters are dim, not blurred.** The reference has real bokeh;
   a separable blur is a readback and this codebase does not get one
   (`tests/test_gui_flicker.py`, the Qt tearing). The affordable substitute is
   still half-built in the bead shader's defocus term.
4. **Cost has not been measured on real hardware, and this pass ADDED to it.**
   Everything here was judged under SwiftShader. The frame is now two instanced
   cylinders per edge rather than one, thirteen clusters that drew no frame at
   all now draw one, and bloom is stronger. `lite` still drops bloom; nothing
   has been checked on the Qt shell. If it tears, the ladder in `CLAUDE.md` is
   `stage: lite` first, then `--disable-gpu-compositing`.
5. **The conduit's core still carries the endpoint chord**, so a conduit into a
   gold cage is warm at that end. That is the brief's "a connection inherits the
   palettes of the two clusters" and the reference's blue-end-to-end conduit at
   the same time; the glass is forced blue and only the axis and the threads
   inherit. Left deliberately.
6. **The reference's specular rail is OFF-AXIS and ours is camera-facing.** The
   scan in §1 puts the near-white line 8 px from one edge of a 40 px tube, which
   is a light that is off to one side; `fresE: 2` puts a narrow line down
   whatever faces the camera. The conduit already has the right term for it
   (`rail`, a gaussian on `vAng`) but `vAng` for a cluster part is the angle
   around the CLUSTER's axis, not around the tube's own — it would have to
   become `atan(position.z, position.x)` like the link placements do. Nothing
   reads the cluster value today, so the change is cheap; it was left because a
   fixed local angle is painted on and rotates with the object, which is worse
   than a view-dependent line, and doing it properly means a light direction in
   the shader.

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

Everything above is landed, tested and rendering: `pytest tests/ -q` is 1964
passed / 1 skipped, `tools/smoke_gui.py` reports FAILURES: none,
`tools/gen_cluster_spec.py --check` is current, and `tsc --noEmit` plus
`next build` are clean. All three renderers carry the glass pass —
`tests/test_cluster_parity.py` gates the tube split across the two GL scenes
and the 2D canvas (which does it as a wide dim stroke under a narrow bright
one), and gates the site's deepened `HUES` against `stage.js`'s `DEEP_L`/
`DEEP_S` by recomputing the transform.

Iteration renders are in `.qa/` (gitignored) if the next reader wants the
before/after.


## The flat pass — the 3D came out, and the part list stayed

Rewritten again the same day, and this one is a reversal rather than a
refinement. The instruction came in two halves:

> "for the connection lines you can go back to drawing fine lines instead of
> all this mess same for the clusters … i think the shape is better than
> dodecahedra's but everything else is worse"

> "keep the complications of the cluster as it was before just remove the 3d
> part, so keep the nodes on the cluster as a dot which has an outer circle and
> keep everything inside, just remove from all of this the 3d effect"

The first half read as "simplify the cluster" and produced a hairline-only
cage; the second half corrected it. **The judgement is about the RENDERING, not
the part list.** So: every population the reference has, drawn flat.

### What came out of `stage.js`

Three lights, a `PMREMGenerator` environment built from a six-line gradient
scene, ACES tone mapping with a per-scene exposure, the material factory, and
nine `InstancedMesh` passes of `MeshPhysicalMaterial`: the frame as a glass
sleeve with a coaxial core, a junction as a hot core inside an energy volume
inside a glass housing, the cluster centre as the same object one size up, and
a conduit as a coaxial triple with a gold collar and a glass hub at each end.

The whole apparatus those needed came out with them — `roleCol`, `chord` and
`gradT` stayed (they are the colour rule, and the flat passes read them), while
`F_SHADE`, the injected `<begin_vertex>`/`<defaultnormal_vertex>` chunks, the
`over` blocks, `sScene`'s `onDispose` and `build()`'s exposure line did not.

### What stayed, and where it is drawn

Five draw calls, all additive, all depth-TESTED and none depth-WRITING —
which is what "no 3D" means here: nothing is shaded by a light and nothing
occludes anything.

| pass | draws |
|---|---|
| `mEdges` | every rod: the 480-rod shell at its LOD, the inner web at 0.53 R, **the coarse frame** and **the 20 spokes**. One merged camera-facing ribbon buffer. |
| `mFaces` | the hull's tinted faces — the one pass that is `NormalBlending`, because a smoky volume has to occlude what is behind it rather than sum with it. |
| `mJoint` | every node, as **a dot with an outer circle**: the 162 shell beads, the 12 junctions, the lit centre, told apart by a `kd` attribute. |
| `mMote` | the interior population and its 28 gold orbiters. |
| `mLink` | the conduits, as fine lines with packets travelling them. |

Two details that are load-bearing rather than incidental:

* **A junction is projected like geometry and a shell bead is not.** `kd.y`
  carries a world radius and the vertex shader turns it into pixels
  (`worldR * u_res.y * P[1][1] * 0.5 / dist`); a junction is a fixed fraction
  of its own hull in the reference, so sized in screen space a far cluster is a
  ring of blobs. A bead keeps its screen size, because it is a texture and a
  texture that scales to a quarter of a pixel is gone.
* **The frame is more rods in the buffer that already existed**, at
  `FRAME_HALF` and full alpha against the shell's ~0.3. What made it read as a
  frame was never the lighting model: it is three times the width of a shell
  rod and it carries a junction at each end, and both survive being flat.

### `connections.py` moved with it; `scene.ts` did too, one instruction later

The 2D canvas draws the coarse frame and its twelve junctions, one hairline per
edge and one additive dot-plus-highlight per corner. Gone: the once-subdivided
42/120 cage, the interior population, the bead at every shell vertex, the
sleeve-and-core double stroke, and the three-disc glass junction with its
`createRadialGradient` centre. The dot fallback goes back up from 180 nodes to
250, because the cost it came down for is gone.

**The site was left lit for exactly one round, and that call was wrong.** The
argument for keeping it — a showcase of one cluster on a page you scroll
through is asked for something different from a background behind an interface
— did not survive being looked at: *"put this version of the cluster in the
website too"*. So `scene.ts`'s six-station hero cluster lost its three lights
and its five `InstancedMesh` passes as well, and gained the same two things the
GUI has: the coarse frame and the twenty spokes as camera-facing additive
ribbons in one merged buffer, and the junctions and the centre as a dot with an
outer circle sized in WORLD units. Everything the stations already had — the
120-edge cage, the 42 shell beads and their halo, the interior population, the
fragmentation and the arrival animations — is untouched, and the frame rods take
the same `emid` fragmentation as the cage's edges so station 02 still comes
apart as one object.

`tests/test_cluster_parity.py` runs over all three again, and what it is FOR
has inverted: it used to keep a renderer from quietly dropping the 3D, and it
now keeps one from quietly putting it back. The `FRAME_CORE_HALF` measurement
stays in `cluster_spec.py`, because a measurement belongs there whether or not
anything draws it; no renderer draws it.

### And it fixed the Qt flicker, which no amount of flag-hunting had

353,566 triangles in 33 draw calls became 24,494 in 19. Measured in the real Qt
shell, fullscreen, focused: the page's own rAF p95 went from **249.9ms to
16.8ms** and its frame count in eight seconds from 138 to 480 — a clean 60Hz.
`notes/qt-flicker.md` has the full table, the instrumentation bug that hid it
(every earlier fullscreen measurement was taken on a page that had parked
itself on `blur`), and the three Qt/Chromium flags that were tested and are not
applied.

### Not recovered

The final glass-pass `stage.js` was uncommitted when this landed, and the
working-tree copy was overwritten. The nearest snapshot in the editor's file
history (2,904 lines against the final 3,339) is what the flat pass was built
from, so the *last round* of glass tuning — the sleeve/core split's final
numbers, the junction's flat-alpha energy volume, the deepened-role removals of
the compensating `pow()` curves — exists only as prose, in "The glass pass"
above and in `claude_sessions/cluster_spec.py`. Everything the flat scene needs
is in the spec; anyone rebuilding the LIT version should start from
`www/components/journey/scene.ts`, which still has it.


## The inner web turns on its own clock

    "the geometric shape circle inside the cluster needs to have it's own
     movement which is different from the cluster itself, this will help it
     being more visible"

A cluster is made of clusters — a 480-edge cage at 1.0 R with a second at
0.53 R inside it — and every rod in the merged buffer was spun by ONE call, so
the inner cage was rigidly locked to the outer one and read as a denser middle
rather than as a second object. Brightening it (0.55 to 0.75, the round
before) helped and could not fix that: two lattices in lockstep are one
lattice at any brightness.

`nd` was (node, half) and is (node, half, POPULATION) now — 0 the shell, 1 the
web, 2 the coarse frame, 3 a spoke — and the vertex shader gives population 1
its own clock. Two choices in it that are not arbitrary:

* **Opposite** (`-u_t + 1.7`), which is -1 and not the -0.62 it shipped as for
  one round. Reversed-and-slower was chosen on the grounds that slower is
  calmer; *"the inner web should turn opposite to the outer cluster"* is the
  mirror of the outer cage's own motion, and it is also the fastest the pair
  can be made to read without either one turning faster — the RELATIVE rate is
  what the eye picks up, and at -1 it is twice the cluster's own. A co-rotation
  at a different rate is only legible while you watch one rod; a
  counter-rotation is legible from the shape of the whole thing, because the
  two lattices slide THROUGH each other and the moiré is what says there are
  two.
* **Only the web takes it.** The shell, the frame and the spokes are one
  object; a frame drifting against its own hull would read as a bug. That is
  why `nd.z` is a population rather than a boolean — it also tells the frame
  and the spokes apart for anything later that wants to.

The site has no inner web to give this to: its six stations carry the 120-edge
cage and an interior particle population, and no second cage at WEB_R. If the
parts are ever brought fully into line, that is the one to add.

## The node effect that was tried and rejected

A second reference still was read for the junctions, and every term in it was
really there: a hot core with radial spikes rather than a disc, a filled bubble
inside the shell, a hairline shell at the bubble's silhouette, and a SECOND
concentric hairline outside it. It was built (`nCore` / `nFlare` / `nBub` /
`nSh1` / `nSh2`, with the sprite widened to 2.15 world radii so the outer
hairline was not clipped by its own edge) and the judgement was *"the cluster
was better before this last reference modifications to the cluster nodes and
core, go back to the previous one"*.

So a node is two radii again — a dot at 0.30 of the sprite and an outer circle
at 0.46 — and `tests/test_stage.py` carries a do-not-come-back guard naming the
five terms. Worth recording rather than deleting: every one of them was a
correct reading of the image, and the image is not the goal.
