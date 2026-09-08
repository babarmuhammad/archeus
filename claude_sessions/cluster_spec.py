"""The cluster and the conduit, as numbers — the ONE place they live.

Three renderers draw this object: `claude_sessions/web/stage.js` (the GUI
background), `www/components/journey/scene.ts` (the site's scroll journey) and
`claude_sessions/connections.py` (the real architecture graph, on a 2D canvas).
They are three languages and three media, and until this module existed they
were also three hand-typed copies of forty numbers. This repository already
records what happens to a hand-maintained copy of something the code states —
`docs/gui-audit.md` catalogued seventeen routes that had never existed — so the
numbers are stated once, here, and the two front-end copies are GENERATED from
this file by `tools/gen_cluster_spec.py` with a test that fails when they are
stale. `connections.py` imports it directly.

Everything is measured out of `notes/reference/cluster.glb` and
`connection.glb`, transcribed in `notes/cluster-spec.md`, which is the prose
version of this table and carries the reasoning. Two rules for reading it:

  * **Cluster lengths are fractions of R, the hull radius.** In the model
    R = 2.8 units; expressed this way the cluster scales to any size.
  * **The parts list gives DIAMETERS.** A renderer wants half-widths, so the
    rod entries below are already halved and named `_HALF`. Getting this wrong
    doubles every strut in the scene, which is exactly how the first cut of the
    cage became a blown-out ball.

The one deliberate departure from the .glb: `FRAME_*`. The renders show a
coarse icosahedral frame of twelve big beads on thick tubes that the model file
does not contain. It is the most recognisable feature of the picture, reading
the .glb alone left it out twice, and the renders win on look because that is
what they are for.
"""

# ── the cluster, in fractions of R ───────────────────────────

#: `IcosahedronGeometry(1, d)` by detail: (vertices, edges). 162/480 is detail
#: TWO, not one — the model's `Outer node` count is 162 and its `Outer lattice
#: rod` count is 480, and both readings of the still image guessed detail 1.
SHELL_BY_DETAIL = {0: (12, 30), 1: (42, 120), 2: (162, 480)}

#: Half-widths, in R — and this is the one table where the RENDERS overrule
#: the .glb, measured off `notes/reference/cluster-render-single.png` with the
#: hull spanning 950 px (so R = 475 px).
#:
#: The model gives the shell rod as Ø 0.111 R. Four hundred and eighty rods at
#: that thickness on a sphere of radius R is a SOLID BALL — the surface area of
#: the shell is 4πR², the rods cover roughly 480 · 0.111R · 0.27R ≈ 14 R², and
#: 4π is 12.6. That is not a near miss, it is over a hundred per cent coverage,
#: and it is exactly what shipped: a featureless blue sphere. In the render the
#: fine mesh is a HAIRLINE web you see the interior through. So the shell and
#: the inner web are measured, not transcribed.
#:
#: The frame is measured for a different reason: it is not in the .glb at all
#: (see the module docstring), so the render is its only source. Tube Ø ≈ 40 px
#: = 0.084 R; 0.052 half is that plus a little presence.
SHELL_ROD_HALF = 0.013       # Outer lattice rod, 480 of them, on the hull
SPOKE_HALF = 0.040           # Hub spoke, 20 of them, from the core outward
WEB_ROD_HALF = 0.009         # Inner filament, a second cage at WEB_R

#: where each population sits, as a fraction of R
WEB_R = 0.53                 # Inner filament, 257 at 0.53 R
MOTE_R = 0.61                # Inner particle, 150 at 0.61 R
ORBIT_R = 0.47               # Orbit gold, 28 at 0.47 R
SPOKE_IN, SPOKE_OUT = 0.22, 0.90
#: ...and the spoke does NOT reach the core. Twenty rods meeting at one point
#: sum, additively, into a white star brighter than anything the scene means;
#: the model gets away with it because its materials are opaque. Starting at
#: 0.22 R and fading the first third is what replaces that.
SPOKE_FADE = 0.34

#: the lit centre. A white core with a gold seed inside it — the single thing
#: the parts list says that no still image did, and the reason every version we
#: built before reading the model had a hollow interior.
#: 0.16 and not the model's 0.1215. Twenty spokes converge on the centre and
#: at the model's radius the core is smaller than the bundle that hides it —
#: in the render the centre is the brightest thing in the cluster and reads
#: as a plasma ball, which is a thing you can SEE past the spokes.
CORE_R = 0.16                # Central glowing core, Ø 0.243 R in the model
SEED_R = 0.0645              # Central energy seed, Ø 0.129 R
#: ...inside a glass shell of its own, the way every junction is. The model
#: lists the core and the seed but not the volume around them; the render shows
#: the centre as the same object as a junction, one size up and brighter.
CORE_SHELL_R = 0.26

#: the coarse frame — the renders' contribution, see the module docstring
#: 0.042 and not 0.052. The ratio the render fixes is not the tube against
#: the hull, it is the tube against the JUNCTION it runs into: measured, a
#: junction is 3.2x its tube, and at 0.052 it was 2.6 and the frame read as
#: plumbing rather than as a lattice with nodes on it.
FRAME_HALF = 0.042           # measured: Ø 40 px against a 950 px hull
FRAME_EDGES = 30
FRAME_NODES = 12

#: THE JUNCTIONS, and they are the thing you are meant to look at. Measured at
#: Ø 130 px against the same 950 px hull — a junction is nearly THREE TIMES the
#: tube it sits on, which is what makes the frame read as built rather than as
#: wire. The previous version drew them as point sprites at 2.1x a shell bead,
#: which is a dot, and it is why the frame vanished into the haze.
FRAME_BEAD_R = 0.135         # the glass housing
SHELL_BEAD_R = 0.0375        # Outer node, Ø 0.075 R — the mesh's own texture

#: counts that scale with the hull rather than being fixed
MOTE_MIN, MOTE_MAX = 12, 240
ORBIT_N = 28

#: additive saturation is a property of HOW MANY rods there are, not of the
#: shader: a 480-rod shell at a 30-rod cage's per-rod alpha is a white ball,
#: and a 30-rod cage at a 480-rod shell's alpha is a wire frame. Keyed by edge
#: count so a shell and its alpha cannot get out of step.
ROD_ALPHA_BY_EDGES = {30: 1.0, 120: 0.42, 480: 0.16}

#: level of detail, by the cluster's own radius in world units. The field runs
#: 0.10 to 1.60, and a 480-rod shell inside eight pixels is a solid disc — the
#: same failure the GIF renderer had to fix by apparent size.
#: (0.22, 0.70), not (0.40, 0.95). The ladder is about what a cluster can
#: RESOLVE, and it was calibrated when a cluster was a wire cage: with the
#: frame and the junctions as lit solids the recognisable part of the object
#: survives to a much smaller size, and at the old first break half the field
#: was bare specks joined by conduit. The upper break moved for the opposite
#: reason to the one it looks like: the shell rod is a hairline now (0.013 R,
#: not 0.0555), so a 480-rod shell no longer collapses into a solid disc.
LOD_BREAKS = (0.22, 0.70)    # < .22 -> 0, < .70 -> 1, else 2


# ── the conduit, in fractions of Rh (the hub radius) ─────────
#
# A link is a COAXIAL TRIPLE, not a tube. Three concentric shells is the whole
# reason it reads as an object: a dark rim, a translucent middle you can see
# threads through, and a hot filament at the axis. Every version shipped before
# the model was read had ONE shell and argued about its falloff.

CONDUIT_HOUSING = 1.08       # dark, opaque — what gives the link an EDGE
CONDUIT_GLASS = 0.82         # deep glass, alpha 0.59
CONDUIT_CORE = 0.44          # hot, emissive, at the axis
CONDUIT_RAIL = 0.14          # ONE luminous rail, on the OUTSIDE of the housing
CONDUIT_RAIL_OFFSET = 0.86   # ...and OFF-AXIS. A cylinder lit from somewhere
                             # has a top; symmetry is what made every earlier
                             # tube read as a smear.
COLLAR_D, COLLAR_THICK = 1.49, 0.17   # the gold ring where conduit meets hub
RAIL_NODE = 0.18             # hot white beads spaced along the rail
FILAMENT_GOLD = 0.08         # gold threads inside the glass
FILAMENT_CROSS = 0.10        # cyan threads, crossing them
CONDUIT_PARTICLE = 0.11      # cyan beads travelling inside

#: how far into the hull a conduit reaches, and the clamp that stops two
#: overlapping hulls inverting a segment. At the full radius the tube stops
#: exactly ON the surface and its flat end hangs in mid-air, which is what made
#: every link look truncated rather than connected.
CONDUIT_REACH = 0.86
CONDUIT_CLAMP = 0.45

#: a hub is CONCENTRIC too, and it has rings. Four nested spheres and three
#: annuli, as fractions of Rh — white core, violet energy, blue glass, dark
#: housing. The version that guessed from a still had three parts and was
#: missing the ENERGY core, which is what stops a bead being a white dot.
HUB_HOUSING = 2.44
HUB_GLASS = 2.00
HUB_ENERGY = 1.10
HUB_HOT = 0.56
HUB_RING_OUTER = 2.65        # cyan
HUB_RING_INNER = 2.35        # violet
HUB_RING_ENERGY = 1.94       # gold


# ── colour ───────────────────────────────────────────────────
#
# THE ONE RULE, and it is the rule the brief calls the most important:
#
#     NEVER reduce a cluster to a single flat colour.
#
# Every version before this drew a cluster from `hue5(tone)` with `tone`
# constant across the cluster, so a cluster was one hue BY CONSTRUCTION and no
# amount of tuning inside that could produce the reference, where one cluster
# holds violet and magenta and cyan and gold at once.
#
# So a cluster gets a CHORD of four roles, not a hue. These are ROLES and not
# colours — archeus wears 32 palettes and four worlds, and baking the model's
# violet in would make the graph world the only one that looks right. The
# mapping is the same one every other surface uses.

ROLE_ACC = 0        # cyan     — u_acc
ROLE_ACC2 = 1       # violet   — u_acc2
ROLE_ERR = 2        # magenta  — u_err
ROLE_WARN = 3       # gold     — u_warn
ROLE_OK = 4         # green    — u_ok
ROLE_WHITE = 5      # white-hot

ROLE_UNIFORMS = ('u_acc', 'u_acc2', 'u_err', 'u_warn', 'u_ok', 'u_white')

#: A family is an ORDERED chord: primary, secondary, accent, highlight. The
#: weights are counted off `notes/reference/cluster-render-field.png` rather
#: than balanced by eye — violet is not merely first, it is forty per cent, and
#: the field reads as a violet field with other colours in it rather than a
#: blue field with violet in it.
#:
#: Each row is (weight, name, [primary, secondary, accent, highlight]).
PALETTE_FAMILIES = (
    (8, 'violet',  (ROLE_ACC2, ROLE_ERR,  ROLE_ACC,  ROLE_WARN)),
    (3, 'blend',   (ROLE_ACC2, ROLE_ACC,  ROLE_ERR,  ROLE_WHITE)),
    (2, 'cyan',    (ROLE_ACC,  ROLE_ACC2, ROLE_OK,   ROLE_WARN)),
    (2, 'magenta', (ROLE_ERR,  ROLE_ACC2, ROLE_ACC,  ROLE_WARN)),
    (3, 'gold',    (ROLE_WARN, ROLE_ERR,  ROLE_ACC2, ROLE_ACC)),
    (2, 'green',   (ROLE_OK,   ROLE_ACC,  ROLE_ACC2, ROLE_WARN)),
)

#: hue ratios WITHIN one cluster, straight off the model's part lists. These
#: are what stop the chord being decoration: the shell really is 360 rods in
#: the secondary and 120 in the primary, a hard 3:1 split rather than a blend,
#: and blending gave every rod the same in-between colour — a cluster of one
#: hue however the numbers were set.
SHELL_SPLIT = 0.75           # 3/4 primary, 1/4 secondary
WEB_SPLIT = 0.667            # Inner filament, 2/3 to 1/3
#: Inner particle, 136 cool to 14 gold. White was a guess from a still and it
#: is why the interior read as flat fog with sparkles in it.
MOTE_GOLD = 0.09
MOTE_WHITE = 0.015
#: the brief's split for the internal network, as cumulative stops
FILAMENT_MIX = (0.60, 0.85, 0.95)   # cool | magenta | gold | white-hot


def lod_for(radius):
    """Which shell detail a cluster of this world radius can carry."""
    lo, hi = LOD_BREAKS
    return 0 if radius < lo else 1 if radius < hi else 2


def family_for(seed):
    """The chord a cluster wears, from a deterministic seed in [0, 1).

    Deterministic is the whole point: the same cluster must look the same after
    a re-render, so this is a lookup on a hash and never `random()` per frame.
    """
    total = sum(w for w, _n, _r in PALETTE_FAMILIES)
    at = (seed - int(seed)) * total
    acc = 0
    for w, name, roles in PALETTE_FAMILIES:
        acc += w
        if at < acc:
            return name, roles
    return PALETTE_FAMILIES[-1][1], PALETTE_FAMILIES[-1][2]


#: everything the generated front-end copies carry. Named explicitly rather
#: than swept out of globals(): a generator that exports whatever happens to be
#: module-level exports the next helper somebody adds, and a front end that
#: reads a number nobody meant to publish is a copy again.
EXPORTED = (
    'SHELL_BY_DETAIL', 'SHELL_ROD_HALF', 'SPOKE_HALF', 'WEB_ROD_HALF',
    'WEB_R', 'MOTE_R', 'ORBIT_R', 'SPOKE_IN', 'SPOKE_OUT', 'SPOKE_FADE',
    'CORE_R', 'SEED_R', 'FRAME_HALF', 'FRAME_EDGES',
    'FRAME_NODES', 'FRAME_BEAD_R', 'SHELL_BEAD_R', 'CORE_SHELL_R',
    'MOTE_MIN', 'MOTE_MAX', 'ORBIT_N', 'ROD_ALPHA_BY_EDGES', 'LOD_BREAKS',
    'CONDUIT_HOUSING', 'CONDUIT_GLASS', 'CONDUIT_CORE', 'CONDUIT_RAIL',
    'CONDUIT_RAIL_OFFSET', 'COLLAR_D', 'COLLAR_THICK', 'RAIL_NODE',
    'FILAMENT_GOLD', 'FILAMENT_CROSS', 'CONDUIT_PARTICLE', 'CONDUIT_REACH',
    'CONDUIT_CLAMP',
    'HUB_HOUSING', 'HUB_GLASS', 'HUB_ENERGY', 'HUB_HOT',
    'HUB_RING_OUTER', 'HUB_RING_INNER', 'HUB_RING_ENERGY',
    'ROLE_UNIFORMS', 'PALETTE_FAMILIES', 'SHELL_SPLIT', 'WEB_SPLIT',
    'MOTE_GOLD', 'MOTE_WHITE', 'FILAMENT_MIX',
)
