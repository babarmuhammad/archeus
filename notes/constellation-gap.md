# What the reference image has that the implementation still does not

> **Partly superseded, 2026-09-09.** The seven traits below were all closed,
> and then the whole approach underneath them changed: every pass in the graph
> scene used to be additive with `depthWrite:false`, and an additive scene with
> no depth cannot have a silhouette. The frame, the junctions and the centre
> are lit instanced solids now, and a cluster wears a four-role CHORD rather
> than one stop on a hue ladder. The reasoning in this document is still worth
> reading — it is why each trait matters — but its **settled-parameters table
> at the end is history, not the current values**. Those live in
> `claude_sessions/cluster_spec.py`, and `notes/cluster-handoff.md` says what
> moved and why.

Written 2026-09-08, after the first cut of Phase 4 landed in all three renderers and
was judged still wrong against the source image
(`WhatsApp Image 2026-09-08 at 16.09.17.jpeg`, a still from
`github.com/FloatingPragma/observer-patch-holography`).

`notes/constellation-study.md` remains the spec for the *geometry*, and the geometry
part of it is done: geodesic cages, interior populations, the long-tail radius, the
white-core node. This document is the delta — the traits the study either measured
wrongly or did not name at all. The verdict that produced it:

> "it's not only the number of nodes connecting, there is more to it"

That is correct. Node count was the easy half.

---

## 1. The hull is a translucent SOLID, not a bare wireframe — biggest miss

This is the one that changes the picture more than everything else below put
together. In the image every cage has **visible tinted faces**: a smoky violet or
blue volume filling the hull, dark at the centre, brightest where a facet turns edge
on. That is why the far side of a cage shows *through* the near side, and it is why
the big clusters read as **objects with mass** rather than as chicken wire.

All three renderers draw edges only, so a cage is a hollow scribble. It cannot read
as a solid no matter how the edges are tuned, and every attempt to fix the density by
adding edges just makes the scribble denser — which is exactly the "solid ball" LOD
problem already fought once in `tools/make_gifs.py` and `connections.drawCluster`.

What it needs: one more pass, the icosahedron's **80 faces**, additive or premultiplied,
very low alpha (~0.05–0.10), tinted by the cluster's hue, with a per-face term that
brightens toward the silhouette (a Fresnel-ish `1 - |dot(N, V)|`). Front and back
both drawn, `depthWrite:false`, which is what produces the interior chords the image
shows. In the 2D canvas the equivalent is a single filled convex path per hull at low
alpha under the strokes, not 80 separate fills.

## 2. Links are BRIGHT in the image; we deliberately made them the dullest thing

`test_a_link_is_duller_than_a_strut_and_a_node_is_the_brightest_thing` pins
`link 0.18 < strut 0.30 < joint 0.50`, and the study argued for it. Look again: the
long inter-cluster filaments are among the **brightest** things in the frame — pale
cyan and white, reading as beams with a hot core, frequently brighter than the cage
struts they connect. The reasoning ("links are almost background") was applied to the
wrong element; what *is* nearly background in the image is the far field, not the links.

Proposal: struts stay mid, links go **above** struts and just under the joints, and the
separation that keeps the field legible moves to *depth* rather than to *kind*. The
test is a deliberate update, like the two the plan already listed — rename it and
re-assert the new order, do not delete it.

## 3. The luminance ceiling is the reason it looks dim, and zen is not enough

`u_calm` mixes every scene back toward `--bg` and no skin goes above ~0.45. The image
is a black ground with **everything on it luminous**. `STAGE.zen()` now lifts calm by
0.4 (capped 0.92) and the result is still visibly darker than the reference, because
the lift starts from a base that was chosen to be a background.

Two things to try, in this order: raise the zen lift so a `graph`-world zen lands near
the cap outright, and give the **graph world specifically** a higher `calm` than the
classic skins even outside zen — it is a locked world bundle (`WORLDS` in `themes.py`),
so it can commit to a look the mixable skins cannot. `test_skin_reach.py:149` caps skin
`calm` at 0.5; that cap is about *skins*, and whether it should bind a world is the
open question, not something to route around silently.

## 4. Bloom is off by default, and the image is mostly bloom

The `lite` tier drops `EffectComposer` and its two render targets, and `lite` is the
default. Every white-hot bead in the reference is a bloom artefact. The existing rule
(threshold 0.55, not 0.2) is right and should not move — the problem is that the pass
is not running at all for most users. Zen is the obvious place to force `cinematic`,
since nothing else is on screen to compete for the frame budget.

## 5. Depth is optical in the image, not just dim

Far clusters are **blurred** — real bokeh, wide and soft — where ours are only smaller
and washed toward `--bg`. A separable blur is a readback and this codebase does not
get to have one (`tests/test_gui_flicker.py`; the Qt tearing). The affordable
substitute is per-point size AND alpha driven by depth so a far node is a big faint
smear rather than a small sharp dot, plus dropping the interior cloud and the faces on
far hulls so distance costs detail rather than blur.

## 6. Satellites

Small clusters sit *just off* the big ones, sometimes touching, at a fraction of the
scale — a hub with its own retinue. The long-tail radius distribution produces the
right *sizes* but scatters them independently, so the retinue relationship never
appears. A cheap version: after placing the hubs, place each small hull near a chosen
hub rather than uniformly in the box.

## 7. Colour

One hue per cluster, and the spread is wider than ours: violet dominant, then cyan,
gold, green, magenta, with gold appearing often as individual accent beads rather than
only as whole-cluster tint. `u_warn` is bound and now read; it is still sparse.

---

## Where each of these has to land

| # | `stage.js` (GUI) | `connections.py` (real graph) | `scene.ts` (site) |
|---|---|---|---|
| 1 faces | new pass, 80 tris merged | one filled hull path per cage | new pass |
| 2 links | offsets + test update | `lineWidth`/alpha | offsets |
| 3 calm | zen lift + world value | n/a (no ceiling there) | n/a |
| 4 bloom | force cinematic in zen | n/a | second additive Points only — **never** a pass (`Canvas.tsx:436-443`) |
| 5 depth | size+alpha by depth, LOD | already px-gated | size+alpha by depth |
| 6 satellites | placement | layout is force-directed, real data — do not fake it | placement |
| 7 colour | widen ladder | `TYPE_COLORS` is real data — leave | widen `HUES` |

Note the two "do not" cells: `connections.py` renders the **real** architecture graph.
Its positions come from the force layout and its colours from `TYPE_COLORS`. Traits 6
and 7 are properties of the *reference picture*, and inventing them there would be
drawing something the data does not say.

---

## Settled parameters, after the tuning rounds

Everything above is now closed in `claude_sessions/web/stage.js` (the `graph`
scene), which is the reference the other two renderers are ported from. The
numbers below are the outcome, and each one is a decision that was paid for.

| Trait | Value | Why this number |
|---|---|---|
| Hull faces | 80 tris, additive, alpha `0.012 + 0.115·fresnel³` | pow 3 and not 2: at 2 the interior still fills with flat colour, which is a bubble rather than a cage |
| Strut rod width | `0.005 + 0.009·r` world units | at `0.008 + 0.016·r` a rod was a band across a cage seen close up |
| Link tube width | `0.05` world units | at 0.075 the tubes passing the foreground cluster were bars across the frame |
| Tube shading | `body = pow(1-ax², 1.6)` ×0.10, `rim = smoothstep(0.50,0.90,ax)·(1-smoothstep(0.90,1,ax))` ×0.40–0.46, **no core** | glass is its walls; a body-led fill is a painted stick, and a core term is the hairline the tube replaced drawn inside its own replacement |
| Bead | core→0.19 opaque near-white, shell 0.19–0.42 hue ×0.24, rim ×0.42, `aa = 0.02 + 0.10·(1−depth)` | crisp edges; one smoothstep from the middle out is a blur, and a blur is a smudge at every size |
| Bead size | `(1.7 + 4.4·r)·(0.45+0.75·d)·(1+1.1·(1−d))` | third term is defocus: a far bead keeps its size and loses its edges |
| Hue, before compositing | `pow(c, 1.5)` on every additive pass | two pale colours added are white; the accents are pale because they clear a contrast floor *as text* |
| Calm ladder | faces +0.26 < struts +0.30 < links +0.42 < joints +0.50 | links are among the brightest things in the reference, not the dullest |
| Depth haze | `exp(-max(0, dist − 15)·0.075)` | nothing in the field is closer than ~15 units; starting at 7 was a global half-dimmer wearing a depth cue's clothes |
| Colour management | `ColorManagement.enabled = false`, `outputColorSpace = LinearSRGB` | these shaders write final display values; the composer path encoded them to sRGB twice and put a flat grey sheet over the scene (measured: 13,15,21 on `lite` against 58,63,75 on `cinematic`) |
| Packet speed | `0.045 + 0.11·energy` | at 0.16 a packet crossed a link in ~6s and read as a strobe |
| Drift | seed vel ×⅓, `sp = 0.18 + 0.5·e`, drag `0.994`, restitution `0.35`, tether `0.10` | the lattice seeding packs 40 bodies far denser than the old spiral did; the old speeds turned a drift into a permanent collision cascade |
| Zen | calm +0.12, gain ×1.12, tier→`cinematic`, ratio `clamp(dpr, 1.5, 2)` | zen is the same theme with nothing on top of it, not a louder one; the render scale is the part that is allowed to change, because rods and beads are hairlines and 0.75 crawls |

**Judge these at the size they are drawn.** `tools/inspect_cluster.py` parks the
camera on one cluster and fills the frame with it, booting the real scene and
overriding only the camera. Six rounds of "still not high quality" were spent
tuning rod walls, bead shells and interior density at a size where none of them
were visible.
