"""Three renderers, one cluster.

The GUI's background (`claude_sessions/web/stage.js`), the site's scroll journey
(`www/components/journey/scene.ts`) and the real architecture graph
(`claude_sessions/connections.py`) all draw the same object, measured out of
`notes/reference/cluster.glb` and `connection.glb`. The instruction that
produced this file was that all three must represent the SAME reference rather
than three approximations of it.

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
GRAPH = STAGE[STAGE.index('  graph(TH, c, ren) {'):STAGE.index('  /* Terminal')]


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
#: it: the 2D canvas has no conduit and the site's journey has no field of
#: forty. A key in this list is one the renderer visibly spends.
READS = {
    'stage.js graph scene': (
        'SHELL_ROD_HALF', 'SPOKE_HALF', 'WEB_ROD_HALF', 'FRAME_HALF',
        'FRAME_BEAD_R', 'FRAME_BEAD_HOT', 'FRAME_BEAD_ENERGY',
        'CORE_R', 'SEED_R', 'CORE_ENERGY_R', 'CORE_SHELL_R', 'SPOKE_IN',
        'SPOKE_OUT', 'WEB_R', 'MOTE_R', 'ORBIT_R', 'ORBIT_N',
        'MOTE_MIN', 'MOTE_MAX', 'LOD_BREAKS', 'ROD_ALPHA_BY_EDGES',
        'CONDUIT_HOUSING', 'CONDUIT_GLASS', 'CONDUIT_CORE', 'CONDUIT_REACH',
        'CONDUIT_CLAMP', 'COLLAR_D', 'COLLAR_THICK', 'PALETTE_FAMILIES',
        'FILAMENT_MIX',
    ),
    'www scene.ts': (
        'FRAME_HALF', 'FRAME_BEAD_R', 'FRAME_BEAD_HOT', 'FRAME_BEAD_ENERGY',
        'CORE_R', 'SEED_R', 'CORE_ENERGY_R', 'CORE_SHELL_R',
        'PALETTE_FAMILIES', 'FILAMENT_MIX',
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
    for label, src in (('stage.js graph scene', GRAPH), ('www scene.ts', SCENE)):
        prefix = 'CL.' if 'graph' in label else 'CLUSTER.'
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
