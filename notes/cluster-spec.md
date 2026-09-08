# The cluster, from the model

> **`claude_sessions/cluster_spec.py` is the authority; this file is its prose.**
> Three renderers draw this object and the module is the one place their
> numbers live — it generates `web/cluster-spec.js` and `www/lib/cluster-spec.ts`,
> and `connections.py` imports it. Two values there deliberately OVERRULE the
> table below, and both are arithmetic rather than taste: 480 shell rods at the
> model's Ø 0.111 R cover more than the whole surface of the hull, and the
> coarse frame is not in the .glb at all, so the render is its only source. The
> module says so at each one.

> **The references live in `notes/reference/`, and they are gitignored.**
> `cluster.glb`, `connection.glb`, `cluster-render-single.png`,
> `cluster-render-field.png`, `connection-render.png`, `field-photo.jpeg` —
> about 11 MB. They stay out of the repository because a design reference is not
> a build input and nobody cloning this needs eleven megabytes to run the tests;
> they stay on disk because every number below is only checkable against them.
> If you are reading this without them, ask for them before changing a number.


Measured out of `notes/reference/cluster.glb` (supplied 2026-09-08 as "the 3d
render of one of the clusters"), which supersedes every earlier reading of a
still image.
`notes/constellation-study.md` guessed the geometry from a photograph and got the
family right and the proportions wrong; this is the geometry itself.

Everything below is expressed as a fraction of **R, the hull radius**, so it
scales to a cluster of any size. In the file R = 2.8 model units (the
`Transparent inner volume` sphere is 5.6 across).

## Parts list

| Part | Count | Ø or thickness | Length | Sits at | Material |
|---|---|---|---|---|---|
| Transparent inner volume | 1 | 2.00 R (the hull) | — | centre | dark glass, α 0.35 |
| Central glowing core | 1 | 0.243 R | — | centre | hot white |
| Central energy seed | 1 | 0.129 R | — | centre | gold |
| Hub spoke | 20 | **0.190 R** | 0.83 R | 0.49 R out | half violet, half cyan |
| Radial filament | 19 | 0.110 R | 0.48 R | 0.29 R out | violet |
| Outer lattice rod | 480 | 0.111 R | 0.27 R | **1.00 R** (on the shell) | ¾ violet, ¼ cyan |
| Outer node | 162 | 0.075 R | — | **1.00 R** | hot white |
| Inner filament | 257 | 0.040 R | 0.16 R | 0.53 R | ⅔ violet, ⅓ cyan |
| Inner particle | 150 | 0.020 R | — | 0.61 R | 91% cyan, 9% gold |
| Orbit gold | 28 | 0.046 R | — | 0.47 R | gold |
| Outer connector | 18 | 0.028 R | 0.08 R | 1.04 R (just outside) | cyan |

**162 vertices and 480 edges is `IcosahedronGeometry(1, 2)`** — subdivided
*twice*, not once. Our cage was detail 1 (42/120) and before that a
dodecahedron (20/30). Both readings of the photograph were wrong in the same
direction, and for the same reason: the still shows two meshes at once and the
eye merges them.

## What the parts list says that no still image did

**A cluster has a lit centre.** A white core with a gold seed inside it, at the
middle of a dark translucent volume. Every version we have built was hollow —
that is why the interiors read as empty no matter how the shell was tuned.

> **...but it is not a SUN.** Drawn at 0.16 R with a 1.2 emissive it was a
> blown white ball filling a third of the frame, and in BOTH references the
> middle of a cage is **dark**. What the part list calls the core is the same
> object as a junction, one size up: hot white inside an energy shell inside
> glass. The four radii in `cluster_spec.py` are the junction's, scaled 1.4x.

**There are two scales of strut, not one.** Twenty thick spokes (0.19 R —
*thicker than the shell rods*) radiating from the core to about half-way out,
and 480 thin rods forming the shell. Drawing one mesh at a middling thickness
produces neither.

> **Correction, 2026-09-09.** The sentence that used to end that paragraph —
> "the thick violet tubes in the stills are the SPOKES" — is **wrong**, and it
> cost a round. `FRAME_*` was later added for the *same* tubes, read a second
> time as the icosahedral frame the .glb does not contain, and both shipped:
> twenty rods as thick as the frame crossing every interior. In
> `cluster-render-single.png` nothing radial crosses the interior at that
> weight; count them and every tube runs between two junctions. The thick tubes
> in the stills are the FRAME. `SPOKE_HALF` is a hairline now (0.011 R,
> stopping at 0.56 R) and draws the faint radial fan the render does show
> around the centre. `cluster_spec.py` says so at the value.

**A bead is small.** 0.075 R across — smaller than the rod it sits on
(0.111 R). The big glass spheres in the stills are a bloom artefact around a
small hot node, not a large sphere.

**The interior is populated, not hazy.** 257 filaments and 150 particles at
0.5–0.6 R, plus 28 gold orbiters at 0.47 R. It is a second graph inside the
first, which is exactly the "nodes made of nodes" argument the brand study
makes — arrived at independently.

## Materials, verbatim

| Name | Base colour | α | Emissive | Rough / metal |
|---|---|---|---|---|
| Dark inner glass | `0.024, 0.016, 0.102` | 0.35 | `0.04, 0.01, 0.10` | 0.10 / 0.05 |
| Cyan energy | `0.051, 0.549, 1.000` | 0.78 | `0.02, 0.65, 1.00` | 0.16 / 0.35 |
| Violet plasma | `0.420, 0.102, 0.949` | 0.78 | `0.55, 0.08, 1.00` | 0.16 / 0.35 |
| Hot white nodes | `0.800, 0.902, 1.000` | 1.00 | `1.00, 0.85, 1.00` | 0.12 / 0.10 |
| Gold particles | `1.000, 0.380, 0.031` | 0.92 | `1.00, 0.20, 0.01` | 0.18 / 0.55 |

**These are roles, not the palette.** archeus wears 32 palettes and four worlds;
baking this violet in would make the graph world the only one that looks right.
The mapping is violet → `accent2`, cyan → `accent`, gold → `warn`, hot white →
white, dark glass → `bg`. The *ratios* are what transfer: three quarters of the
shell in the second accent, a quarter in the first; nine parts cyan to one gold
in the interior particles; the core always white with a warm seed.

## Cost, and what has to be spent per distance

The full part list is ~1,150 primitives per cluster and the field holds forty.
That is a level-of-detail problem, not a budget refusal — the same one
`connections.drawCluster` and `tools/make_gifs.py` already solved by apparent
size. Near a cluster you can see a 0.02 R particle; at forty units you cannot
see the shell rods.

Suggested ladder, by apparent radius in pixels:

- **> 180 px** (the hero): everything.
- **60–180 px**: shell + beads + spokes + core + interior particles; drop the
  inner filaments and the gold orbiters.
- **20–60 px**: shell at detail 1 (42/120) + beads + core; no spokes, no interior.
- **< 20 px**: a bead and its halo. A 480-rod shell inside eight pixels is a
  solid disc, which is the exact failure the GIF renderer had to fix.

---

# The connection, from the model

Measured out of `notes/reference/connection.glb`. Its node names are
the spec — nothing here is inferred. Hub centres sit at ±3.80 and the conduit
spans 7.60 between them; the hub's glass shell is 1.56 across, so everything is
given against **Rh, the hub radius = 0.78 model units**.

## A link is a COAXIAL TRIPLE, not a tube

| Layer | Ø / Rh | Material |
|---|---|---|
| `Conduit_Outer_Housing` | 1.08 | dark housing — opaque, and it is what gives the link a silhouette |
| `Conduit_Glass_Layer` | 0.82 | deep blue glass, α 0.59 |
| `Conduit_Energy_Core` | 0.44 | neon violet, emissive |
| `Outer_Luminous_Rail` | 0.14 | one violet rail running the full length on the OUTSIDE of the housing |
| `Connector_Collar` | 1.49 Ø, 0.17 thick | gold ring where the conduit meets a hub |
| `Rail_Node` | 0.18 | hot white beads spaced along the rail |
| `Internal_Filament` | 0.08 | gold threads inside the glass |
| `Internal_CrossLink` | 0.10 | cyan threads, crossing them |
| `Energy_Particle` | 0.11 | cyan beads travelling inside |

Three concentric shells is the whole reason it reads as an object: a dark rim, a
translucent middle you can see threads through, and a hot filament at the axis.
Every version we shipped had one shell and argued about its falloff.

**In a shader this is nearly free.** The ribbon already carries `ax`, the
coordinate across the rod, so the layers are thresholds on it — no extra
geometry, no extra draw call.

## A hub is CONCENTRIC too, and it has rings

| Part | Ø / Rh | Material |
|---|---|---|
| `Hub_Housing` | 2.44 | dark housing |
| `Hub_GlassShell` | 2.00 | deep blue glass, α 0.59 |
| `Hub_EnergyCore` | 1.10 | neon violet, emissive |
| `Hub_HotCore` | 0.56 | hot white |
| `Hub_OuterRing` | 2.65 | cyan, 0.14 thick |
| `Hub_InnerRing` | 2.35 | violet |
| `Hub_EnergyRing` | 1.94 | gold |

So a bead is four nested spheres and three thin rings around them — white core,
violet energy, blue glass, dark housing. The "big glass sphere with a glowing
nucleus" reading from the stills was right; this gives the radii.

## Materials

| Name | Base | α | Emissive | Rough / metal |
|---|---|---|---|---|
| Dark Housing | `0.031, 0.047, 0.137` | 1.00 | — | 0.22 / 0.85 |
| Deep Blue Glass | `0.098, 0.314, 0.824` | 0.59 | `0.0, 0.20, 1.0` | 0.12 / 0.75 |
| Neon Violet | `0.510, 0.137, 1.000` | 1.00 | `1.0, 0.05, 1.0` | 0.18 / 0.65 |
| Hot White Core | `1.000, 0.961, 1.000` | 1.00 | `1.0, 1.0, 1.0` | 0.08 / 0.20 |
| Electric Cyan | `0.078, 0.667, 1.000` | 1.00 | `0.0, 0.80, 1.0` | 0.15 / 0.55 |
| Energy Gold | `1.000, 0.569, 0.098` | 1.00 | `1.0, 0.35, 0.02` | 0.18 / 0.75 |

Same rule as the cluster's: these are ROLES. violet → `accent2`, cyan →
`accent`, gold → `warn`, hot white → white, dark housing → `bg`. A palette
baked in would make one world right and thirty-one wrong.
