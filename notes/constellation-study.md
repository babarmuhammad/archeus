# The constellation — from dodecahedra to connected clusters

Study for Phase 4. Reads the reference image, and turns every trait in it into a
parameter that can be written down and tested. Three independent implementations
follow from this one document: the GUI's GL stage (`claude_sessions/web/stage.js`),
the real architecture graph's 2D canvas (`claude_sessions/connections.py`) and the
site's scroll journey (`www/components/journey/scene.ts`).

## Why replace the dodecahedron at all

The dodecahedron was chosen because it is a *solid* — a closed, finished, platonic
object. That is the wrong statement now. It says "here is a thing"; the project's
subject is "here is a thing made of things, and it is connected to other things".

The reference image says the second sentence, and it says it structurally rather
than decoratively. What it shows is **nodes made of nodes**: every cage in the frame
is a wireframe hull with a whole population of smaller points living inside it, and
every cage is tied to its neighbours by long thin filaments. That is, literally, the
shape of this project's memory graph — entities inside modules inside repositories —
which is what justifies the background as *state rendered* rather than as wallpaper.

A dodecahedron has 20 vertices and 30 edges and reads as a die. A once-subdivided
icosahedron has 42 vertices and 120 edges and reads as a *cage* — a mesh dense
enough that the eye stops counting faces and starts reading a surface. That single
change is most of the difference between the two images.

## The traits, in reading order

Twelve observations, each with the parameter it becomes.

### 1. The hull is geodesic, not platonic

Many more triangular facets than a platonic solid has, and the facets are visibly
*not* coplanar — the hull bulges. That is a subdivided icosahedron projected back
onto its circumsphere.

    IcosahedronGeometry(1, 1)      42 vertices · 120 edges · 80 faces
    (was DodecahedronGeometry(1,0)  20 vertices ·  30 edges · 12 faces)

Euler checks: 42 − 120 + 80 = 2. `EdgesGeometry` keeps all 120 of them, because the
dihedral angle between two sub-triangles of one original face is ~10–20° after the
projection to the sphere, far above the 1° default threshold. Cost: 40 cages × 120
edges × 2 endpoints = 9,600 vertices in **one** merged draw call — the same order of
magnitude as the 2,400 the dodecahedra cost, and still one call.

### 2. A cluster of clusters — the interior population

Inside every hull, a dense haze of small points. Denser in the bigger hulls; a tiny
hull holds a handful. This is the trait that carries the whole idea and the one the
old scene had no equivalent of.

    a fourth draw call: Points, merged
    radius        0.55 · r      (well inside the hull, never touching it)
    count         5 + 200·(r/r_max)^2.2      → ~5 for a leaf, ~205 for a hub
    distribution  Fibonacci sphere (golden angle), radius u^0.45
                  — u^(1/3) is uniform-in-volume; 0.45 pulls slightly inward,
                    which is what gives the visible denser core
    determinism   no Math.random anywhere; identical on every reload

`0.45 < 1/3` is wrong arithmetic and `0.45 > 1/3` is the point: the exponent is
*above* the volume-uniform value, so the cloud is very slightly hollowed rather than
core-heavy — matching the image, where the densest reading comes from the hull's own
vertices, not from a solid ball in the middle.

### 3. Nodes are white with a coloured halo, not coloured dots

Every vertex is a **white** core inside a **coloured** bloom. The old joint mixed
40% toward white and read as a pale version of the accent.

    core   mix(colour, white, 0.75)   over the inner 40% of the sprite
    halo   additive, wide, coloured, pow(1 − 2d, 2.2)
    ring   a thin annulus at d ≈ 0.26, gaussian, **only on the large hulls**
           (the image shows it only where the node is big enough to resolve one)

### 4. The scale distribution is a long tail, and longer than before

Three or four hulls dominate the frame; dozens are barely more than specks. The old
scene cubed a flat hash; that is a tail, but a short one.

    r = 0.10 + h^4 · 1.50        range 0.10 → 1.60   (was 0.13 + h^3 · 1.15)

Mean of `h^4` over a uniform hash is 0.2, so the mean radius lands at 0.40 against a
maximum of 1.60 — four to one, which is what "a handful of hubs" measures as.

### 5. Depth is real: far means small, dim and washed

The old scene expressed depth only as `z`, so a distant hull was the same brightness
as a near one and the field read flat. Two separate mechanisms, because they are two
different cues:

    size   gl_PointSize scales with vD (already present, kept)
    colour vF = exp(−max(0, dist − 7) · 0.085), then mix(bg, colour, vF)

The fog mixes toward `u_bg` **before** `calm()`, never instead of it. `calm()` is the
brightness ceiling the whole stage is subject to; a scene that skips it is a scene
that has opted out of the one rule the background exists under.

### 6. Gold sits next to violet, blue, green and teal

Five hues in the frame, unevenly weighted: cool colours dominate, gold and green are
accents. `u_warn` (`#e0af68`) has been bound as a uniform since the stage was written
and **no shader in the graph scene has ever read it** — which makes gold the cheapest
possible change. `u_ok` (`#73daca`) is newly bound alongside it, for the same reason.

    stop 0  violet  u_acc2   #9d7bff      weight 1/7
    stop 1  indigo  mix 55%                      2/7
    stop 2  cyan    u_acc    #7dcfff              2/7
    stop 3  gold    u_warn   #e0af68              1/7
    stop 4  green   u_ok     #73daca              1/7

The weights come from `TONES = [0, .25, .25, .5, .5, .75, 1]` indexed by `i % 7`:
five sevenths cool, two sevenths warm. Selected in GLSL by `step()` mixes rather than
a branch chain, and the attribute is constant across a hull so interpolation lands on
the exact stop.

### 7. A hull is one hue — but not *only* one hue

Look closely at the large hulls and individual struts run gold inside an otherwise
violet cage. So the per-hull hue is a base, not a uniform:

    vJ = hash(local position)         per-vertex, deterministic
    colour = mix(hue(tone), hue(tone + 0.28), vJ · 0.45)

Bounded at 45% toward the *next* stop, so a cage never loses its identity.

### 8. Links join nodes, they do not pass through hulls

This is the observation that changes the link geometry, and it is easy to miss. The
long filaments in the image begin and end **on the hulls**, at the bright vertices —
none of them is drawn across a cage's interior. The old links ran centre to centre
and speared straight through the point cloud.

    endpoint = a + normalize(b − a) · r_a

Both endpoints need the *other* node's index, so the link geometry gains `lo` (other
index) and `lr` (own radius) alongside `lt`/`li`/`lsd`. Stable under rotation — which
anchoring to an actual spinning vertex would not be, and the image is a still frame
that gives no permission to guess.

### 9. Inter-cluster links are thinner and duller than hull struts

In the image the difference is unmistakable: struts are filaments with presence,
links are almost background. The old scene gave them near-identical `calm` offsets
(`+0.35` and `+0.34`), which is why the field read as one undifferentiated web.

    struts   u_calm + 0.30
    links    u_calm + 0.18      ← the separation
    joints   u_calm + 0.50      ← nodes are the brightest thing in the frame

WebGL line width is 1px whatever you ask for, so "thinner" is spent as alpha. That is
the correct currency anyway: the image's links are dimmer *and* thinner, and one
control buys the read of both.

### 10. Something travels along the links

Faint beads part-way along several filaments. Already implemented and already tested
(`test_the_graph_links_carry_travelling_data`) — two de-synchronised packets per
segment, speed reading `u_e`. Kept exactly, because it is the same thing
`connections.py` runs along its real dependency edges, and it is the clearest single
statement that the links carry something rather than decorate something.

### 11. Bloom is on the nodes only; struts stay filaments

Threshold stays **0.55**. This is a lesson the project has already paid for: at 0.2
every lit pixel blooms and the scene becomes an undifferentiated colour spill — you
see the glow and not the city. 0.55 with dim struts and bright white node cores is
exactly the separation the image has.

### 12. Composition: edge to edge, no empty middle

Hulls run off all four sides of the frame; nothing is centred and nothing is framed.
The existing golden-angle spiral layout plus the drifting box already produce this.
`BOUND = [11.5, 6.2, 5.0]` is unchanged, and the wall inset stays `BOUND[k] − r` —
without it a hull with `r = 1.6` half-leaves the frame while its centre is still
legally inside.

## What must not change

The physics stays. `m = r³`, elastic exchange along the contact normal weighted by
mass, the separating-pair guard, damping, the wall inset. It was written *because*
sizes vary, and Phase 4 makes them vary more, so it becomes more load-bearing rather
than less. `test_the_dodecahedra_vary_in_size_and_collide_by_mass` is renamed to
`..._the_clusters_...` and its exponent updated — it is re-asserted, not deleted.

The six stops stay: `document.hidden`, `!MO.vis`, `motion:off`, `stage:off`,
`prefers-reduced-motion`, `webglcontextlost`. So do `STAGE_SCALE = 0.75`, the absence
of `devicePixelRatio` from the file, the 24→34fps cap, the single `MO.frame` chain,
zero `fetch`/`setInterval` inside a scene, and no `backdrop-filter`/`filter:`/
`mix-blend-mode` anywhere near the canvas.

Draw calls go from three to four. The rule was never "three": it is *a handful of
uniform writes per frame and zero allocation*, and a fourth merged buffer costs one
more call and no per-frame CPU at all.

## The three ports, and why they differ

**`stage.js` (GUI, GL).** The reference implementation, and where the numbers above
get tuned, because it is the only one with a shader budget to spend.

**`connections.py` (real graph, 2D canvas).** Not decoration — this draws actual
project data. `drawDodec` becomes `drawCluster`, same contract, same two-axis
rotation (`T·0.5`, `T·0.37`, per-node phase), because the correspondence between the
real graph and the background *is* the homage and losing it loses the point. Canvas
2D has no shader, so: an additive halo painted under each white vertex dot, the
interior cloud drawn only for `r ≥ 12` (below that it is noise, not structure), and
the dot fallback threshold drops from 250 nodes to **180** — 120 strokes per hull
costs four times what 30 did, and a 2D canvas pays it on the CPU.

**`www/components/journey/scene.ts` (site, GL, no post-processing).** Same idea,
different constraint. Bloom was already tried here and removed on purpose
(`Canvas.tsx`): these are `ShaderMaterial`s writing final display values, so a bloom
pass lifts the dark tones instead of blooming the bright ones. The halo is therefore
a second additive `Points`, not a pass. DPR stays clamped at 1.75, and `STATIONS`,
`CAM`/`LOOK` and the Catmull-Rom curves are not touched — the scroll rhythm is tuned
and the geometry swap has no business retuning it.

## Derived assets

`tools/make_gifs.py` (`_dodec` → `_cluster`, regenerate `docs/graph.gif`),
`tools/capture_graph_gif.py` (re-capture `graph-real.gif` into docs and `www/public`),
`docs/architecture.md` (it describes "rotating dodecahedra" in prose), and the Graph
skin screenshots from `tools/shot_gui.py` that README, docs and the site all embed.

## The one-line summary

The dodecahedron was a *solid*. This is a *cluster*: a hull made of many facets,
holding many points, tied to other clusters at its surface. The project stopped being
about objects and started being about what holds them coherent — and that is also
what the name means.
