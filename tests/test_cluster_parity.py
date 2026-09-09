"""Three renderers, one cluster, and none of them is lit.

The GUI's background (`claude_sessions/web/stage.js`), the site's scroll journey
(`www/components/journey/scene.ts`) and the real architecture graph
(`claude_sessions/connections.py`) all draw the same object, measured out of
`notes/reference/cluster.glb` and `connection.glb`. The instruction that
produced this file was that all three must represent the SAME reference rather
than three approximations of it.

ALL THREE ARE FLAT. Every part the reference has, drawn as additive ribbons and
sprites, with no lighting model, no glass and no depth writes:

    "keep the complications of the cluster as it was before just remove the 3d
     part … just remove from all of this the 3d effect"
    "put this version of the cluster in the website too"

That was two instructions and it is worth keeping both, because the file spent
one round in between describing a deliberate SPLIT — the GUI flat, the site
still lit on the argument that a showcase and a background are asked for
different things. They are not being asked for different things. So the checks
below run over all three again, and what they are for has inverted: they used
to keep a renderer from quietly dropping the 3D, and they now keep one from
quietly putting it back.

What the three share is the SHAPE and the COLOUR RULES — the spec's
measurements, the role numbering, the chord — and the READS table says per
renderer which of them it spends, because they still do not all draw all of
it.

Three hand-typed copies of forty numbers do not stay equal — this repository
already records what happened to `docs/gui-audit.md`, which drifted to listing
seventeen routes that had never existed. So `claude_sessions/cluster_spec.py` is
the single source, `tools/gen_cluster_spec.py` generates the two front-end
copies, and this file is the gate:

  * the generated copies are current;
  * each renderer READS the spec rather than restating it;
  * the numbers the spec owns appear in no renderer as a bare literal;
  * and the one rule the whole rewrite exists for — never reduce a cluster to a
    single flat colour — holds in all three.
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'tools'))

from claude_sessions import cluster_spec as CS          # noqa: E402
from claude_sessions import connections                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    return io.open(os.path.join(ROOT, *parts), encoding='utf-8').read()


STAGE = _read('claude_sessions', 'web', 'stage.js')
SCENE = _read('www', 'components', 'journey', 'scene.ts')
CONN = _read('claude_sessions', 'connections.py')
#: the graph scene only — the other six scenes in stage.js draw other things
GRAPH = STAGE[STAGE.index('  graph(TH, c) {'):STAGE.index('  /* Terminal')]


def test_the_generated_copies_are_current():
    """`tools/gen_cluster_spec.py --check`, as a test.

    Same shape as the api.md gate, and for the same reason: a generated file
    that is allowed to go stale is a hand-maintained copy with extra steps."""
    import gen_cluster_spec
    for path, render in gen_cluster_spec.TARGETS:
        cur = io.open(path, encoding='utf-8').read().replace('\r\n', '\n')
        assert cur == render(), (
            f'{os.path.relpath(path, ROOT)} is stale — '
            f'run tools/gen_cluster_spec.py')


def test_every_renderer_reads_the_spec():
    """One imports it, two read the copy it generates. What none of them may do
    is state a number themselves."""
    assert 'from . import cluster_spec as _spec' in CONN
    assert 'const CL = CLUSTER;' in GRAPH, 'stage.js does not read the spec'
    assert "import { CLUSTER } from '@/lib/cluster-spec';" in SCENE
    # ...and the page the 2D canvas draws into actually receives it
    assert '__CLUSTER_JSON__' in CONN
    assert 'const CL=__CLUSTER_JSON__;' in CONN


#: What a renderer must READ, per renderer, because not all three draw all of
#: it — and since the GUI went flat, not all three draw the same PARTS either.
#: The site is the only one with a glass sleeve, a coaxial core and three
#: concentric spheres per junction, so it is the only one that reads their
#: radii; the GUI spends the populations and their placement; the 2D canvas
#: spends the frame's topology. A key in this list is one the renderer visibly
#: spends.
READS = {
    'stage.js graph scene': (
        # the populations and where they sit
        'SHELL_ROD_HALF', 'WEB_ROD_HALF', 'WEB_R', 'FRAME_HALF',
        'SPOKE_HALF', 'SPOKE_IN', 'SPOKE_OUT',
        'MOTE_R', 'MOTE_MIN', 'MOTE_MAX', 'ORBIT_R', 'ORBIT_N', 'FILAMENT_MIX',
        # the two nodes that are a dot with an outer circle, at their own radii
        'FRAME_BEAD_R', 'CORE_SHELL_R',
        # how much of it to draw at a given size, and how bright a rod is when
        # there are four hundred and eighty of them
        'LOD_BREAKS', 'ROD_ALPHA_BY_EDGES',
        # the conduit, as a line that stops on a hull
        'CONDUIT_REACH', 'CONDUIT_CLAMP',
        'PALETTE_FAMILIES',
    ),
    'www scene.ts': (
        # the frame and the spokes, as ribbons
        'FRAME_NODES', 'FRAME_EDGES', 'FRAME_HALF',
        'SPOKE_HALF', 'SPOKE_IN', 'SPOKE_OUT',
        # the two nodes that are a dot with an outer circle, at their own radii
        'FRAME_BEAD_R', 'CORE_SHELL_R',
        'PALETTE_FAMILIES', 'FILAMENT_MIX',
    ),
    'connections.py': (
        # a 2D canvas draws the coarse frame and its junctions, and the two
        # counts are the whole contract: twelve nodes on thirty edges
        'FRAME_NODES', 'FRAME_EDGES', 'FRAME_BEAD_R',
    ),
}

#: ...and the values that were WRONG, which must not come back. Each of these
#: was measured, shipped and then measured again against the render:
#:
#:   0.0555  the model's shell rod half-width. 480 rods at it cover more than
#:           the whole surface of the hull — the arithmetic is in
#:           cluster_spec.py — and what it drew was a featureless blue sphere.
#:   0.095   the frame tube at the spokes' weight, which made the frame read as
#:           plumbing rather than as a lattice with nodes on it.
#:   0.53 R  is still right for the inner web; what is gone is the SHELL at
#:           that width, so the pair is checked rather than the number.
SUPERSEDED = ('0.0555', '0.095 * n.r', 'RING(0)', 'const TONES =')


def test_every_renderer_reads_the_spec_keys_it_draws():
    """The positive form of "do not hardcode", and the one that survives.

    Scanning for a VALUE cannot work: 0.16 is the core radius and it is also
    every other smoothstep in a shader, so a value scan either misses the real
    divergence or fails on a coincidence — it did both before it was written
    this way. Reading the KEY is exact, and a renderer that typed a number
    instead would stop naming the key, which is the thing this catches:
    somebody tunes the frame in the GUI, the site keeps the old width, and the
    two stop being the same object with nothing breaking."""
    for label, src in (('stage.js graph scene', GRAPH), ('www scene.ts', SCENE),
                       ('connections.py', CONN)):
        prefix = 'CLUSTER.' if 'scene.ts' in label else 'CL.'
        for key in READS[label]:
            assert prefix + key in src, f'{label} does not read {key}'


def test_the_measurements_that_were_wrong_do_not_come_back():
    """Each of these shipped, was judged against the render and replaced. The
    docstring of SUPERSEDED says what each one cost."""
    code = re.sub(r'/\*.*?\*/', '', GRAPH, flags=re.S)
    code = re.sub(r'^\s*//.*$', '', code, flags=re.M)
    for bad in SUPERSEDED:
        assert bad not in code, f'a superseded measurement is back: {bad}'


def test_a_cluster_is_never_one_flat_colour_in_any_renderer():
    """THE rule, and the one every version of this scene broke by construction.

    A per-cluster `tone` indexed a shared five-stop ramp, so a cluster was one
    colour because the code could not express another. All three now walk a
    CHORD of four roles by a number derived from position — and the check is
    that each renderer reads a chord and that its ramp is gone, because a
    renderer that kept `hue5` would look right in a screenshot of one cluster
    and wrong the moment two are on screen."""
    for src, label in ((GRAPH, 'stage.js'), (SCENE, 'scene.ts')):
        assert 'chord(' in src, label
        assert 'gradT(' in src, f'{label}: the walk is not position-derived'
        assert 'hue5(v' not in src, f'{label}: the one-hue ramp is back'
    # the 2D canvas cannot run a shader, so it rotates around the node's OWN
    # hue instead — which is also the only correct answer there, since that hue
    # is real data (TYPE_COLORS) and not a decision this file gets to make
    assert 'function chordCol(col,t,lift){' in CONN
    assert 'function gradT(v,ax,seed){' in CONN

    # ...and no family in the shared table is one colour repeated
    for _w, name, roles in CS.PALETTE_FAMILIES:
        assert len(set(roles)) >= 3, f'{name} is not a chord: {roles}'


def test_no_renderer_draws_a_lit_or_glass_cluster_any_more():
    """The 3D came out of all three, and this is what keeps it out.

    The instruction that produced the glass sleeve is still a true reading of
    the reference — the structural tubes there ARE thick transparent glass, and
    one cylinder cannot be that, so it took two: a sleeve at FRAME_HALF and a
    brighter coaxial core at FRAME_CORE_HALF, only the core writing depth. It
    was built three times, in three renderers, and rejected as a look. The
    measurements survive in `cluster_spec.py`, where a measurement belongs; the
    rendering does not survive anywhere, and none of these three files may grow
    it back without a new instruction.

    A frame rod is one additive ribbon in a merged buffer. A junction is a dot
    with an outer circle. Nothing is shaded by a light and nothing writes
    depth."""
    strip = lambda t: re.sub(r'^\s*//.*$', '',
                             re.sub(r'/\*.*?\*/', '', t, flags=re.S), flags=re.M)
    for label, src in (('stage.js', GRAPH), ('scene.ts', SCENE)):
        code = strip(src)
        for gone in ('MeshPhysicalMaterial', 'InstancedMesh', 'DirectionalLight',
                     'HemisphereLight', 'PMREMGenerator', 'FRAME_CORE_HALF',
                     'depthWrite: true'):
            assert gone not in code, f'{label}: the 3D cluster is back ({gone})'
        # ...and what replaced it, in both: a ribbon rod and a ringed sprite
        assert 'blending: THREE.AdditiveBlending' in src \
            or 'blending: TH.AdditiveBlending' in src, label
        assert 'rim  = smoothstep(0.55, 0.92, ax)' in src, \
            f'{label}: a rod is not a ribbon with a wall term'
        assert 'kd' in src, f'{label}: the node populations are not separated'
    dc = CONN.split('function drawCluster(')[1].split('function draw()')[0]
    assert 'CL.FRAME_CORE_HALF' not in dc, \
        'connections.py: the sleeve-and-core double stroke is back'
    assert dc.count('ctx.stroke();') == 1, \
        'connections.py: a frame edge is more than one stroke again'


def test_the_conduits_still_carry_something_in_the_renderer_that_has_them():
    """The brief asks for energy flowing INSIDE the tubes, and the tubes are
    gone from every renderer — so the effect lives where there is still
    something for it to travel along.

    The GUI has conduits between its forty clusters and they are fine lines, so
    the packet IS the line brightening: a travelling gaussian on the segment's
    own parameter, seeded per SEGMENT and pushed onto both endpoints so it
    survives interpolation (without it every conduit pulses in lockstep, which
    is a strobe and not traffic).

    The site's six stations are joined by a scroll-driven link rather than by a
    field of conduits, and its per-station cages have no tube to run anything
    inside any more — the version that did ran a gaussian on `vLen`, the
    cylinder's own axis, hashed off the instance translation, and it went with
    the instanced cylinder. The travelling term it still has is the one on that
    link, which is the same idea on the only geometry left to hang it on.

    2D is deliberately not in this check: a canvas render is a still."""
    assert 'float packet(float at, float head){' in GRAPH, 'stage.js: no packet'
    assert 'packet(vT, fract(u_t * sp + vS))' in GRAPH, \
        'stage.js: the packet does not travel'
    assert 'cs.push(sd, sd);' in GRAPH, \
        'stage.js: the seed does not survive interpolation'
    # the site: the link is still drawn by scroll and still carries a head
    assert 'the link: a tube along the same curve, drawn by scroll' in SCENE
    # ...and the instanced-tube flow term is gone rather than half-removed
    for gone in ('varying float vLen;', 'instanceMatrix[3].xyz'):
        assert gone not in SCENE, f'scene.ts: the instanced tube is back ({gone})'


def test_the_roles_are_deepened_by_the_same_amount_in_both_gl_renderers():
    """The reference's hues are saturated and this palette's are pale, and the
    gap is LIGHTNESS: #7dcfff is already s = 1.0 (its max channel is 255), so a
    saturation push cannot move it, while dropping L to 0.46 lands it on the
    (0, 128, 233) a cut across a reference tube measures.

    The two renderers apply the same transform in two different places, and
    that is deliberate rather than sloppy: the GUI wears 32 palettes so it has
    to compute it at run time, while the site's HUES is a literal list, and a
    run-time THREE.Color round trip there would go through a MANAGED working
    colour space that the GUI has switched off — the same two lines of code
    would not produce the same two colours. So the site carries the deepened
    literals and this test is what keeps the two definitions in step."""
    import colorsys
    m = re.search(r'const DEEP_L = ([\d.]+), DEEP_S = ([\d.]+);', GRAPH)
    assert m, 'stage.js does not deepen its roles'
    dl, ds = float(m.group(1)), float(m.group(2))
    pale = ['#7dcfff', '#9d7bff', '#f7768e', '#73daca', '#e0af68', '#7ee787']
    want = []
    for h in pale:
        n = int(h[1:], 16)
        hh, li, sa = colorsys.rgb_to_hls(((n >> 16) & 255) / 255,
                                         ((n >> 8) & 255) / 255, (n & 255) / 255)
        r, g, b = colorsys.hls_to_rgb(hh, li * dl, min(1.0, sa * ds))
        want.append('#%02x%02x%02x' % (round(r * 255), round(g * 255), round(b * 255)))
    got = re.search(r'const HUES = \[([^\]]*)\]', SCENE)
    assert got, 'scene.ts has no HUES'
    assert [x.strip().strip("'") for x in got.group(1).split(',')] == want, \
        f'scene.ts HUES are not stage.js DEEP_L/DEEP_S applied: want {want}'


def test_the_roles_are_numbered_once_and_every_renderer_agrees():
    """A role index is a contract between three languages. The numbering lives
    in cluster_spec.py; each renderer turns a number into a colour in exactly
    one function, so a renderer cannot quietly decide that 2 is gold."""
    assert CS.ROLE_UNIFORMS == ('u_acc', 'u_acc2', 'u_err', 'u_warn', 'u_ok',
                                'u_white')
    assert STAGE.count('vec3 roleCol(float r){') == 1
    assert SCENE.count('vec3 roleCol(float r){') == 1
    # the magenta role is bound in both — it is the hue the reference most
    # obviously needed and the one neither renderer had
    assert 'u_err: {value: c.err' in STAGE
    assert 'u_err: { value: new THREE.Color(HUES[2]) }' in SCENE


def test_the_2d_view_keeps_its_two_do_nots():
    """`connections.py` draws the REAL architecture graph. Its positions come
    from the force layout and its colours from TYPE_COLORS, both of which are
    facts about a project. The reference's placement and its palette are
    properties of a picture, and importing them here would be drawing something
    the data does not say — so the chord ROTATES AROUND a node's own hue and
    nothing in this file invents a position."""
    assert 'TYPE_COLORS' in CONN
    dc = CONN.split('function drawCluster(')[1].split('function draw()')[0]
    for banned in ('PALETTE_FAMILIES', 'u_acc2', 'satellite'):
        assert banned not in dc, banned
    # the chord is a rotation OF col, not a replacement for it
    assert 'chordCol(col,' in dc


def test_the_payload_the_2d_view_gets_is_named_not_swept():
    """A payload built by sweeping the module ships whatever helper somebody
    adds next, and a front end that reads a number nobody meant to publish is a
    copy again. Same reason `EXPORTED` is a list rather than `globals()`."""
    assert 'def _cluster_payload():' in CONN
    got = set(connections._cluster_payload())
    assert got and got <= set(CS.EXPORTED), got - set(CS.EXPORTED)
    assert 'CONDUIT_HOUSING' not in got, \
        'the 2D canvas cannot spend a coaxial radius; do not ship it one'
